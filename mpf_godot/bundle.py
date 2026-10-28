"""Build a game bundle: the game as it runs (generated MPF config, media, sounds, fonts, Godot import already
made), with no binary. platforms/game-bundles.md says why; the game describes itself in a small JSON spec.

    python -m mpf_godot bundle SPEC.json --target all --out DIR [--version V] [--no-archive]

SPEC.json (paths relative to the spec's folder, the game's repository root):
  id, name                     bundle id (the archive and its top folder) and display name
  game_dir                     the Godot project folder (default "game"); project.godot is in it
  git_tracked                  folders whose git-tracked files are copied (default [game_dir])
  git_exclude                  path prefixes left out of those (default [game_dir + "/addons/"]: add-ons come from the platform)
  copy                         extra files/folders copied as they are (generated config, media, sounds, scripts, assets ...)
  never                        paths that must not be in the tree (cabinet data); the build stops if one is
  never_names                  file name patterns that must not be in it (e.g. "*.local.cfg")
  import_seed                  [{"dir", "template", "skip_prefixes"}]: write the .import file `template` (a file of
                               the game) next to every .png under dir that the game does not track
  platform_addons              ["gde_gozen"]: installed by the platform for the machine, never packed
  run, options, requires,      copied into bundle.json as they are
  keep_on_update, extra
Texture formats follow the target: arm64 -> etc2, x86_64 -> s3tc, all -> both (imported offline, one archive for every machine).
"""
import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mpf_godot import fsutil  # noqa: E402
from mpf_godot import toolchain as tc  # noqa: E402

FORMAT = 1
FORMATS = {"arm64": "etc2", "x86_64": "s3tc", "all": "both"}
ARCH = {"arm64": "arm64", "x86_64": "x86_64", "all": "arm64+x86_64"}
DROP = {"etc2": ("s3tc", "bptc"), "s3tc": ("etc2", "astc"), "both": ()}
SKIP_NAMES = {"__pycache__", ".DS_Store", ".git"}
SKIP_SUFFIX = (".import", ".pyc", ".part", ".lock")


def say(text):
    print(text, flush=True)


def git(root, *args):
    r = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def skip(rel):
    return any(p in SKIP_NAMES for p in rel.replace("\\", "/").split("/")) or rel.endswith(SKIP_SUFFIX)


def copy_path(root, rel, dst_root):
    """A file or a folder (minus skipped names); returns the number of files copied."""
    src = os.path.join(root, rel)
    if not os.path.exists(src):
        return 0
    files = [rel]
    if os.path.isdir(src):
        files = []
        for base, dirs, names in os.walk(src):
            dirs[:] = [d for d in dirs if d not in SKIP_NAMES]
            files += [os.path.relpath(os.path.join(base, n), root) for n in names]
    n = 0
    for f in files:
        if skip(f):
            continue
        dst = os.path.join(dst_root, f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(root, f), dst)
        n += 1
    return n


def stage_tree(root, spec, stage):
    n = 0
    game = spec.get("game_dir", "game")
    exclude = tuple(spec.get("git_exclude", [game + "/addons/"]))
    for folder in spec.get("git_tracked", [game]):
        for p in git(root, "ls-files", "-z", folder).split("\0"):
            if p and not p.startswith(exclude):
                n += copy_path(root, p, stage)
    for rel in spec.get("copy", []):
        n += copy_path(root, rel, stage)
    return n


def forbidden(spec, stage):
    found = [rel for rel in spec.get("never", []) if os.path.exists(os.path.join(stage, rel))]
    pats = spec.get("never_names", [])
    for base, _, files in os.walk(stage):
        for name in files:
            if any(fnmatch.fnmatch(name, p) for p in pats):
                found.append(os.path.relpath(os.path.join(base, name), stage))
    return found


def seed_imports(root, spec, stage):
    n = 0
    for s in spec.get("import_seed", []):
        with open(os.path.join(root, s["template"]), encoding="utf-8") as f:
            template = f.read()
        top = os.path.join(stage, s["dir"])
        for base, _, files in os.walk(top):
            for name in sorted(files):
                if name.endswith(".png") and not name.startswith(tuple(s.get("skip_prefixes", ()))):
                    with open(os.path.join(base, name + ".import"), "w", encoding="utf-8", newline="\n") as f:
                        f.write(template)
                    n += 1
    return n


def set_texture_formats(project, formats):
    """Godot imports the VRAM-compressed variants this project setting names (default: S3TC/BPTC only)."""
    with open(project, encoding="utf-8") as f:
        text = f.read()
    lines = ["textures/vram_compression/import_etc2_astc=" + ("true" if formats in ("etc2", "both") else "false"),
             "textures/vram_compression/import_s3tc_bptc=" + ("true" if formats in ("s3tc", "both") else "false")]
    text = re.sub(r"^textures/vram_compression/import_\w+=.*\n", "", text, flags=re.M)
    if "[rendering]\n" not in text:
        raise SystemExit("no [rendering] section in " + project)
    with open(project, "w", encoding="utf-8") as f:
        f.write(text.replace("[rendering]\n", "[rendering]\n\n" + "\n".join(lines) + "\n", 1))


