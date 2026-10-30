#!/usr/bin/env python3
"""Put game bundles and PuP Packs into an image before it is flashed. Pure Python 3.8+, standard library only: runs as it is on
Windows, macOS and Linux, needs no root, no loop device, no extra tool and no network (nothing to install).

    inject_image.py IMAGE [--bundle FILE]... [--pup FILE[:GAME]]... [-o OUT] [--in-place]

IMAGE is a raw disk image (`.img`, or `.img.xz` / `.img.gz`, unpacked first). The tool copies it and appends one small partition
labelled `MPFSEED` (FAT32, readable by every system) holding an `inbox/` folder with the files; the rest of the image is untouched.
At the first boot `mpf-persist` (common/readonly) makes the read/write data partition in the free space of the card, copies the seed's
inbox into it once, and `mpf-netconfig-inbox.service` installs the files exactly as if they had been uploaded on the page (the same
checks). A partition table that is GPT (the x86 image) or MBR (the Raspberry Pi 4 image) is handled.

  --bundle FILE      a game bundle (`*.tar.xz` with a bundle.json: common/games/README.md). Give several for several games or
                     versions; the first one becomes the active game, the others wait to be chosen on the page.
  --pup FILE[:GAME]  a PuP Pack zip. `:GAME` names the game it is for (`my-game` = its active or newest version, `my-game@1.4` = that
                     version); without it the pack goes to the active game.
  -o OUT             output image (default IMAGE with `-games` before the extension). `--in-place` changes IMAGE itself.

A file of the seed is limited to 4 GiB (FAT32). x86: the USB stick image, whose installer copies the games to the disk it installs on.
A Jetson is flashed from NVIDIA's tools, not from a disk image: copy the files to its inbox over SSH instead (`/data/inbox`, or the page).
"""
import argparse
import gzip
import hashlib
import json
import lzma
import os
import re
import shutil
import struct
import sys
import tarfile
import tempfile
import time
import uuid
import zlib

LABEL = "MPFSEED"
MB = 1 << 20
SECTOR = 512
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*(@[A-Za-z0-9._-]+)?$")
GUID_BASIC_DATA = uuid.UUID("EBD0A0A2-B9E5-4433-87C0-68B6B72699C7")
MAX_FILE = (1 << 32) - 1


