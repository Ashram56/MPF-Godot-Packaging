#!/usr/bin/env python3
"""Make a format 2 game bundle (the archive the setup page, the inbox and inject_image.py install) from a folder of your own MPF code.

    make_bundle.py SRC --id my-game --name "My game" --version 1.0 \
        --hardware virtual=hw_virtual --hardware proc=hw_proc [--keep data] [-o DIR]

SRC is an MPF machine folder with a Godot (GMC) project: `project.godot` and MPF's `config/` side by side. It is copied to `game/`
inside the bundle as it is; the result is `<id>@<version>.tar.xz` with a `.sha256` beside it. The bundle is **files and facts**
(format 2, platforms/game-bundles.md): no command, no start script, no settings tool. The platform launches the game itself
(`python -m mpf_godot run game -c <configs>`), stores the settings and applies them. Nothing is generated: run Godot's import
(`godot --headless --import`) in SRC first, so the machine does not import at its first start.

Options:
  --configs A,B      MPF config files of config/ always loaded (default `config`)
  --hardware N=A,B   one hardware choice: its name and the extra config files of config/ it loads (repeatable). Two or more add a
                     "Hardware" setting on the page (default `virtual` when there is one); one is always used. Without any, the
                     platform loads only --configs: they must name MPF's hardware platform themselves.
  --settings FILE    your own settings schema (a JSON file in SRC: `groups` and `options`, each with one target `godot_arg`, `ini`
                     or `hardware`; platforms/game-bundles.md); the Hardware setting is added to it when it has none
  --keep PATH        a file or folder (relative to `game/`) that an update carries over to the next version: settings, scores,
                     audits (repeatable). `.platform/` (the page's settings, the PuP link, MPF_GAME_DATA) is always kept.
  --dmd-rom NAME     the PinMAME set name: the default Serum colourisation of the game on a ZeDMD
  --pup-rom NAME / --pup-manifest FILE   the PuP Pack the game reads (MPF_PUP_PACK) and its manifest in SRC (the list of the
                     pack's files the game uses, never a file of the pack); the page then offers the pack upload for this game
  --arch ARCH        `all` (default: no native binary), `arm64`, `x86_64` or `arm64+x86_64`
  --platform-addon N an add-on the platform installs for the machine (default `gde_gozen` and `mpf-gmc`; repeat to choose); your
                     own copy in SRC/addons/N is left out
  --exclude GLOB     leave out files (repeatable; `.git`, `__pycache__`, `*.pyc`, `logs`, `.venv` are always left out)
  --description T / --icon FILE   text and picture shown on the page's game list (icon relative to SRC)
"""
import argparse
import datetime
import fnmatch
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "netconfig"))
import mpf_contract as K  # noqa: E402

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ALWAYS = [".git", "__pycache__", "*.pyc", "logs", ".venv", ".godot/mono", ".platform"]
SETTINGS = "settings.json"
HW_OPTION = {"id": "machine.hardware", "group": "machine", "label": "Hardware", "type": "choice",
             "help": "virtual: no machine, play with the keyboard; the others: the machine's own boards.", "target": {"hardware": True}}


