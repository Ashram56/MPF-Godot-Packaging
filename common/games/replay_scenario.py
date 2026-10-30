#!/usr/bin/env python3
"""Replay a scenario recorded on the setup page's Monitor into a running MPF (a simulation, for qualification tests).

    python3 replay_scenario.py scenario.json [--host 127.0.0.1] [--port 5051] [--speed 1] [--wait 30]

The file is what the page's Download button gives (or `/var/lib/mpf-netconfig/scenarios/<game id>/<name>.json`): timed switch changes,
`{"format": 1, "events": [[seconds, switch, "on|off|toggle|tap"], ...]}`. The tool talks to MPF's BCP server like the page does, so it
works against any game started in simulation (`mpf game -x`, a virtual platform) with no hardware, e.g. from a test script after a
change to the game's code. It waits for the BCP server to come up (`--wait`), plays the events with their timing and exits 0 when all
were sent; 1 if a switch is unknown to the game (the list of switches comes from the game, so a renamed switch is caught), 2 if it cannot connect.
"""
import argparse
import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "netconfig"))
os.environ.setdefault("MPF_STATE_DIR", "/tmp")
from mpf_monitor import check_events, decode, encode  # noqa: E402

STATE = {"on": 1, "off": 0}


def switches_of(sock):
    sock.sendall((encode("service", subcommand="list_switches", values="name,label,number,board,state") + "\n").encode())
    buf, end = b"", time.time() + 10
    while time.time() < end:
        try:
            buf += sock.recv(65536)
        except socket.timeout:
            continue
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            cmd, kw = decode(line.decode("utf-8", "replace").strip())
            if cmd == "list_switches":
                return {row[0]: int(row[4] or 0) for row in kw.get("switches", [])}
    raise SystemExit("the game did not list its switches")


def connect(host, port, wait):
    end = time.time() + wait
    while True:
        try:
            s = socket.create_connection((host, port), timeout=3)
            s.settimeout(1.0)
            return s
        except OSError as e:
            if time.time() > end:
                print(f"cannot reach MPF's BCP server at {host}:{port}: {e}", file=sys.stderr)
                sys.exit(2)
            time.sleep(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5051)
    ap.add_argument("--speed", type=float, default=1.0, help="2 plays twice as fast")
    ap.add_argument("--wait", type=float, default=30, help="seconds to wait for the BCP server")
    a = ap.parse_args()
    with open(a.scenario, encoding="utf-8") as f:
        events = check_events(json.load(f)["events"])
    s = connect(a.host, a.port, a.wait)
    state = switches_of(s)
    missing = sorted({n for _, n, _ in events if n not in state})
    if missing:
        print("this game has no switch named: " + ", ".join(missing), file=sys.stderr)
        return 1
    t0 = time.monotonic()
    for t, name, do in events:
        time.sleep(max(0.0, t / a.speed - (time.monotonic() - t0)))
        if do == "tap":
            s.sendall((encode("switch", name=name, state=1) + "\n").encode())
            time.sleep(0.15)
            new = 0
        else:
            new = (1 - state[name]) if do == "toggle" else STATE[do]
        state[name] = new
        s.sendall((encode("switch", name=name, state=new) + "\n").encode())
    print(f"{len(events)} events sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
