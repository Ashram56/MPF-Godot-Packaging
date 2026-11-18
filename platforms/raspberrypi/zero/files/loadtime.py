#!/usr/bin/env python3
"""Time from loadfile to the first frame (mpv's playback-restart) on the Zero, hardware decoder against software, in one
long-lived mpv (as the topper agent runs it), no screen output.  Run on the Zero:  python3 loadtime.py [FILE]"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time

FILE = sys.argv[1] if len(sys.argv) > 1 else "/var/lib/pup-topper/media/Background - Topper/TronLegacyLogo.mp4"
sock = os.path.join(tempfile.gettempdir(), "loadtime-%d.sock" % os.getpid())
proc = subprocess.Popen(["mpv", "--no-config", "--idle=yes", "--vo=null", "--ao=null", "--no-terminal", "--keep-open=no",
                         "--hwdec=v4l2m2m-copy", "--input-ipc-server=" + sock])
for _ in range(300):
    if os.path.exists(sock):
        break
    time.sleep(0.1)
s = socket.socket(socket.AF_UNIX)
s.connect(sock)
s.settimeout(30)
buf = b""


def events():
    global buf
    while True:
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                yield json.loads(line)
            except ValueError:
                pass
        buf += s.recv(65536)


def cmd(*c):
    s.sendall(json.dumps({"command": list(c)}).encode() + b"\n")


def wait(name, limit=30):
    end = time.time() + limit
    for ev in events():
        if ev.get("event") == name:
            return time.time()
        if time.time() > end:
            return None


m = re.search(r"mpv 0\.(\d+)", subprocess.run(["mpv", "--version"], capture_output=True, text=True).stdout)
INDEX = [-1] if (int(m.group(1)) >= 38 if m else True) else []


def load(option):
    t0 = time.time()
    cmd("loadfile", FILE, "replace", *INDEX, option)
    t1 = wait("playback-restart")
    return None if t1 is None else t1 - t0


try:
    for option in ("hwdec=v4l2m2m-copy", "hwdec=no", "hwdec=v4l2m2m-copy", "hwdec=no"):
        times = [load(option) for _ in range(4)]
        print("%-20s %s s" % (option, " ".join("%.2f" % t if t else "timeout" for t in times)), flush=True)
finally:
    proc.terminate()
