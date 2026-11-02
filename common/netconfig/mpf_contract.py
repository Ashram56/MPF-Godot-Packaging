"""Bundle format 2: a game bundle is files and facts, the platform runs everything (platforms/game-bundles.md). Standard library only.

A format 2 `bundle.json` holds no command and names no script to run: no `run`, `launch`, `options.tool`, `profiles.apply`,
`pup.install`. The platform reads its facts and does the rest itself:

- launch: `python -m mpf_godot run <game_dir> -c <configs> -- -- <Godot user arguments>` (platform_launch below);
- MPF hardware: the configs of `mpf.hardware[<the "hardware" setting>]` are added to `mpf.configs`;
- settings: the schema `settings.schema` (a JSON file of the bundle) is shown on the page; the values live in
  `<game>/.platform/settings.json` (written by the platform, carried over by updates); each option says where its value goes:
  `{"godot_arg": "--dmd-tint"}` (a Godot user argument), `{"ini": "game/pup.local.cfg", "section": "pup", "key": "ost_music"}`
  (a key the platform writes before the start) or `{"hardware": true}` (picks `mpf.hardware`);
- board profiles: `profiles.<board>` = {"limits": {option: [allowed values]}, "defaults": {option: value}}, the board is detected here;
- PuP Pack: the author's zip, unpacked as it is into the library and linked at `<game>/.platform/pup`; the game reads it from
  `MPF_PUP_PACK` and its own `pup.manifest` (a list of the pack's files and how to show them, never a file of the pack);
- add-ons (DMD only): folders of the bundle listed in `addons`, each switched on by a setting, passed in `MPF_ADDONS`.
"""
import configparser
import json
import os
import platform

FORMAT = 2
PLATFORM_DIR = ".platform"                    # what the platform keeps inside a game's folder (settings, the PuP link)
PUP_LINK = PLATFORM_DIR + "/pup"
SETTINGS_FILE = PLATFORM_DIR + "/settings.json"
# keys of format 1 that made the platform run something of the game's
FORBIDDEN = {"run": "the platform launches the game", "launch": "the platform launches the game",
             "options": "settings are declared in `settings.schema`, the platform applies them",
             "extra": "board profiles are data in `profiles`", "precheck": "a build step, not part of a bundle"}
FORBIDDEN_PUP = ("install", "status", "pack_dir", "media_dir", "extract_only", "needs_restart")
TARGETS = ("godot_arg", "ini", "hardware")
DT_MODEL = os.environ.get("MPF_DT_MODEL", "/proc/device-tree/model")


def is_v2(b):
    return int((b or {}).get("format", 1)) >= FORMAT


def problems(b, root=None):
    """[str]: what makes `b` (a format 2 bundle.json) break the contract; with `root` (the unpacked bundle) also the files it declares."""
    bad = []
    for k, why in FORBIDDEN.items():
        if k in b:
            bad.append(f"`{k}` is not allowed in a format 2 bundle ({why})")
    for k in FORBIDDEN_PUP:
        if k in (b.get("pup") or {}):
            bad.append(f"`pup.{k}` is not allowed: the platform unpacks the author's zip and gives the game MPF_PUP_PACK")
    if "env" in (b.get("requires") or {}):
        bad.append("`requires.env` is not allowed: the platform's variables have fixed names (MPF_GAME_VENV, GODOT, MPF_*)")
    for board, p in (b.get("profiles") or {}).items():
        if not isinstance(p, dict) or set(p) - {"limits", "defaults", "godot_args"}:
            bad.append(f"`profiles.{board}` may only hold limits, defaults and godot_args (data, no command)")
    if not b.get("game_dir"):
        bad.append("`game_dir` is missing: the folder with project.godot and MPF's config/")
    for a in b.get("addons") or []:
        if not isinstance(a, dict) or not a.get("id") or not a.get("dir"):
            bad.append("each `addons` entry needs an id and a dir")
    if root:
        bad += missing_files(b, root)
        try:
            schema(root, b)
        except ValueError as e:
            bad.append(str(e))
    return bad


def missing_files(b, root):
    game = os.path.join(root, b.get("game_dir") or "game")
    need = [(os.path.join(game, "project.godot"), "game_dir has no project.godot")]
    configs = list((b.get("mpf") or {}).get("configs") or ["config"])
    for sets in ((b.get("mpf") or {}).get("hardware") or {}).values():
        configs += list(sets)
    for c in configs:
        need.append((os.path.join(game, "config", c + ".yaml"), f"MPF config {c}.yaml is not in {b.get('game_dir')}/config"))
    if (b.get("settings") or {}).get("schema"):
        need.append((os.path.join(root, b["settings"]["schema"]), "the settings schema is not in the bundle"))
    if (b.get("pup") or {}).get("manifest"):
        need.append((os.path.join(root, b["pup"]["manifest"]), "the PuP manifest is not in the bundle"))
    for a in b.get("addons") or []:
        if isinstance(a, dict) and a.get("dir"):
            need.append((os.path.join(root, a["dir"]), f"add-on {a.get('id')}: {a['dir']} is not in the bundle"))
    return [msg for path, msg in need if not os.path.exists(path)]


# ---------------------------------------------------------------- the board
def board():
    """rpi4, rpi5, jetson, x86 or arm64 (MPF_BOARD wins): the key of `profiles`."""
    if os.environ.get("MPF_BOARD"):
        return os.environ["MPF_BOARD"]
    try:
        model = open(DT_MODEL, encoding="utf-8", errors="replace").read()
    except OSError:
        model = ""
    for word, name in (("Raspberry Pi 5", "rpi5"), ("Raspberry Pi 4", "rpi4"), ("Raspberry Pi", "rpi"), ("Jetson", "jetson"),
                       ("NVIDIA", "jetson")):
        if word in model:
            return name
    return "x86" if platform.machine() in ("x86_64", "amd64") else "arm64"


