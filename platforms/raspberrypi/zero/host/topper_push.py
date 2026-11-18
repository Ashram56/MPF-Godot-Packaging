#!/usr/bin/env python3
"""Copy the topper's videos from the PuP Pack to the Pi Zero W (test without the platform's media server).

    python3 topper_push.py PACK_DIR                       # lists what would be sent
    python3 topper_push.py PACK_DIR --send pi@10.55.0.2   # sends it (tar over ssh, no rsync needed)

The topper's playlists are those of PuP screens 13 and 14: their default background (screens.pup) and every active row of
triggers.pup on those screens (the same choice as the platform's mpf_godot/pup_remote/media.py). On the Zero the files go to
/var/lib/pup-topper/media/<Folder>/<File>; set download=false in /boot/firmware/pup-topper.cfg there first, then
`sudo systemctl restart pup-topper`. Standard library only; read-only on the pack.
"""
import argparse
import csv
import os
import subprocess
import sys

SCREENS = (13, 14)
FILES = (".mp4", ".m4v", ".mov", ".avi", ".wmv", ".webm", ".mkv", ".f4v", ".png", ".jpg", ".jpeg")
DEST = "/var/lib/pup-topper/media"


def rows(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        data = list(csv.reader(f))
    head = [h.strip() for h in data[0]] if data else []
    return [dict(zip(head, (c.strip() for c in r))) for r in data[1:] if any(c.strip() for c in r)]


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def wanted(pack):
    lists = set()
    for r in rows(os.path.join(pack, "screens.pup")):
        if num(r.get("ScreenNum")) in SCREENS and r.get("PlayList"):
            lists.add(r["PlayList"].lower())
    for r in rows(os.path.join(pack, "triggers.pup")):
        if num(r.get("ScreenNum")) in SCREENS and r.get("Active", "1") == "1" and r.get("PlayList"):
            lists.add(r["PlayList"].lower())
    return lists


def files(pack):
    out = []
    lists = wanted(pack)
    for folder in sorted(os.listdir(pack)):
        path = os.path.join(pack, folder)
        if folder.lower() in lists and os.path.isdir(path):
            out += [folder + "/" + n for n in sorted(os.listdir(path))
                    if os.path.isfile(os.path.join(path, n)) and n.lower().endswith(FILES)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pack")
    ap.add_argument("--send", metavar="USER@HOST")
    a = ap.parse_args()
    found = files(a.pack)
    size = sum(os.path.getsize(os.path.join(a.pack, f)) for f in found)
    print("%d files, %.0f MB:" % (len(found), size / 1e6))
    for f in found:
        print("  " + f)
    if not found or not a.send:
        return
    tar = subprocess.Popen(["tar", "-C", a.pack, "-cf", "-"] + found, stdout=subprocess.PIPE)
    ssh = subprocess.run(["ssh", a.send, "mkdir -p %s && tar -C %s -xf -" % (DEST, DEST)], stdin=tar.stdout)
    tar.wait()
    sys.exit(ssh.returncode or tar.returncode)


main()