def die(msg):
    sys.exit(f"make_bundle: {msg}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inside(rel, what):
    if not rel or rel.startswith("/") or ".." in rel.replace("\\", "/").split("/"):
        die(f"{what} {rel}: a path inside the game folder")
    return rel.replace("\\", "/").strip("/")


def hardware_sets(items):
    sets = {}
    for item in items:
        name, _, cfgs = item.partition("=")
        if not NAME_RE.match(name) or not cfgs:
            die(f"--hardware {item}: NAME=config[,config]")
        sets[name] = [c.strip() for c in cfgs.split(",") if c.strip()]
    return sets


def settings_schema(src, rel, sets):
    """The settings schema of the bundle (or None): the game's own file, plus the Hardware setting when there are two sets or more."""
    s = {"groups": [], "options": []}
    if rel:
        try:
            with open(os.path.join(src, rel), encoding="utf-8") as f:
                s = json.load(f)
        except (OSError, ValueError) as e:
            die(f"--settings {rel}: {e}")
    if len(sets) > 1 and not any((o.get("target") or {}).get("hardware") for o in s.get("options", [])):
        if not any(g.get("id") == "machine" for g in s.setdefault("groups", [])):
            s["groups"].insert(0, {"id": "machine", "label": "Machine"})
        s.setdefault("options", []).insert(0, dict(HW_OPTION, choices=list(sets), default="virtual" if "virtual" in sets else list(sets)[0]))
    return s if (rel or s["options"]) else None


def collect(src, skip):
    files = []
    for base, dirs, names in os.walk(src):
        dirs[:] = sorted(d for d in dirs if not any(fnmatch.fnmatch(d, g) or fnmatch.fnmatch(os.path.relpath(os.path.join(base, d), src).replace(os.sep, "/"), g) for g in skip))
        for n in sorted(names):
            rel = os.path.relpath(os.path.join(base, n), src).replace(os.sep, "/")
            if not any(fnmatch.fnmatch(n, g) or fnmatch.fnmatch(rel, g) for g in skip):
                files.append(rel)
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], epilog="See the top of this file for details.")
    ap.add_argument("src")
    ap.add_argument("--id", required=True)
    ap.add_argument("--name")
    ap.add_argument("--version", required=True)
    ap.add_argument("--configs", default="config")
    ap.add_argument("--hardware", action="append", default=[])
    ap.add_argument("--settings")
    ap.add_argument("--keep", action="append", default=[])
    ap.add_argument("--dmd-rom")
    ap.add_argument("--pup-rom")
    ap.add_argument("--pup-manifest")
    ap.add_argument("--arch", default="all")
    ap.add_argument("--platform-addon", action="append", default=[])
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--description", default="")
    ap.add_argument("--icon")
    ap.add_argument("-o", "--output-dir", default=".")
    a = ap.parse_args()
    src = os.path.abspath(a.src)
    if not os.path.isdir(src):
        die(f"{a.src}: not a folder")
    if not ID_RE.match(a.id):
        die("--id: lowercase letters, digits, . _ - (at most 64)")
    if not VERSION_RE.match(a.version):
        die("--version: letters, digits, . _ + - (at most 64)")
    if a.arch not in ("all", "arm64", "x86_64", "arm64+x86_64"):
        die("--arch: all, arm64, x86_64 or arm64+x86_64")
    keep = [inside(k, "--keep") for k in a.keep]
    sets = hardware_sets(a.hardware)
    addons = a.platform_addon or ["gde_gozen", "mpf-gmc"]
    configs = [c.strip() for c in a.configs.split(",") if c.strip()]

    bundle = {
        "format": K.FORMAT, "id": a.id, "name": a.name or a.id, "version": a.version, "description": a.description,
        "target": {"os": "linux", "arch": a.arch},
        "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "game_dir": "game",
        "mpf": {"configs": configs, **({"hardware": sets} if sets else {})},
        "platform_addons": addons,
        "keep_on_update": ["game/" + k for k in keep],
    }
    if a.dmd_rom:
        bundle["dmd"] = {"rom": a.dmd_rom}
    if a.pup_rom or a.pup_manifest:
        if not (a.pup_rom and a.pup_manifest):
            die("--pup-rom and --pup-manifest go together")
        bundle["pup"] = {"rom": a.pup_rom, "manifest": "game/" + inside(a.pup_manifest, "--pup-manifest")}
    if a.icon:
        bundle["icon"] = "game/" + inside(a.icon, "--icon")
    schema = settings_schema(src, a.settings and inside(a.settings, "--settings"), sets)
    if schema:
        bundle["settings"] = {"schema": SETTINGS}

    skip = ALWAYS + ["addons/" + n for n in addons] + a.exclude
    files = collect(src, skip)
    if not files:
        die("nothing to pack")
    if not any(f.startswith(".godot/") for f in files):
        print("warning: no .godot/ import in the folder: run `godot --headless --import` in it first, or the machine imports at "
              "its first start", file=sys.stderr)
    with tempfile.TemporaryDirectory() as view:              # the bundle as the platform sees it, without copying the game
        os.symlink(src, os.path.join(view, "game"))
        if schema:
            with open(os.path.join(view, SETTINGS), "w", encoding="utf-8") as f:
                json.dump(schema, f)
        bad = K.problems(bundle, view)
    if bad:
        die("the bundle would break the format 2 contract:\n  " + "\n  ".join(bad))

    top = f"{a.id}@{a.version}"
    extra = {"bundle.json": json.dumps(bundle, indent=2) + "\n"}
    if schema:
        extra[SETTINGS] = json.dumps(schema, indent=2) + "\n"
    sums = "".join(f"{hashlib.sha256(v.encode()).hexdigest()}  {k}\n" for k, v in extra.items() if k != "bundle.json")
    sums += "".join(f"{sha256(os.path.join(src, r))}  game/{r}\n" for r in files)
    extra["SHA256SUMS"] = sums
    os.makedirs(a.output_dir, exist_ok=True)
    out = os.path.join(a.output_dir, top + ".tar.xz")
    with tarfile.open(out, "w:xz") as t:
        for k in ("bundle.json", SETTINGS, "SHA256SUMS"):
            if k in extra:
                data = extra[k].encode()
                i = tarfile.TarInfo(f"{top}/{k}")
                i.size, i.mode = len(data), 0o644
                t.addfile(i, io.BytesIO(data))
        for r in files:
            p = os.path.join(src, r)
            i = t.gettarinfo(p, f"{top}/game/{r}")
            i.uid = i.gid = 0
            i.uname = i.gname = "root"
            if i.isfile():
                with open(p, "rb") as f:
                    t.addfile(i, f)
            else:
                t.addfile(i)
    with open(out + ".sha256", "w") as f:
        f.write(f"{sha256(out)}  {os.path.basename(out)}\n")
    print(f"{out}: {len(files)} files, {os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    main()
