#!/usr/bin/env python3
"""Match the PuP Pack's DMD captures against the game's display effects, and check the trigger map.

    python scripts/pup_captures.py            # writes docs/pup_captures.md, exits 1 when the map disagrees

In Visual Pinball, PinUP Player fires D<n> when the pixels inside the purple rectangle of PupCapture/<n>.bmp show
on PinMAME's DMD. This compares that rectangle with every frame the game can show (scripts/pup_decode.py match)
and checks each D<n> line of the trigger map: an event of the form [captures] event ("game_deff_{id}") must name
an effect among the best matches. Lines with conditions ({count==3}), other events, or effects with no recorded
frames are checked by hand and marked so; captures only inactive rows use are marked unused. Re-run it after every sync with the game's upstream (an effect that no longer draws its capture is
marked **check**). Settings in game/pup.cfg [captures]:
    frames=["rom/mpf_package/media/dmd/deffs/deff_*/frames/*.png", ...]   globs from the repository root
    event_map="rom/mpf_package/event_map.csv"   credits library animations (column library_animations) to effects
    event="game_deff_{id}"
Vendored from Ashram56/Stern-SAM-Decryption tools/pup/runtime. Needs Pillow (in .venv).
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pup_decode  # noqa: E402
import toolchain as tc  # noqa: E402

sys.path.insert(0, tc.GAME)
from pup_runtime import engine, pupfiles, settings  # noqa: E402

REPORT = os.path.join(tc.ROOT, "docs", "pup_captures.md")


def owners_from_event_map(path):
    """[(regex, id)]: the frames of library animation <name> belong to every effect whose row lists it."""
    import csv
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            for anim in (row.get("library_animations") or "").split():
                out.append((re.escape(anim) + "/", row.get("deff")))
    return out


def main():
    cfg = settings.load()
    cap = cfg.get("captures", {})
    event = cap.get("event", "deff_{id}")
    template = re.compile("^" + re.escape(event).replace(r"\{id\}", r"(\d+)") + "$")
    owners = owners_from_event_map(os.path.join(tc.ROOT, cap["event_map"])) if cap.get("event_map") else []
    pack = pup_decode.Pack(settings.pack_dir(cfg))
    frames = [os.path.join(tc.ROOT, g) for g in cap.get("frames", [])]
    matched, _data, count = pup_decode.match(pack, frames, cap.get("id_regex", r"deff_(\d+)"), owners)
    mapping = engine.load_map(settings.map_path(cfg))
    regex = re.compile(cap.get("id_regex", r"deff_(\d+)"))
    drawn = {int(m.group(1)) for g in frames for p in glob.glob(g, recursive=True)
             for m in [regex.search(p.replace(os.sep, "/"))] if m}       # effects with recorded frames
    active = {t.id for t in pupfiles.load_triggers(settings.pack_dir(cfg)) if t.active}
    lines = ["# PuP DMD captures against the game's display effects", "",
             "Written by `scripts/pup_captures.py` ({} frames). D<n> fires in Visual Pinball when the pixels in the "
             "purple rectangle of `PupCapture/<n>.bmp` are on the DMD; *score* is the best frame's intersection over "
             "union of lit dots with it. *Effects*: every effect with a frame within 0.5 % of the best (2 % under "
             "97 %). *Map*: the trigger map's events for D<n>; *by hand* when they carry conditions or are not "
             "display effect events (checked by hand, see the map's comments).".format(count), "",
             "| D | rows | score | effects | map | |", "|---|---|---|---|---|---|"]
    disagree = 0
    for n, _rect, rows, best, ids, _label in matched:
        events = [str(e) for e in mapping["dmd"].get(n, [])]
        plain = [int(m.group(1)) for e in events for m in [template.match(e)] if m]
        if any(d not in drawn for d in plain):          # an effect with no recorded frames: checked by hand
            plain = []
        by_hand = len(plain) < len(events)
        if not rows or not any(r in active for r in rows):
            state = "unused"
        elif not events:
            state = "**unmapped**"
        elif plain and best >= 0.9 and not set(plain) <= set(i for i in ids if isinstance(i, int)):
            state = "**check**"
            disagree += 1
        else:
            state = "by hand" if by_hand else "ok"
        lines.append("| {} | {} | {:.0%} | {} | {} | {} |".format(
            n, " ".join(map(str, rows)) or "-", best, " ".join(map(str, ids)) or "-",
            "<br>".join(e.replace("|", "\\|") for e in events) or "-", state))
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("{} captures, {} to check: {}".format(len(matched), disagree, REPORT))
    return 1 if disagree else 0


if __name__ == "__main__":
    sys.exit(main())
