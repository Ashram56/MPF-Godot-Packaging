#!/usr/bin/env python3
"""Decode a PinUP Player pack (PuP Pack) for a game that runs without PinMAME: what fires what, and which
display effect each DMD capture is.

    python tools/pup/pup_decode.py decode PACK OUT.json
    python tools/pup/pup_decode.py match PACK OUT.md --frames 'media/dmd/deff_*/*.gif' \\
        [--id-regex 'deff_(\\d+)'] [--owners owners.csv] [--event 'game_deff_{id}'] [--map trigger_map.yaml]

PACK is the pack folder (the one holding triggers.pup) or the zip its author publishes (the folder holding
triggers.pup is found at any depth). Needs Pillow for the captures (`pip install pillow`).

- decode: screens.pup, playlists.pup (with each playlist's files), triggers.pup (each Trigger expression parsed
  into terms) and every PupCapture/<n>.bmp (its purple rectangle and lit dots), as one JSON file.
- match: compares each capture with every 128x32 frame of the --frames files (GIF or PNG, every frame of an
  animation), the way PinUP Player compares it with PinMAME's DMD, and writes a report: per capture the trigger
  rows using it, the best score (intersection over union of lit dots inside the rectangle) and the effect ids
  with a frame within 0.5 % of the best (2 % under 97 %). An effect id comes from --id-regex on the frame's path,
  and from --owners (a CSV with columns pattern,id: every frame whose path matches the regex pattern also
  belongs to that id; for shared library animations that several effects play).
  --map writes a starting trigger map (YAML: dmd / switches / override) with --event naming each effect's event.

The method and what the numbers mean: knowledge/pup_pack_format.md; the agent: agents/pup_pack.md.
"""
import argparse
import csv
import glob
import io
import json
import os
import re
import sys
import zipfile

PURPLE = (253, 0, 253)       # the capture's rectangle (and ignored) pixels
LIT = 9                      # a dot is lit when its red (or grey) value is at least this
W, H = 128, 32
TERM = re.compile(r"^([A-Z])(\d+)(?:=(\d+))?$")
MEDIA = {"video": (".mp4", ".m4v", ".mov", ".avi", ".f4v", ".mkv", ".webm"),
         "audio": (".mp3", ".ogg", ".wav"), "picture": (".png", ".jpg", ".jpeg", ".gif", ".bmp")}


# ------------------------------------------------------------------ the pack, from a folder or a zip

class Pack:
    """Read-only access to a pack folder or the pack folder inside a zip."""

    def __init__(self, path):
        self.path = path
        if os.path.isdir(path):
            self.zip, self.prefix = None, ""
            names = []
            for root, _dirs, files in os.walk(path):
                for f in files:
                    names.append(os.path.relpath(os.path.join(root, f), path).replace(os.sep, "/"))
            self.names = sorted(names)
        else:
            self.zip = zipfile.ZipFile(path)
            all_names = [n.replace("\\", "/") for n in self.zip.namelist() if not n.endswith("/")]
            tops = sorted((n for n in all_names if n.rsplit("/", 1)[-1].lower() == "triggers.pup"),
                          key=lambda n: n.count("/"))
            if not tops:
                raise SystemExit("{}: no triggers.pup, not a PuP Pack".format(path))
            self.prefix = tops[0][:-len("triggers.pup")]
            self._raw = {n.replace("\\", "/"): n for n in self.zip.namelist()}
            self.names = sorted(n[len(self.prefix):] for n in all_names if n.startswith(self.prefix))
        self._lower = {n.lower(): n for n in self.names}

    def find(self, name):
        """The pack's own spelling of a relative name (PinUP Player runs on Windows: case does not matter)."""
        return self._lower.get(name.replace("\\", "/").lower())

    def read(self, name):
        real = self.find(name)
        if real is None:
            return None
        if self.zip:
            return self.zip.read(self._raw[self.prefix + real])
        with open(os.path.join(self.path, real), "rb") as f:
            return f.read()

    def csv(self, name):
        data = self.read(name)
        if data is None:
            return []
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig", errors="replace"))))
        if not rows:
            return []
        head = [h.strip() for h in rows[0]]
        return [dict(zip(head, (c.strip() for c in r))) for r in rows[1:] if any(c.strip() for c in r)]


