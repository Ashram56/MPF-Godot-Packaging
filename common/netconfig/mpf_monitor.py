"""Switch monitor and saved logs for the setup page (standard library only).

The monitor is a BCP client of the running game (the BCP server MPF itself opens for outside clients like MPF Monitor, 127.0.0.1:5051 unless MPF_BCP_HOST / MPF_BCP_PORT say
otherwise): `monitor_start?category=switches` for the changes, `service?subcommand=list_switches` for the names and states,
`switch?name=X&state=N` to set one (1 on, 0 off, -1 flip), exactly what MPF's own monitor does. The connection exists only while
a page asks for it (`snapshot()` is called by the page about every second) and closes 20 s after the last call, so a machine
nobody looks at has no extra client.

The log writer (`save_log()`) puts a snapshot of the game's output on the data partition, because the game's own logs are in RAM
in read-only mode: one text file with the machine's state, the journal of the game and of this page, the game's log files and the
latest switch changes, ready to be handed to someone who debugs the machine (`MPF_SAVED_LOGS_DIR`, the 20 latest are kept).
"""
import json
import os
import platform
import re
import socket
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlsplit

import mpf_common as C

HOST = os.environ.get("MPF_BCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MPF_BCP_PORT", "5051"))
IDLE = 20          # seconds without a page asking: the connection closes
KEEP_LOGS = 20
SAVED = os.environ.get("MPF_SAVED_LOGS_DIR") or (os.path.join(C.DATA, "logs") if C.READONLY else "/var/lib/mpf-logs")


def encode(cmd, **kw):
    """One BCP line (without the newline): ints and bools carry their type prefix like MPF's own encoder."""
    parts = []
    for k, v in kw.items():
        s = "bool:" + str(v) if isinstance(v, bool) else "int:" + str(v) if isinstance(v, int) else quote(str(v), "")
        parts.append(f"{quote(k, '')}={s}")
    return cmd + ("?" + "&".join(parts) if parts else "")


def decode(line):
    u = urlsplit(line, allow_fragments=False)
    if u.query.startswith("json="):
        try:
            return u.path, json.loads(u.query[5:])
        except ValueError:
            return u.path, {}
    out = {}
    for k, v in parse_qs(u.query, keep_blank_values=True).items():
        v = v[0]
        if v.startswith("int:"):
            try:
                v = int(v[4:])
            except ValueError:
                pass
        elif v.lower() in ("bool:true", "bool:false"):
            v = v.lower() == "bool:true"
        elif v == "NoneType:":
            v = None
        else:
            v = unquote(v)
        out[k] = v
    return u.path, out


class Monitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.sock = None
        self.switches = {}       # name -> {name, label, number, board, state}
        self.order = []
        self.log = []            # latest changes, oldest first: [time, name, state]
        self.error = ""
        self.last_use = 0.0
        self.thread = None

    # -------------------------------------------------------------- connection
    def _run(self):
        try:
            s = socket.create_connection((HOST, PORT), timeout=3)
        except OSError as e:
            self.error = f"cannot reach the game's BCP server ({HOST}:{PORT}): {e.strerror or e}. Is the game running?"
            return
        s.settimeout(1.0)
        with self.lock:
            self.sock = s
            self.error = ""
        try:
            self._send("monitor_start", category="switches")
            self._send("service", subcommand="list_switches", values="name,label,number,board,state")
            buf = b""
            while time.time() - self.last_use < IDLE:
                try:
                    chunk = s.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    self.error = "the game closed the connection"
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self._handle(line.decode("utf-8", "replace").strip())
        except OSError as e:
            self.error = f"connection lost: {e.strerror or e}"
        finally:
            with self.lock:
                self.sock = None
            try:
                s.close()
            except OSError:
                pass

    def _send(self, cmd, **kw):
        with self.lock:
            s = self.sock
        if s is None:
            raise ValueError("the game is not connected")
        try:
            s.sendall((encode(cmd, **kw) + "\n").encode())
        except OSError as e:
            raise ValueError(f"cannot send to the game: {e.strerror or e}")

    def _handle(self, line):
        cmd, kw = decode(line)
        with self.lock:
            if cmd == "list_switches":
                self.switches, self.order = {}, []
                for row in kw.get("switches", []):
                    try:
                        name, label, number, board, state = row
                    except (TypeError, ValueError):
                        continue
                    self.switches[name] = {"name": name, "label": "" if label in (None, "%") else label, "number": str(number), "board": board or "", "state": int(state or 0)}
                    self.order.append(name)
            elif cmd == "switch" and kw.get("name") in self.switches:
                st = 1 if int(kw.get("state") or 0) else 0
                self.switches[kw["name"]]["state"] = st
                self.log.append([round(time.time(), 2), kw["name"], st])
                del self.log[:-200]

    def _touch(self):
        self.last_use = time.time()
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    # -------------------------------------------------------------- the page
    def snapshot(self, since=0):
        self._touch()
        with self.lock:
            return {"connected": self.sock is not None, "error": self.error,
                    "switches": [self.switches[n] for n in self.order], "now": round(time.time(), 2),
                    "log": [e for e in self.log if e[0] > since][-100:]}

    def set_switch(self, name, do):
        with self.lock:
            known = name in self.switches
        if not known:
            raise ValueError("unknown switch")
        if do not in ("toggle", "on", "off", "tap"):
            raise ValueError("do: toggle, on, off or tap")
        self._touch()
        if do == "tap":
            self._send("switch", name=name, state=1)
            threading.Timer(0.15, lambda: self._tap_release(name)).start()
        else:
            self._send("switch", name=name, state={"toggle": -1, "on": 1, "off": 0}[do])

    def _tap_release(self, name):
        try:
            self._send("switch", name=name, state=0)
        except ValueError:
            pass