def die(msg):
    sys.exit(f"inject_image: {msg}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def unpack(src, dst):
    """Copy IMAGE to DST, decompressing .xz and .gz."""
    opener = lzma.open if src.endswith(".xz") else gzip.open if src.endswith(".gz") else None
    if opener is None:
        shutil.copyfile(src, dst)
        return
    with opener(src, "rb") as i, open(dst, "wb") as o:
        shutil.copyfileobj(i, o, 1 << 20)


# ------------------------------------------------------------------------------------------------ partition tables

def _align(n, to=2048):
    return (n + to - 1) // to * to


def add_partition_gpt(f, sectors):
    """Append a basic-data partition of SECTORS sectors after the last one of a GPT disk, grow the file, move the backup table to the
    new end. Returns the first sector."""
    f.seek(SECTOR)
    hdr = bytearray(f.read(92))
    if hdr[:8] != b"EFI PART":
        die("GPT header not found")
    hsize = struct.unpack_from("<I", hdr, 12)[0]
    old_backup = struct.unpack_from("<Q", hdr, 32)[0]
    ent_lba, nent, esize = struct.unpack_from("<QII", hdr, 72)
    f.seek(ent_lba * SECTOR)
    entries = bytearray(f.read(nent * esize))
    used_end, free = 33, None
    for i in range(nent):
        e = entries[i * esize:(i + 1) * esize]
        if e[:16] == b"\0" * 16:
            free = i if free is None else free
            continue
        first, last = struct.unpack_from("<QQ", e, 32)
        used_end = max(used_end, last + 1)
        if e[56:128].decode("utf-16-le", "ignore").rstrip("\0").upper() == LABEL:
            die(f"the image has a {LABEL} partition already: start again from the original image")
    if free is None:
        die("the GPT has no free entry")
    start = _align(used_end)
    f.seek(0, 2)
    cur = f.tell() // SECTOR
    total = max(start + sectors + 33, cur)        # the backup entries (32 sectors) and header (1 sector) end the disk
    if total > cur:
        f.truncate(total * SECTOR)
    if old_backup != total - 1:                   # the old backup is stale once the table moves: do not leave it inside the data
        f.seek((old_backup - 32) * SECTOR)
        f.write(b"\0" * 33 * SECTOR)
    e = bytearray(esize)
    e[0:16] = GUID_BASIC_DATA.bytes_le
    e[16:32] = uuid.uuid4().bytes_le
    struct.pack_into("<QQQ", e, 32, start, start + sectors - 1, 0)
    e[56:56 + 14] = LABEL.encode("utf-16-le")
    entries[free * esize:(free + 1) * esize] = e
    ecrc = zlib.crc32(bytes(entries)) & 0xFFFFFFFF
    for name, cur_lba, other_lba, elba in (("primary", 1, total - 1, 2), ("backup", total - 1, 1, total - 33)):
        h = bytearray(hdr[:hsize]) if hsize <= len(hdr) else bytearray(hdr)
        struct.pack_into("<Q", h, 24, cur_lba)
        struct.pack_into("<Q", h, 32, other_lba)
        struct.pack_into("<Q", h, 40, 34)
        struct.pack_into("<Q", h, 48, total - 34)
        struct.pack_into("<Q", h, 72, elba)
        struct.pack_into("<I", h, 88, ecrc)
        struct.pack_into("<I", h, 16, 0)
        struct.pack_into("<I", h, 16, zlib.crc32(bytes(h[:hsize])) & 0xFFFFFFFF)
        f.seek(cur_lba * SECTOR)
        f.write(bytes(h).ljust(SECTOR, b"\0"))
        f.seek(elba * SECTOR)
        f.write(bytes(entries))
    # the protective MBR covers the disk
    f.seek(446)
    pm = bytearray(f.read(16))
    if pm[4] == 0xEE:
        struct.pack_into("<I", pm, 12, min(total - 1, 0xFFFFFFFF))
        f.seek(446)
        f.write(bytes(pm))
    return start


def add_partition_mbr(f, sectors):
    f.seek(0)
    mbr = bytearray(f.read(SECTOR))
    if mbr[510:512] != b"\x55\xaa":
        die("the image has no partition table (no MBR signature)")
    slots, used_end, free = [], 2048, None
    for i in range(4):
        e = mbr[446 + 16 * i:446 + 16 * (i + 1)]
        ptype = e[4]
        start, size = struct.unpack_from("<II", e, 8)
        if ptype == 0 or size == 0:
            free = i if free is None else free
            continue
        used_end = max(used_end, start + size)
    if free is None:
        die("the image uses the four primary partitions of its table: there is no room for the seed partition")
    start = _align(used_end)
    f.seek(0, 2)
    cur = f.tell() // SECTOR
    if start + sectors > cur:
        f.truncate((start + sectors) * SECTOR)
    e = bytearray(16)
    e[4] = 0x0C                                     # FAT32 (LBA)
    e[1:4] = e[5:8] = b"\xfe\xff\xff"              # CHS out of range: LBA is used
    struct.pack_into("<II", e, 8, start, sectors)
    mbr[446 + 16 * free:446 + 16 * (free + 1)] = e
    f.seek(0)
    f.write(bytes(mbr))
    return start


def partition_table_kind(f):
    f.seek(0)
    mbr = f.read(SECTOR)
    if len(mbr) < SECTOR or mbr[510:512] != b"\x55\xaa":
        die("the image has no MBR or GPT partition table")
    return "gpt" if mbr[446 + 4] == 0xEE else "mbr"


# ------------------------------------------------------------------------------------------------ FAT32

def _short_name(name, taken):
    """An 8.3 name for NAME that is not in TAKEN: BASE~N.EXT in upper case."""
    base, dot, ext = name.rpartition(".")
    if not dot:
        base, ext = name, ""
    clean = lambda s: re.sub(r"[^A-Z0-9_$%'\-@~!#&()^{}]", "", s.upper().replace(" ", ""))
    base, ext = clean(base), clean(ext)[:3]
    n = 1
    while True:
        tail = f"~{n}"
        cand = (base[:8 - len(tail)] or "F") + tail
        short = cand.ljust(8) + ext.ljust(3)
        if short not in taken:
            taken.add(short)
            return short.encode("ascii")
        n += 1


def _lfn_entries(name, short):
    chk = 0
    for c in short:
        chk = (((chk & 1) << 7) + (chk >> 1) + c) & 0xFF
    units = name.encode("utf-16-le")
    units += b"\x00\x00" if len(name) % 13 else b""
    units = units.ljust(((len(units) + 25) // 26) * 26, b"\xff")
    chunks = [units[i:i + 26] for i in range(0, len(units), 26)]
    out = []
    for i, c in reversed(list(enumerate(chunks, 1))):
        order = i | (0x40 if i == len(chunks) else 0)
        out.append(struct.pack("<B10sBBB12sH4s", order, c[0:10], 0x0F, 0, chk, c[10:22], 0, c[22:26]))
    return out


def _fat_time(ts):
    t = time.localtime(ts)
    year = min(max(t.tm_year, 1980), 2107)
    return ((t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2),
            ((year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday)


def _dir_entry(short, attr, cluster, size, ts):
    tm, dt = _fat_time(ts)
    return struct.pack("<11sBBBHHHHHHHI", short, attr, 0, 0, tm, dt, dt, cluster >> 16, tm, dt, cluster & 0xFFFF, size)


def _dir_bytes(items, taken_start_cluster, ts, dot=None):
    """Directory content for ITEMS (name, attr, cluster, size). DOT = (own cluster, parent cluster) adds `.` and `..`."""
    out = bytearray()
    if dot:
        out += _dir_entry(b".          ", 0x10, dot[0], 0, ts) + _dir_entry(b"..         ", 0x10, dot[1], 0, ts)
    taken = set()
    for name, attr, cluster, size in items:
        short = _short_name(name, taken)
        for e in _lfn_entries(name, short):
            out += e
        out += _dir_entry(short, attr, cluster, size, ts)
    return bytes(out)


def format_fat32(f, offset, sectors, files):
    """Write a FAT32 volume of SECTORS sectors at byte OFFSET of F with one folder `inbox` holding FILES [(name, path)]."""
    ts = time.time()
    spc = 64
    while spc > 1 and (sectors // spc) < 66000:
        spc //= 2
    reserved = 32
    fat_sectors = 1
    while True:
        clusters = (sectors - reserved - 2 * fat_sectors) // spc
        need = ((clusters + 2) * 4 + SECTOR - 1) // SECTOR
        if need <= fat_sectors:
            break
        fat_sectors = need
    if clusters < 65525:
        die("the seed partition is too small for FAT32")
    csize = spc * SECTOR
    data_start = reserved + 2 * fat_sectors
    fat = bytearray((clusters + 2) * 4)
    struct.pack_into("<II", fat, 0, 0x0FFFFFF8, 0x0FFFFFFF)

    def chain(first, count):
        for i in range(count - 1):
            struct.pack_into("<I", fat, (first + i) * 4, first + i + 1)
        struct.pack_into("<I", fat, (first + count - 1) * 4, 0x0FFFFFFF)

    nxt = 2
    root_cluster = nxt
    nxt += 1                                       # the root fits in one cluster (a volume label and one entry)
    chain(root_cluster, 1)
    inbox_entries = []
    placed = []
    # dir size: each file takes up to 1 + ceil(len/13) + 1 entries, plus . and ..
    dir_bytes_max = 32 * (2 + sum(2 + (len(n) + 12) // 13 for n, _ in files))
    inbox_clusters = max(1, (dir_bytes_max + csize - 1) // csize)
    inbox_cluster = nxt
    chain(inbox_cluster, inbox_clusters)
    nxt += inbox_clusters
    for name, path in files:
        size = os.path.getsize(path)
        if size > MAX_FILE:
            die(f"{path} is over 4 GiB: FAT32 cannot hold it")
        n = max(1, (size + csize - 1) // csize) if size else 0
        first = nxt if n else 0
        if n:
            chain(first, n)
            nxt += n
        placed.append((name, path, first, size))
        inbox_entries.append((name, 0x20, first, size))
    if nxt - 2 > clusters:
        die("the seed partition is too small for its files")
    base = offset
    boot = bytearray(SECTOR)
    boot[0:3] = b"\xeb\x58\x90"
    boot[3:11] = b"MSWIN4.1"
    struct.pack_into("<HBHBHHBHHHII", boot, 11, SECTOR, spc, reserved, 2, 0, 0, 0xF8, 0, 63, 255, 0, sectors)
    struct.pack_into("<IHHIHH12sBBBI11s8s", boot, 36, fat_sectors, 0, 0, root_cluster, 1, 6, b"\0" * 12, 0x80, 0,
                     0x29, uuid.uuid4().int & 0xFFFFFFFF, LABEL.ljust(11).encode(), b"FAT32   ")
    boot[510:512] = b"\x55\xaa"
    fsinfo = bytearray(SECTOR)
    struct.pack_into("<I", fsinfo, 0, 0x41615252)
    struct.pack_into("<I", fsinfo, 484, 0x61417272)
    struct.pack_into("<II", fsinfo, 488, clusters - (nxt - 2), nxt)
    fsinfo[510:512] = b"\x55\xaa"
    f.seek(base)
    f.write(bytes(boot) + bytes(fsinfo))
    f.write(b"\0" * (4 * SECTOR))
    f.seek(base + 6 * SECTOR)
    f.write(bytes(boot) + bytes(fsinfo))
    fat_bytes = bytes(fat).ljust(fat_sectors * SECTOR, b"\0")
    f.seek(base + reserved * SECTOR)
    f.write(fat_bytes + fat_bytes)

    def at(cluster):
        return base + (data_start + (cluster - 2) * spc) * SECTOR

    root = _dir_entry(LABEL.ljust(11).encode(), 0x08, 0, 0, ts) + _dir_bytes([("inbox", 0x10, inbox_cluster, 0)], 0, ts)
    f.seek(at(root_cluster))
    f.write(root.ljust(csize, b"\0"))
    f.seek(at(inbox_cluster))
    f.write(_dir_bytes(inbox_entries, 0, ts, dot=(inbox_cluster, 0)).ljust(inbox_clusters * csize, b"\0"))
    for name, path, first, size in placed:
        if not size:
            continue
        f.seek(at(first))
        with open(path, "rb") as src:
            shutil.copyfileobj(src, f, 1 << 20)
        pad = (-size) % csize
        if pad:
            f.write(b"\0" * pad)


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
    ap.add_argument("-o", "--output")
    ap.add_argument("--in-place", action="store_true")
    a = ap.parse_args()
    if not a.bundle and not a.pup:
        die("nothing to add: give --bundle and/or --pup")
    for f in a.bundle + [p.rsplit(":", 1)[0] if ":" in p and not os.path.exists(p) else p for p in a.pup]:
        if not os.path.isfile(f):
            die(f"{f}: no such file")

    out = a.image if a.in_place else (a.output or re.sub(r"(\.img)?(\.xz|\.gz)?$", "-games.img", a.image, count=1))
    if a.in_place and a.image.endswith((".xz", ".gz")):
        die("--in-place needs a raw .img")

    stage = tempfile.mkdtemp(prefix="mpf-inject-")
    try:
        files = []          # (name on the seed, path)
        for n, path in enumerate(a.bundle, 1):
            meta = check_bundle(path)
            name = f"{n:02d}_{re.sub(r'[^A-Za-z0-9._@+-]', '_', os.path.basename(path))}"
            side = os.path.join(stage, name + ".sha256")
            with open(side, "w") as f:
                f.write(f"{sha256(path)}  {name}\n")
            files += [(name, path), (name + ".sha256", side)]
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
            files.append((name, path))
            print(f"pack {os.path.basename(path)} -> {game or 'the active game'}")
        names = [n for n, _ in files]
        if len(set(n.lower() for n in names)) != len(names):
            die("two files would have the same name on the seed (a pack for the same game twice?)")

        payload = sum(os.path.getsize(p) for _, p in files)
        # the volume must hold at least 65525 clusters: 512-byte clusters make 33 MB the smallest FAT32
        size = max(40 * MB, ((payload * 105 // 100 + 8 * MB) // MB + 1) * MB)
        sectors = size // SECTOR

        if not a.in_place:
            if os.path.exists(out):
                die(f"{out} exists already")
            print(f"copying {a.image} -> {out}")
            unpack(a.image, out)
        try:
            with open(out, "r+b") as f:
                kind = partition_table_kind(f)
                start = (add_partition_gpt if kind == "gpt" else add_partition_mbr)(f, sectors)
                print(f"{kind.upper()} table: seed partition at sector {start}, {size // MB} MB")
                format_fat32(f, start * SECTOR, sectors, files)
        except BaseException:
            if not a.in_place and os.path.exists(out):
                os.remove(out)
            raise
        print(f"{out}: seed partition {LABEL} ({size // MB} MB) added with {len(files)} file(s); flash it as usual")
    finally:
        shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    main()
