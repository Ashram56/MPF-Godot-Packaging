#!/usr/bin/env python3
"""Writes fixes/README.md, the index of every fix document, from each document's title and table.

    python fixes/make_index.py           # rewrite the index
    python fixes/make_index.py --check   # exit 1 when the index is out of date (tests/test_fixes.py)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# component folder -> (heading, where its issues go)
COMPONENTS = [
    ("mpf", "MPF", "https://github.com/missionpinball/mpf/issues"),
    ("mpf-monitor", "MPF Monitor", "https://github.com/missionpinball/mpf-monitor/issues"),
    ("gmc", "GMC", "https://github.com/missionpinball/mpf-gmc/issues"),
    ("godot", "Godot", "https://github.com/godotengine/godot/issues"),
    ("gde-gozen", "GDE GoZen", "https://codeberg.org/gozen/gde_gozen/issues"),
    ("jetson-ffmpeg", "jetson-ffmpeg", "https://github.com/gjrtimmer/jetson-ffmpeg/issues"),
    ("native-video", "native_video", "https://github.com/claytercek/godot-native-video/issues"),
    ("libpinproc", "libpinproc / pypinproc", "https://github.com/preble/libpinproc/issues"),
]
SECTIONS = ("## Problem", "## Cause", "## Fix", "## How to check", "## Upstream issue")
ROWS = ("Id", "Component", "Kind", "Affected versions", "Platforms", "Found on", "Fact", "Our fix", "Applied by",
        "Upstream")


def parse(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    title = text.split("\n", 1)[0].lstrip("# ").strip()
    rows = {}
    for m in re.finditer(r"^\| ([^|]+?) \| (.*) \|$", text, re.M):
        rows.setdefault(m.group(1).strip(), m.group(2).strip())
    return title, rows, text


def problems(path):
    """What a fix document lacks against fixes/TEMPLATE.md."""
    title, rows, text = parse(path)
    missing = ["row " + r for r in ROWS if r not in rows] + ["section " + s for s in SECTIONS if s not in text]
    if not title:
        missing.append("title")
    return missing


def short(cell, n=90):
    cell = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", re.sub(r"\s+", " ", cell))   # links are relative to the doc
    return cell if len(cell) <= n else cell[:n - 1].rstrip() + "…"


def index():
    out = ["# Fixes and improvements",
           "",
           "Every change we carry to MPF, MPF Monitor, GMC, Godot and the add-ons and libraries around them, one document",
           "each: problem, cause, our fix, affected versions, platforms, how to check, and a draft issue for the upstream",
           "project. **No draft is filed yet**: each becomes one upstream issue when the owner says so. Platform and",
           "installer findings (Windows, macOS, Linux, Jetson) are in [../platforms/](../platforms/README.md).",
           "",
           "New fix: copy [TEMPLATE.md](TEMPLATE.md) to `fixes/<component>/<slug>.md`, then run `python fixes/make_index.py`",
           "(this page is generated from the documents' tables; `tests/test_fixes.py` checks both).",
           ""]
    total = 0
    for folder, name, tracker in COMPONENTS:
        d = os.path.join(HERE, folder)
        if not os.path.isdir(d):
            continue
        docs = sorted(f for f in os.listdir(d) if f.endswith(".md") and f != "README.md")
        if not docs:
            continue
        out += ["## {}".format(name), "", "Upstream tracker: {}".format(tracker), "",
                "| Fix | Kind | Platforms | Applied by | Upstream |", "|---|---|---|---|---|"]
        for doc in docs:
            title, rows, _ = parse(os.path.join(d, doc))
            out.append("| [{}]({}/{}) | {} | {} | {} | {} |".format(
                title, folder, doc, short(rows.get("Kind", ""), 40), short(rows.get("Platforms", ""), 60),
                short(rows.get("Applied by", "")), short(rows.get("Upstream", ""), 70)))
            total += 1
        out.append("")
    out += ["Test projects and repro programs the reports refer to: [repro/](repro/).", "",
            "{} documents.".format(total), ""]
    return "\n".join(out)


def main(argv):
    text = index()
    path = os.path.join(HERE, "README.md")
    if "--check" in argv:
        with open(path, encoding="utf-8") as f:
            return 0 if f.read() == text else 1
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