def profile(b, board_name=None):
    return ((b.get("profiles") or {}).get(board_name or board())) or {}


# ---------------------------------------------------------------- settings
def schema(game, b, board_name=None):
    """The bundle's settings schema as this board sees it: choices narrowed to the profile's limits, defaults replaced by its defaults."""
    rel = (b.get("settings") or {}).get("schema")
    if not rel:
        return {"groups": [], "options": []}
    try:
        with open(os.path.join(game, rel), encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"the settings schema {rel} cannot be read: {e}")
    prof = profile(b, board_name)
    for o in s.get("options", []):
        t = o.get("target") or {}
        if sum(k in t for k in TARGETS) != 1:
            raise ValueError(f"setting {o.get('id')}: its target needs exactly one of {', '.join(TARGETS)}")
        allowed = (prof.get("limits") or {}).get(o["id"])
        if allowed is not None and "choices" in o:
            o["choices"] = [c for c in o["choices"] if c in allowed] or o["choices"]
        if o["id"] in (prof.get("defaults") or {}):
            o["default"] = prof["defaults"][o["id"]]
    return s


def saved(game):
    try:
        with open(os.path.join(game, SETTINGS_FILE), encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def save(game, values):
    path = os.path.join(game, SETTINGS_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(values, f, indent=1, sort_keys=True)
    os.replace(path + ".tmp", path)


def check_value(o, v):
    """The value as stored (a string, a number or a bool), or ValueError."""
    t = o.get("type", "string")
    if t == "bool":
        if str(v).lower() in ("1", "true", "on", "yes"):
            return True
        if str(v).lower() in ("0", "false", "off", "no"):
            return False
        raise ValueError(f"{o['id']}: on or off")
    if t in ("integer", "number"):
        try:
            n = int(v) if t == "integer" else float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{o['id']}: a number")
        if ("min" in o and n < o["min"]) or ("max" in o and n > o["max"]):
            raise ValueError(f"{o['id']}: between {o.get('min')} and {o.get('max')}")
        return n
    v = str(v)
    v = (o.get("aliases") or {}).get(v, v)
    if "choices" in o and v not in o["choices"]:
        raise ValueError(f"{o['id']}: one of {', '.join(map(str, o['choices']))}")
    return v


def set_values(game, b, pairs, unset=()):
    opts = {o["id"]: o for o in schema(game, b)["options"]}
    cur = saved(game)
    for k, v in pairs:
        if k not in opts:
            raise ValueError(f"unknown setting {k}")
        cur[k] = check_value(opts[k], v)
    for k in unset:
        cur.pop(k, None)
    save(game, cur)
    return cur


def effective(game, b, board_name=None):
    """{option: value} used at the start: the saved value when this board allows it, else the profile's default, else the schema's."""
    s = schema(game, b, board_name)
    cur = saved(game)
    out = {}
    for o in s.get("options", []):
        v = cur.get(o["id"], o.get("default"))
        if "choices" in o and v is not None and v not in o["choices"]:
            v = o.get("default")
        if v is not None:
            out[o["id"]] = v
    return out


# ---------------------------------------------------------------- the start
def _arg(v):
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


def apply_ini(game, writes):
    """Write the `ini` settings into the game's files (configparser; the other keys of a file stay as they are)."""
    for rel, keys in writes.items():
        path = os.path.join(game, rel)
        cp = configparser.ConfigParser(interpolation=None)
        cp.optionxform = str
        cp.read(path, encoding="utf-8")
        for (sec, key), v in keys.items():
            if not cp.has_section(sec):
                cp.add_section(sec)
            cp.set(sec, key, v)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            cp.write(f)


def plan(game, b, board_name=None):
    """What the platform starts, from the bundle's facts and the saved settings: {game_dir, configs, godot_args, ini, env}."""
    values = effective(game, b, board_name)
    opts = {o["id"]: o for o in schema(game, b, board_name).get("options", [])}
    mpf = b.get("mpf") or {}
    configs = list(mpf.get("configs") or ["config"])
    hw_sets = mpf.get("hardware") or {}
    godot, ini = [], {}
    hw = None
    for k, v in values.items():
        t = opts[k].get("target") or {}
        if "godot_arg" in t:
            godot.append(f"{t['godot_arg']}={_arg(v)}")
        elif "ini" in t:
            ini.setdefault(t["ini"], {})[(t.get("section", "main"), t["key"])] = _arg(v)
        elif t.get("hardware"):
            hw = str(v)
    if hw is None and hw_sets:
        hw = "virtual" if "virtual" in hw_sets else sorted(hw_sets)[0]
    configs += [c for c in hw_sets.get(hw, []) if c not in configs]
    godot = [str(a) for a in profile(b, board_name).get("godot_args", [])] + godot
    env = {"MPF_BOARD": board_name or board(), "MPF_GAME_DATA": os.path.join(game, PLATFORM_DIR, "data")}
    pup = os.path.join(game, PUP_LINK)
    if b.get("pup") and os.path.isfile(os.path.join(pup, "triggers.pup")):
        env["MPF_PUP_PACK"] = os.path.realpath(pup)
    on = []
    for a in b.get("addons") or []:
        want = a.get("when", True)
        if not a.get("setting") or values.get(a["setting"]) == want:
            on.append(os.path.join(game, a["dir"]))
    if on:
        env["MPF_ADDONS"] = os.pathsep.join(on)
    return {"game_dir": os.path.normpath(os.path.join(game, b.get("game_dir") or "game")), "configs": configs,
            "godot_args": godot, "ini": ini, "env": env}