MON = Monitor()


# ---------------------------------------------------------------- saved logs
def _tail(path, limit=120_000):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - limit))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _journal(unit, lines=400):
    r = C.run("journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso")
    return (r.stdout or r.stderr).strip() or "(nothing)"


def build_log(game=None):
    """The text of a log snapshot: what someone debugging the machine needs, in one file."""
    out = [f"== MPF log snapshot {time.strftime('%Y-%m-%d %H:%M:%S %z')} ==",
           f"host {socket.gethostname()}  {platform.machine()}  {platform.release()}",
           f"game {game['id']}@{game['version']} ({game['name']})" if game else "game (none active)"]
    try:
        with open("/proc/uptime") as f:
            out.append("uptime " + f.read().split()[0] + " s")
    except OSError:
        pass
    mode = C.mode_status()
    if mode:
        out.append(f"mode {mode[0]}")
    out += ["", "== journal: mpf-game.service ==", _journal("mpf-game.service"),
            "", "== journal: mpf-netconfig / inbox ==", _journal("mpf-netconfig.service", 120), _journal("mpf-netconfig-inbox.service", 120)]
    for folder in (C.VOLATILE_LOGS, os.path.join(game["path"], "game", "logs") if game else ""):
        if folder and os.path.isdir(folder):
            files = sorted((os.path.join(folder, n) for n in os.listdir(folder) if n.endswith((".log", ".txt"))),
                           key=lambda p: -os.path.getmtime(p))[:4]
            for p in files:
                out += ["", f"== {p} (end) ==", _tail(p)]
            break
    with MON.lock:
        sw = list(MON.log)[-60:]
        active = [n for n, s in MON.switches.items() if s["state"]]
    if sw:
        out += ["", "== latest switch changes (monitor) =="] + [f"{time.strftime('%H:%M:%S', time.localtime(t))} {n} {'on' if s else 'off'}" for t, n, s in sw]
        out.append("active now: " + (", ".join(active) or "none"))
    return "\n".join(out) + "\n"


def save_log(game=None):
    """Write a snapshot, keep the latest KEEP_LOGS, return its file name."""
    os.makedirs(SAVED, exist_ok=True)
    gid = re.sub(r"[^A-Za-z0-9._@-]", "_", f"{game['id']}@{game['version']}") if game else "game"
    name = f"{time.strftime('%Y%m%d-%H%M%S')}-{gid}.log.txt"
    with open(os.path.join(SAVED, name), "w", encoding="utf-8") as f:
        f.write(build_log(game))
    for old in sorted(saved_logs(), reverse=True)[KEEP_LOGS:]:
        try:
            os.remove(os.path.join(SAVED, old))
        except OSError:
            pass
    return name


def saved_logs():
    try:
        return sorted(n for n in os.listdir(SAVED) if n.endswith(".log.txt"))
    except OSError:
        return []


def read_saved(name):
    """Text of one saved log; the name must be one of the listed files (no path)."""
    if name not in saved_logs():
        return None
    return _tail(os.path.join(SAVED, name), 5_000_000)