def num(value, kind=int):
    try:
        return kind(float(value)) if kind is int else kind(value)
    except (TypeError, ValueError):
        return None


def terms(expression):
    """'D14' -> [['D', 14, None]]; 'W11=1,L35=1' -> [['W', 11, 1], ['L', 35, 1]]; unknown parts are kept as
    ['?', text, None] so nothing is silently lost."""
    out = []
    for part in expression.replace(" ", "").split(","):
        if not part:
            continue
        m = TERM.match(part.upper())
        out.append([m.group(1), int(m.group(2)), num(m.group(3))] if m else ["?", part, None])
    return out


# ------------------------------------------------------------------ captures and frames as bit sets

def pixels(image):
    """The pixels of an L or RGB image, as ints or tuples."""
    data, n = image.tobytes(), len(image.getbands())
    return list(data) if n == 1 else [tuple(data[i:i + n]) for i in range(0, len(data), n)]


def bits(pixels, test):
    value = 0
    for i, px in enumerate(pixels):
        if test(px):
            value |= 1 << i
    return value


def capture(data):
    """A PupCapture BMP (bytes) -> {rect: [x0, y0, x1, y1], mask, lit} (mask/lit: int, bit y*128+x), or None
    when it is not 128x32. A capture with no purple rectangle compares the whole frame (Transformers: 1, 8, 9)."""
    from PIL import Image
    image = Image.open(io.BytesIO(data)).convert("RGB")
    if image.size != (W, H):
        return None
    px = pixels(image)
    purple = bits(px, lambda p: p == PURPLE)
    if not purple:
        mask = (1 << (W * H)) - 1
        return {"rect": [0, 0, W - 1, H - 1], "mask": mask, "lit": bits(px, lambda p: p[0] >= LIT)}
    xs = [i % W for i in range(W * H) if purple >> i & 1]
    ys = [i // W for i in range(W * H) if purple >> i & 1]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    mask = 0
    for y in range(y0, y1 + 1):
        mask |= ((1 << (x1 - x0 + 1)) - 1) << (y * W + x0)
    mask &= ~purple
    lit = bits(px, lambda p: p != PURPLE and p[0] >= LIT) & mask
    return {"rect": [x0, y0, x1, y1], "mask": mask, "lit": lit}


def frames(path):
    """Lit-dot bit sets of every 128x32 frame of a GIF/PNG (an animation gives one per frame). A capture scaled by
    a whole factor (T2's 256x64 GIFs) is brought back to 128x32, one sample per dot."""
    from PIL import Image, ImageSequence
    image = Image.open(path)
    w, h = image.size
    if w % W or h % H or w // W != h // H:
        return
    for frame in ImageSequence.Iterator(image):
        frame = frame.convert("L")
        if (w, h) != (W, H):
            frame = frame.resize((W, H), Image.NEAREST)
        yield bits(pixels(frame), lambda v: v >= LIT)


def score(frame, cap):
    """Intersection over union of the lit dots inside the capture's rectangle (1.0 = PinUP Player fires)."""
    region = frame & cap["mask"]
    union = bin(region | cap["lit"]).count("1")
    return bin(region & cap["lit"]).count("1") / union if union else 1.0


def rows_text(value):
    """A bit set as 128-character rows of '#' and '.', for the JSON."""
    return ["".join("#" if value >> (y * W + x) & 1 else "." for x in range(W)) for y in range(H)]


# ------------------------------------------------------------------ decode

def decode(pack):
    screens = [{"num": num(r.get("ScreenNum")), "name": r.get("ScreenDes", ""), "mode": r.get("Active", ""),
                "background": r.get("PlayList", "") + ("/" + r["PlayFile"] if r.get("PlayFile") else ""),
                "loop": r.get("Loopit", ""), "row": r} for r in pack.csv("screens.pup")]
    playlists = []
    for r in pack.csv("playlists.pup"):
        folder = r.get("Folder", "")
        files = sorted(n.split("/", 1)[1] for n in pack.names if "/" in n and n.split("/", 1)[0].lower()
                       == folder.lower() and "/" not in n.split("/", 1)[1])
        playlists.append({"folder": folder, "alpha_sort": r.get("AlphaSort", "") == "1",
                          "rest_seconds": num(r.get("RestSeconds"), float), "volume": num(r.get("Volume")),
                          "priority": num(r.get("Priority")), "files": files, "row": r})
    triggers = []
    for r in pack.csv("triggers.pup"):
        if num(r.get("ID")) is None:
            continue
        expression = r.get("Trigger", "")
        triggers.append({"id": num(r.get("ID")), "active": r.get("Active", "1") == "1",
                         "descript": r.get("Descript", ""), "trigger": expression, "terms": terms(expression),
                         "screen": num(r.get("ScreenNum")), "playlist": r.get("PlayList", ""),
                         "file": r.get("PlayFile", ""), "volume": num(r.get("Volume")),
                         "priority": num(r.get("Priority")), "length": num(r.get("Length"), float),
                         "rest_seconds": num(r.get("RestSeconds"), float), "loop": r.get("Loop", "")})
    captures = {}
    for name in pack.names:
        m = re.match(r"(?i)^pupcapture/(\d+)\.bmp$", name)
        if not m:
            continue
        cap = capture(pack.read(name))
        if cap:
            captures[int(m.group(1))] = {"rect": cap["rect"], "lit_dots": bin(cap["lit"]).count("1"),
                                         "dots": rows_text(cap["lit"]), "mask": rows_text(cap["mask"])}
    used = {}
    for t in triggers:
        for kind, n, _ in t["terms"]:
            used.setdefault(kind, {}).setdefault(str(n), []).append(t["id"])
    kinds = {kind: len(v) for kind, v in used.items()}
    return {"pack": os.path.basename(os.path.normpath(pack.path)), "screens": screens, "playlists": playlists,
            "triggers": triggers, "captures": {str(k): captures[k] for k in sorted(captures)}, "used": used,
            "summary": {"triggers": len(triggers), "active": sum(t["active"] for t in triggers),
                        "captures": len(captures), "codes": kinds,
                        "unused_captures": sorted(k for k in captures if str(k) not in used.get("D", {})),
                        "media": {k: sum(n.lower().endswith(ext) for n in pack.names) for k, ext in MEDIA.items()}}}


# ------------------------------------------------------------------ match

KEEP_ID_TEXT = False


def effect_id(text):
    """The effect id from a frame's path: a number (Tron's deff_25), or the text as it is with --id-text (T2's
    hex ids, deff04: a number would lose the leading zero and the hex)."""
    if KEEP_ID_TEXT:
        return str(text)
    return int(text) if str(text).isdigit() else str(text)


def match(pack, patterns, id_regex, owners=(), floor_high=0.005, floor_low=0.02):
    """[(n, rect, rows, best, ids, best_label)] for every capture of the pack. owners: [(regex, id)]."""
    regex = re.compile(id_regex)
    recorded = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern, recursive=True)):
            rel = path.replace(os.sep, "/")
            m = regex.search(rel)
            ids = {effect_id(m.group(1))} if m else set()
            ids |= {effect_id(i) for rx, i in owners if re.search(rx, rel)}
            for i, frame in enumerate(frames(path)):
                recorded.append((ids, "{}#{}".format(path, i), frame))
    if not recorded:
        raise SystemExit("no 128x32 frames in {}".format(" ".join(patterns)))
    data = decode(pack)
    used = data["used"].get("D", {})
    out = []
    for name in pack.names:
        m = re.match(r"(?i)^pupcapture/(\d+)\.bmp$", name)
        cap = capture(pack.read(name)) if m else None
        if not cap:
            continue
        scored = [(score(frame, cap), owners_, label) for owners_, label, frame in recorded]
        best = max(s for s, _, _ in scored)
        floor = best - (floor_high if best >= 0.97 else floor_low)
        ids = sorted({o for s, os_, _ in scored if s >= floor for o in os_}, key=lambda v: (str(type(v)), v))
        label = max(scored, key=lambda s: s[0])[2]
        n = int(m.group(1))
        out.append((n, cap["rect"], used.get(str(n), []), best, ids, label))
    return sorted(out), data, len(recorded)


