"""The PuP Pack's own files (triggers.pup, playlists.pup, screens.pup), read as PinUP Player reads them.

They stay the source of truth: the pack can be updated without touching this code. Only the meaning of the
trigger codes (D<n> = a DMD frame, W<n> = a switch, L<n> = a lamp) is translated, in trigger_map.yaml.
"""
import csv
import os
import re

TERM = re.compile(r"^([DWLS])(\d+)(?:=(\d+))?$")


def read_csv(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    head = [h.strip() for h in rows[0]]
    return [dict(zip(head, (c.strip() for c in row))) for row in rows[1:] if any(c.strip() for c in row)]


def _int(value, default=None):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_expression(text):
    """'D14' -> [('D', 14, None)]; 'W11=1,L35=1' -> [('W', 11, 1), ('L', 35, 1)]. Unknown terms raise."""
    terms = []
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        m = TERM.match(part.upper())
        if not m:
            raise ValueError("unknown PuP trigger term {!r}".format(part))
        terms.append((m.group(1), int(m.group(2)), _int(m.group(3))))
    return terms


class Trigger:
    """One row of triggers.pup."""
    __slots__ = ("id", "active", "descript", "expression", "terms", "screen", "playlist", "file", "volume",
                 "priority", "length", "counter", "rest", "loop")

    def __init__(self, row):
        self.id = _int(row.get("ID"))
        self.active = row.get("Active", "1") == "1"
        self.descript = row.get("Descript", "")
        self.expression = row.get("Trigger", "")
        self.terms = parse_expression(self.expression) if self.expression else []
        self.screen = _int(row.get("ScreenNum"))
        self.playlist = row.get("PlayList", "")
        self.file = row.get("PlayFile", "")
        self.volume = _int(row.get("Volume"))
        self.priority = _int(row.get("Priority"), 0)
        self.length = _float(row.get("Length"))
        self.counter = _int(row.get("Counter"))
        self.rest = _float(row.get("RestSeconds"), 0.0)
        self.loop = row.get("Loop", "")

    def command(self):
        """What the Godot PuP player needs to play this row (game/pup/pup_screen.gd)."""
        cmd = {"trigger": self.id, "screen": self.screen, "playlist": self.playlist, "file": self.file,
               "priority": self.priority, "mode": self.loop}
        if self.volume is not None:
            cmd["volume"] = self.volume
        if self.length:
            cmd["length"] = self.length
        return cmd

    def __repr__(self):
        return "<PuP trigger {} {!r} {}>".format(self.id, self.descript, self.expression)


def load_triggers(pack_dir):
    return [Trigger(row) for row in read_csv(os.path.join(pack_dir, "triggers.pup")) if _int(row.get("ID"))]
