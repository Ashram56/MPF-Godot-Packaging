#!/usr/bin/env python3
"""Make a game bundle (the archive the setup page, the inbox and inject_image.py install) from a folder of your own code.

    make_bundle.py SRC --id my-game --name "My game" --version 1.0 --start "python3 run.py" [-o DIR]

SRC is the folder that holds your game (an MPF machine folder, a Godot project, a Python launcher: anything the start command
can run). It is copied to `game/` inside the bundle, the bundle's working folder is `game/`, and the result is
`<id>@<version>.tar.xz` with a `.sha256` beside it. The format is described in common/games/README.md.

Options of the common cases:
  --start CMD        what runs the game (default `python3 run.py`). `python3` is the base system's venv python (MPF installed),
                     any other name is looked up in that venv's bin first (`mpf`), then on the PATH. It runs in `game/`.
  --no-display       a game that opens no window (the page does not wait for the X session before starting it)
  --keep PATH        a file or folder (relative to `game/`) that an update carries over to the next version: settings, scores
                     (repeatable; default none). PuP Packs listed by --pup-dir are linked rather than copied.
  --pup-dir DIR      where this game's PuP Pack goes (relative to `game/`); the page then offers the Pack upload for it
  --pup-install CMD  the command that installs a pack (`ZIP_PATH_OR_URL` stands for the zip; runs in the game's folder as the game user)
  --pup-media DIR    the part of the pack that is large media (hard-linked between versions)
  --arch ARCH        `all` (default: no native binary), `arm64`, `x86_64` or `arm64+x86_64`
  --platform-addon N take the platform's own build of a binary add-on (`gde_gozen`) instead of one from your folder
  --exclude GLOB     leave out files (repeatable; `.git`, `__pycache__`, `*.pyc`, `logs` are always left out)
  --description T / --icon FILE   text and picture shown on the page's game list (icon relative to `game/`)
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import tarfile

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
ALWAYS = [".git", "__pycache__", "*.pyc", "logs", ".venv", ".godot/mono"]


def die(msg):
    sys.exit(f"make_bundle: {msg}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], epilog="See the top of this file for details.")
    ap.add_argument("src")
    ap.add_argument("--id", required=True)
    ap.add_argument("--name")
    ap.add_argument("--version", required=True)
    ap.add_argument("--start", default="python3 run.py")
    ap.add_argument("--no-display", action="store_true")
    ap.add_argument("--keep", action="append", default=[])
    ap.add_argument("--pup-dir")
    ap.add_argument("--pup-media")
    ap.add_argument("--pup-install")
    ap.add_argument("--arch", default="all")
    ap.add_argument("--platform-addon", action="append", default=[])
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--description", default="")
    ap.add_argument("--icon")
    ap.add_argument("-o", "--output-dir", default=".")
    a = ap.parse_args()
    if not os.path.isdir(a.src):
        die(f"{a.src}: not a folder")
    if not ID_RE.match(a.id):
        die("--id: lowercase letters, digits, . _ - (at most 64)")
    if not VERSION_RE.match(a.version):
        die("--version: letters, digits, . _ + - (at most 64)")
    if a.arch not in ("all", "arm64", "x86_64", "arm64+x86_64"):
        die("--arch: all, arm64, x86_64 or arm64+x86_64")
    for k in a.keep:
        if k.startswith("/") or ".." in k.split("/"):
            die(f"--keep {k}: a path inside the game folder")

    bundle = {
        "format": 1, "id": a.id, "name": a.name or a.id, "version": a.version,
        "description": a.description,
        "target": {"os": "linux", "arch": a.arch},
        "run": {"start": a.start, "cwd": "game", "needs_display": not a.no_display},
        "keep_on_update": ["game/" + k for k in a.keep],
    }
    if (a.pup_media or a.pup_install) and not a.pup_dir:
        die("--pup-media and --pup-install go with --pup-dir")
    if a.pup_dir:
        bundle["pup"] = {"pack_dir": "game/" + a.pup_dir.strip("/"), "needs_restart": True}
        if a.pup_install:
            bundle["pup"]["install"] = a.pup_install
        if a.pup_media:
            bundle["pup"]["media_dir"] = "game/" + a.pup_media.strip("/")
        bundle["keep_on_update"].append("game/" + a.pup_dir.strip("/"))
    if a.platform_addon:
        bundle["platform_addons"] = a.platform_addon
    if a.icon:
        bundle["icon"] = "game/" + a.icon
    top = f"{a.id}@{a.version}"
    skip = ALWAYS + a.exclude

    files = []
    for base, dirs, names in os.walk(a.src):
        dirs[:] = sorted(d for d in dirs if not any(fnmatch.fnmatch(d, g) or fnmatch.fnmatch(os.path.relpath(os.path.join(base, d), a.src), g) for g in skip))
        for n in sorted(names):
            rel = os.path.relpath(os.path.join(base, n), a.src)
            if not any(fnmatch.fnmatch(n, g) or fnmatch.fnmatch(rel, g) for g in skip):
                files.append(rel)
    if not files:
        die("nothing to pack")
    start_prog = a.start.split()[0]
    if start_prog in ("python", "python3") and len(a.start.split()) > 1 and not a.start.split()[1].startswith("-") \
            and a.start.split()[1] not in files and not os.path.exists(os.path.join(a.src, a.start.split()[1])):
        print(f"warning: {a.start.split()[1]} is not in {a.src}", file=sys.stderr)

    sums = "".join(f"{sha256(os.path.join(a.src, r))}  game/{r}\n" for r in files)
    os.makedirs(a.output_dir, exist_ok=True)
    out = os.path.join(a.output_dir, top + ".tar.xz")
    import io
    with tarfile.open(out, "w:xz") as t:
        def add_bytes(name, data):
            i = tarfile.TarInfo(f"{top}/{name}")
            i.size, i.mode = len(data), 0o644
            t.addfile(i, io.BytesIO(data))
        add_bytes("bundle.json", (json.dumps(bundle, indent=2) + "\n").encode())
        add_bytes("SHA256SUMS", sums.encode())
        for r in files:
            p = os.path.join(a.src, r)
            i = t.gettarinfo(p, f"{top}/game/{r}")
            i.uid = i.gid = 0
            i.uname = i.gname = "root"
            with open(p, "rb") as f:
                t.addfile(i, f)
    with open(out + ".sha256", "w") as f:
        f.write(f"{sha256(out)}  {os.path.basename(out)}\n")
    print(f"{out}: {len(files)} files, {os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    main()
