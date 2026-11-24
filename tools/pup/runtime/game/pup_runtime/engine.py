"""PuP trigger engine: which triggers.pup rows a game event fires, and their RestSeconds.

No MPF here (pup_runtime/mode.py wires it to the machine), so the unit tests drive it directly.
A fired row becomes a command for the Godot PuP player (game/pup/pup_player.gd), which owns the screens,
playlists, priorities and the Loop column (Loop, SetBG, StopFile, StopPlayer, SkipSamePrty).

The trigger map (YAML) says what the pack's trigger codes mean in the game:
    dmd:       {n: [events]}        D<n>: the events of the display effects that draw capture n
    switches:  {n: switch_name}     W<n>: the switch, by name
    override:  {row ID: [events]}   any row (lamp terms, several terms, a better event than its capture's)
    counters:  {event: [reset events]}   the event gets a `count` argument: 1, 2, 3... since a reset event
An event may carry conditions on its arguments, all of which must hold: "game_deff_112{award==1}",
"game_deff_102{count==3, completed==0}", "game_deff_83{values.1==4}" (item 1 of the list argument `values`),
"game_deff_142{state.side==1}" (the game's rule state: [pup] state in game/pup.cfg, pup_runtime/mode.py).
"""
import re

from pup_runtime import pupfiles

EVENT = re.compile(r"^\s*([\w.]+)\s*(?:\{(.*)\})?\s*$")
CONDITION = re.compile(r"^\s*([\w.]+)\s*==\s*([\w.\-]+)\s*$")


def load_map(path):
    from ruamel.yaml import YAML
    with open(path, encoding="utf-8") as f:
        data = YAML(typ="safe").load(f) or {}
    out = {key: {int(k): v for k, v in (data.get(key) or {}).items()} for key in ("dmd", "switches", "override")}
    out["counters"] = {str(k): list(v or []) for k, v in (data.get("counters") or {}).items()}
    return out


def parse_event(text):
    """'game_deff_112{award==1}' -> ('game_deff_112', (('award', '1'),)); 'game_deff_25' -> ('game_deff_25', ())."""
    m = EVENT.match(str(text))
    if not m:
        raise ValueError("bad PuP event {!r}".format(text))
    conds = []
    for part in (m.group(2) or "").split(","):
        if not part.strip():
            continue
        c = CONDITION.match(part)
        if not c:
            raise ValueError("bad PuP event condition {!r} in {!r}".format(part, text))
        conds.append((c.group(1), c.group(2)))
    return m.group(1), tuple(conds)


def arg(kwargs, path):
    """kwargs['values'][1] for 'values.1', kwargs['state'].side for 'state.side'; None when missing."""
    value = kwargs
    for key in path.split("."):
        if isinstance(value, (list, tuple)):
            if not (key.lstrip("-").isdigit() and -len(value) <= int(key) < len(value)):
                return None
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value.get(key, getattr(value, key, None))
        else:
            value = getattr(value, key, None)
        if value is None:
            return None
    return value


def holds(conds, kwargs):
    return all(str(arg(kwargs, key)) == want for key, want in conds)


class Engine:

    def __init__(self, triggers, trigger_map, send, now, enable=()):
        """triggers: pupfiles.Trigger rows; send(command dict); now() -> seconds; enable: row IDs used even when
        the pack leaves them inactive (Active 0), such as its music rows ([pup] music_rows, pup_runtime/mode.py)."""
        enable = {int(i) for i in enable}
        self.send, self.now = send, now
        self.events = {}            # event name -> [(conditions, Trigger)]
        self.switches = {}          # switch name -> [Trigger]
        self.unmapped = []          # rows this game cannot fire (unknown code or no mapping)
        self.last = {}              # trigger id -> time it last fired (RestSeconds)
        self.counted = dict(trigger_map.get("counters", {}))    # event -> its reset events
        self.resets = {}            # reset event -> [counted events]
        self.counts = {}            # counted event -> count since its last reset
        for name, resets in self.counted.items():
            for reset in resets:
                self.resets.setdefault(reset, []).append(name)
        for row in triggers:
            if not (row.active or row.id in enable) or not row.terms or row.screen is None:
                continue
            self._bind(row, trigger_map)

    def _bind(self, row, trigger_map):
        events = trigger_map["override"].get(row.id)
        if events is None and len(row.terms) == 1:
            kind, num, _ = row.terms[0]
            if kind == "D":
                events = trigger_map["dmd"].get(num)
            elif kind == "W" and num in trigger_map["switches"]:
                self.switches.setdefault(trigger_map["switches"][num], []).append(row)
                return
        if not events:
            self.unmapped.append(row)
            return
        for text in events:
            name, conds = parse_event(text)
            self.events.setdefault(name, []).append((conds, row))

    # ------------------------------------------------------------------ firing

    def on_event(self, name, **kwargs):
        for counted in self.resets.get(name, ()):
            self.counts[counted] = 0
        if name in self.counted:
            self.counts[name] = self.counts.get(name, 0) + 1
            kwargs = dict(kwargs, count=self.counts[name])
        self.fire([row for conds, row in self.events.get(name, ()) if holds(conds, kwargs)])

    def on_switch(self, name):
        self.fire(self.switches.get(name, ()))

    def fire(self, rows):
        """Rows in triggers.pup order; a row resting since its last fire is skipped. Two rows that would send
        the same command (several captures of one display effect) send it once."""
        now = self.now()
        sent = set()
        for row in sorted(rows, key=lambda r: r.id):
            last = self.last.get(row.id)
            if last is not None and row.rest and now - last < row.rest:
                continue
            self.last[row.id] = now
            cmd = row.command()
            key = (cmd["screen"], cmd["playlist"], cmd["file"], cmd["mode"], cmd["priority"])
            if key in sent:
                continue
            sent.add(key)
            self.send(cmd)

    @property
    def event_names(self):
        """Every event the engine must hear: the mapped ones, the counted ones and their resets."""
        return sorted(set(self.events) | set(self.counted) | set(self.resets))


def build(pack_dir, map_path, send, now, enable=()):
    return Engine(pupfiles.load_triggers(pack_dir), load_map(map_path), send, now, enable)