def write_map(path, matched, data, event):
    lines = ["# PuP trigger map written by tools/pup/pup_decode.py match: check every line, then keep it by hand.",
             "# dmd: capture n (trigger D<n>) -> the game events that show it; switches: W<n> -> switch name;",
             "# override: triggers.pup row ID -> events (rows whose expression the game cannot evaluate).", "dmd:"]
    for n, _rect, rows, best, ids, _label in matched:
        events = ", ".join(event.format(id=i) for i in ids) if best >= 0.9 else ""
        lines.append("  {}: [{}]{}  # {:.0%}{}".format(n, events, "" if events else "   ", best,
                                                      "" if rows else ", no trigger row uses it"))
    switches = sorted(int(k) for k in data["used"].get("W", {}))
    lines.append("switches:" + ("" if switches else " {}"))
    lines += ["  {}: sw{}       # rename to the game's switch name".format(n, n) for n in switches]
    multi = [t for t in data["triggers"] if len(t["terms"]) > 1 or any(k not in "DW" for k, _, _ in t["terms"])]
    lines.append("override:" + ("" if multi else " {}"))
    lines += ["  {}: []   # {} {}".format(t["id"], t["trigger"], t["descript"]) for t in multi]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decode", help="the pack as JSON")
    d.add_argument("pack")
    d.add_argument("out")
    m = sub.add_parser("match", help="captures against the game's DMD frames")
    m.add_argument("pack")
    m.add_argument("out")
    m.add_argument("--frames", action="append", required=True, help="glob of 128x32 GIF/PNG files (repeatable)")
    m.add_argument("--id-regex", default=r"deff_(\d+)", help="effect id from a frame's path (group 1)")
    m.add_argument("--owners", help="CSV with columns pattern,id: frames whose path matches also belong to id")
    m.add_argument("--event", default="deff_{id}", help="event name for an effect id, for --map")
    m.add_argument("--map", help="also write a starting trigger map (YAML) here")
    m.add_argument("--id-text", action="store_true",
                   help="keep the id as matched (hex, leading zeros: T2's deff04 -> t2_deff_04), not as a number")
    args = p.parse_args(argv)
    pack = Pack(args.pack)
    global KEEP_ID_TEXT
    KEEP_ID_TEXT = bool(getattr(args, "id_text", False))
    if args.cmd == "decode":
        data = decode(pack)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        print(json.dumps(data["summary"]))
        return 0
    owners = []
    if args.owners:
        with open(args.owners, encoding="utf-8-sig", newline="") as f:
            owners = [(r["pattern"], r["id"]) for r in csv.DictReader(f)]
    matched, data, count = match(pack, args.frames, args.id_regex, owners)
    lines = ["# PuP captures against the game's DMD frames", "",
             "{} captures, {} frames. *score*: intersection over union of lit dots inside the capture's rectangle "
             "with the best frame (100% = PinUP Player would fire). *ids*: effects with a frame within 0.5 % of the "
             "best (2 % under 97 %).".format(len(matched), count), "",
             "| D | rows | rectangle | score | ids | best frame |", "|---|---|---|---|---|---|"]
    for n, rect, rows, best, ids, label in matched:
        lines.append("| {} | {} | {},{}-{},{} | {:.0%} | {} | `{}` |".format(
            n, " ".join(map(str, rows)) or "-", *rect, best, " ".join(map(str, ids)) or "-", label))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    if args.map:
        write_map(args.map, matched, data, args.event)
    weak = sum(1 for _, _, rows, best, _, _ in matched if rows and best < 0.9)
    print("{} captures matched, {} used by a trigger row score under 90 %: {}".format(len(matched), weak, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
