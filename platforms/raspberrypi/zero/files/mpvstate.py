#!/usr/bin/env python3
"""Read-only: the state of the topper's running mpv (what is playing, whether time advances, decoder, dropped frames).
On the Zero:  python3 mpvstate.py     (or from another computer: ssh pi@10.55.0.2 python3 - < mpvstate.py)"""
import glob
import json
import socket
import time

PROPS = ["path", "time-pos", "duration", "pause", "core-idle", "eof-reached", "loop-file", "hwdec-current", "paused-for-cache",
         "estimated-vf-fps", "frame-drop-count", "decoder-frame-drop-count", "video-params/w", "video-params/h", "idle-active"]
socks = sorted(glob.glob("/tmp/pup-topper-mpv-*.sock"))
if not socks:
    raise SystemExit("no topper mpv socket")
s = socket.socket(socket.AF_UNIX)
s.connect(socks[-1])
s.settimeout(5)
buf = b""


def get(name):
    global buf
    s.sendall(json.dumps({"command": ["get_property", name], "request_id": 77}).encode() + b"\n")
    while True:
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("request_id") == 77:
                return msg.get("data", msg.get("error"))
        buf += s.recv(65536)


for round_ in (1, 2):
    print("--- sample", round_, time.strftime("%H:%M:%S"))
    for p in PROPS:
        print("%-28s %s" % (p, get(p)))
    time.sleep(2)
