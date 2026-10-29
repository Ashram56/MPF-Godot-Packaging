#!/usr/bin/env python3
"""Put game bundles and PuP Packs into an image before it is flashed.

    inject_image.py IMAGE [--bundle FILE]... [--pup FILE[:GAME]]... [-o OUT] [--extra-mb N]

IMAGE is a raw disk image (`.img`, or `.img.xz` / `.img.gz`, unpacked first). The tool copies it, appends one partition labelled
`mpfdata` (the read/write data partition of common/readonly) holding an `inbox/` folder with the files, and leaves the rest of the
image untouched. At the first boot `mpf-persist` mounts that partition and grows it to the end of the card, and
`mpf-netconfig-inbox.service` installs the files, exactly as if they had been uploaded on the page (the same checks). Nothing needs
root, a loop device or a network; it needs `sfdisk` and `mke2fs` (e2fsprogs).

  --bundle FILE      a game bundle (`*.tar.xz` with a bundle.json: common/games/README.md). Give several for several games or
                     versions; the first one becomes the active game, the others wait to be chosen on the page.
  --pup FILE[:GAME]  a PuP Pack zip. `:GAME` names the game it is for (`my-game` = its active or newest version, `my-game@1.4` = that
                     version); without it the pack goes to the active game.
  --extra-mb N       room left free in the partition (default 128): it is grown to the whole card at the first boot anyway.
  -o OUT             output image (default IMAGE with `-games` before the extension). `--in-place` changes IMAGE itself.

Raspberry Pi 4, x86 (the USB stick image: its installer copies the games to the disk it installs on). A Jetson is flashed from NVIDIA's
tools, not from a disk image: copy the files to its inbox over SSH instead (`/data/inbox`, or the page).
"""
import argparse
import gzip
import hashlib
import json
import lzma
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

LABEL = "mpfdata"
MB = 1 << 20
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*(@[A-Za-z0-9._-]+)?$")


def die(msg):
    sys.exit(f"inject_image: {msg}")


def need(tool):
    for d in (os.environ.get("PATH", "") + ":/sbin:/usr/sbin").split(":"):
        if os.access(os.path.join(d, tool), os.X_OK):
            return os.path.join(d, tool)
    die(f"{tool} not found (apt install e2fsprogs fdisk)")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def unpack(src, dst):
    """Copy IMAGE to DST (sparse when possible), decompressing .xz and .gz."""
    opener = lzma.open if src.endswith(".xz") else gzip.open if src.endswith(".gz") else None
    if opener is None:
        shutil.copyfile(src, dst)
        return
    with opener(src, "rb") as i, open(dst, "wb") as o:
        shutil.copyfileobj(i, o, 1 << 20)


def table(image):
    out = subprocess.run([need("sfdisk"), "-J", image], capture_output=True, text=True)
    if out.returncode:
        die(f"{image} has no partition table that sfdisk can read: {out.stderr.strip()}")
    return json.loads(out.stdout)["partitiontable"]