def godot_import(game, godot):
    for _ in range(2):          # the first pass can report add-on icon errors; the second is clean
        subprocess.run([godot, "--headless", "--path", game, "--import"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=1800)
    if not os.path.isdir(os.path.join(game, ".godot", "imported")):
        raise SystemExit("the Godot import made no .godot/imported")


def prune_formats(game, formats):
    """Godot always imports the variant its host prefers whatever the setting says: take the formats the target
    cannot use out of every .import and delete their .ctex files."""
    drop = DROP[formats]
    removed = 0
    if not drop:
        return 0
    for base, _, files in os.walk(game):
        if ".godot" in os.path.relpath(base, game).split(os.sep):
            continue
        for name in files:
            if not name.endswith(".import"):
                continue
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if "path." not in text:
                continue
            out = []
            for line in text.split("\n"):
                m = re.match(r"path\.(\w+)=", line)
                if m and m.group(1) in drop:
                    continue
                if line.startswith("dest_files="):
                    items = [i for i in re.findall(r'"([^"]*)"', line)
                             if not any(i.endswith(".{}.ctex".format(d)) for d in drop)]
                    line = "dest_files=[{}]".format(", ".join('"{}"'.format(i) for i in items))
                if line.startswith('"imported_formats"'):
                    gone = {"s3tc": "s3tc_bptc", "bptc": "s3tc_bptc", "etc2": "etc2_astc", "astc": "etc2_astc"}
                    items = [i for i in re.findall(r'"(\w+)"', line.split(":", 1)[1]) if i not in {gone[d] for d in drop}]
                    line = '"imported_formats": [{}],'.format(", ".join('"{}"'.format(i) for i in items))
                out.append(line)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(out))
    imported = os.path.join(game, ".godot", "imported")
    for name in os.listdir(imported):
        if any(name.endswith(".{}.ctex".format(d)) for d in drop):
            os.remove(os.path.join(imported, name))
            removed += 1
    return removed


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_sums(stage):
    lines = []
    for base, dirs, files in os.walk(stage):
        dirs.sort()
        for name in files:
            rel = os.path.relpath(os.path.join(base, name), stage).replace(os.sep, "/")
            if rel != "SHA256SUMS":
                lines.append("{}  {}\n".format(sha256(os.path.join(base, name)), rel))
    lines.sort(key=lambda l: l.split("  ", 1)[1])
    with open(os.path.join(stage, "SHA256SUMS"), "w", encoding="utf-8") as f:
        f.writelines(lines)
    return len(lines)


def manifest(root, spec, version, target):
    m = {"format": FORMAT, "id": spec["id"], "name": spec.get("name", spec["id"]), "version": version,
         "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "target": {"os": "linux", "arch": ARCH[target], "texture_formats": FORMATS[target]},
         "source": {"game_commit": git(root, "rev-parse", "HEAD")},
         "requires": dict(spec.get("requires", {}), godot=tc.GODOT_VERSION),
         "platform_addons": list(spec.get("platform_addons", [])),
         "keep_on_update": list(spec.get("keep_on_update", []))}
    for k in ("run", "options"):
        if k in spec:
            m[k] = spec[k]
    m.update(spec.get("extra", {}))
    return m


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m mpf_godot bundle", description=__doc__.split("\n\n")[0])
    p.add_argument("spec", help="the game's bundle spec (JSON); its folder is the game's repository root")
    p.add_argument("--target", choices=sorted(FORMATS), default="all")
    p.add_argument("--version", help="default: the date and the short commit")
    p.add_argument("--out", default="dist")
    p.add_argument("--no-archive", action="store_true")
    args = p.parse_args(argv)
    spec_path = os.path.abspath(args.spec)
    root = os.path.dirname(spec_path)
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    game_rel = spec.get("game_dir", "game")
    version = args.version or "{}-{}".format(datetime.date.today().strftime("%Y.%m.%d"),
                                              git(root, "rev-parse", "--short", "HEAD") or "nogit")
    formats = FORMATS[args.target]
    out = os.path.abspath(args.out)
    parent = os.path.join(out, "stage")
    stage = os.path.join(parent, spec["id"])
    if os.path.isdir(parent):
        fsutil.remove_dir(parent)
    os.makedirs(stage)
    say("== staging ({}, textures {})".format(args.target, formats))
    say("   {} files".format(stage_tree(root, spec, stage)))
    bad = forbidden(spec, stage)
    if bad:
        raise SystemExit("cabinet data in the bundle: " + ", ".join(bad))
    game = os.path.join(stage, game_rel)
    say("== Godot import: {} .import files seeded".format(seed_imports(root, spec, stage)))
    set_texture_formats(os.path.join(game, "project.godot"), formats)
    godot_import(game, tc.godot_path())
    say("   dropped {} texture files the target cannot use".format(prune_formats(game, formats)))
    for rel in spec.get("never", []):          # the import itself may have made some (.godot is not cabinet data)
        if rel != game_rel + "/.godot" and os.path.exists(os.path.join(stage, rel)):
            raise SystemExit("cabinet data appeared in the bundle: " + rel)
    with open(os.path.join(stage, "bundle.json"), "w", encoding="utf-8") as f:
        json.dump(manifest(root, spec, version, args.target), f, indent=2)
    say("== SHA256SUMS: {} files".format(write_sums(stage)))
    if args.no_archive:
        say("== " + stage)
        return 0
    archive = os.path.join(out, "{}-{}-linux-{}.tar.xz".format(spec["id"], version, args.target))
    subprocess.run(["tar", "-C", parent, "-cJf", archive, spec["id"]], check=True, env=dict(os.environ, XZ_OPT="-T0 -6"))
    with open(archive + ".sha256", "w") as f:
        f.write("{}  {}\n".format(sha256(archive), os.path.basename(archive)))
    fsutil.remove_dir(parent)
    say("== " + archive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