def check_bundle(path):
    """Cheap look before the image is touched: a tar.xz with a readable bundle.json at its top (the board checks it again)."""
    try:
        with tarfile.open(path, "r:*") as t:
            for m in t:
                if m.isfile() and m.name.lstrip("./").count("/") <= 1 and os.path.basename(m.name) == "bundle.json":
                    return json.load(t.extractfile(m))
    except (tarfile.TarError, OSError, ValueError) as e:
        die(f"{path}: not a readable bundle ({e})")
    die(f"{path}: no bundle.json inside (is it a bundle? common/games/README.md)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], epilog="See the top of this file for details.")
    ap.add_argument("image")
    ap.add_argument("--bundle", action="append", default=[])
    ap.add_argument("--pup", action="append", default=[])
    ap.add_argument("--extra-mb", type=int, default=128)
    ap.add_argument("-o", "--output")
    ap.add_argument("--in-place", action="store_true")
    a = ap.parse_args()
    if not a.bundle and not a.pup:
        die("nothing to add: give --bundle and/or --pup")
    for f in a.bundle + [p.rsplit(":", 1)[0] if ":" in p and not os.path.exists(p) else p for p in a.pup]:
        if not os.path.isfile(f):
            die(f"{f}: no such file")
    mke2fs = need("mke2fs")
    sfdisk = need("sfdisk")

    out = a.image if a.in_place else (a.output or re.sub(r"(\.img)?(\.xz|\.gz)?$", "-games.img", a.image, count=1))
    if a.in_place and a.image.endswith((".xz", ".gz")):
        die("--in-place needs a raw .img")
    if not a.in_place:
        if os.path.exists(out):
            die(f"{out} exists already")
        print(f"copying {a.image} -> {out}")
        unpack(a.image, out)

    stage = tempfile.mkdtemp(prefix="mpf-inject-")
    try:
        inbox = os.path.join(stage, "inbox")
        os.makedirs(inbox)
        for n, path in enumerate(a.bundle, 1):
            meta = check_bundle(path)
            name = f"{n:02d}_{re.sub(r'[^A-Za-z0-9._@+-]', '_', os.path.basename(path))}"
            dest = os.path.join(inbox, name)
            shutil.copyfile(path, dest)
            with open(dest + ".sha256", "w") as f:
                f.write(f"{sha256(dest)}  {name}\n")
            print(f"bundle {os.path.basename(path)} {meta.get('id', '')} {meta.get('version', '')}".rstrip())
        for spec in a.pup:
            path, game = (spec, None)
            if ":" in spec and not os.path.exists(spec):
                path, game = spec.rsplit(":", 1)
            if game is not None and not ID_RE.match(game):
                die(f"{game!r} is not a game id (my-game, or my-game@1.4)")
            name = f"{game}.pup.zip" if game else os.path.basename(path)
            if not name.lower().endswith(".zip"):
                name += ".zip"
            if game is None and name.endswith(".pup.zip"):
                name = name[: -len(".pup.zip")] + ".zip"    # without a game named it goes to the active game
            shutil.copyfile(path, os.path.join(inbox, name))
            print(f"pack {os.path.basename(path)} -> {game or 'the active game'}")

        payload = sum(os.path.getsize(os.path.join(inbox, n)) for n in os.listdir(inbox))
        size = ((payload * 11 // 10 + a.extra_mb * MB + 63 * MB) // MB + 1) * MB    # ext4 journal and metadata take about 64 MB
        t = table(out)
        if any(str(p.get("name", "")).lower() == LABEL for p in t.get("partitions", [])):
            die(f"{out} has a {LABEL} partition already: start again from the original image")
        if t["label"] == "dos" and len(t["partitions"]) >= 4:
            die("the image uses the four primary partitions of its table: there is no room for the data partition")
        with open(out, "r+b") as f:
            f.seek(0, 2)
            start_bytes = f.tell()
            f.truncate(start_bytes + size + MB)    # +1 MB: the backup of a GPT lives at the end
        line = f'size={size // 512}, type=L, name="{LABEL}"\n' if t["label"] == "gpt" else f"size={size // 512}, type=83\n"
        r = subprocess.run([sfdisk, "--append", "--no-reread", "--no-tell-kernel", "-q", out], input=line, capture_output=True, text=True)
        if r.returncode:
            die(f"sfdisk could not add the partition: {r.stderr.strip()}")
        parts = table(out)["partitions"]
        new = max(parts, key=lambda p: p["start"])
        offset, blocks = new["start"] * 512, new["size"] * 512 // 4096
        r = subprocess.run([mke2fs, "-q", "-t", "ext4", "-b", "4096", "-L", LABEL, "-m", "0", "-E", f"offset={offset}", "-d", stage, out, str(blocks)],
                           capture_output=True, text=True)
        if r.returncode:
            die(f"mke2fs failed: {r.stderr.strip()}")
        print(f"{out}: data partition {size // MB} MB added with {len(os.listdir(inbox))} file(s); flash it as usual")
    finally:
        shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    main()
