"""game/pup.cfg (+ game/pup.local.cfg): the PuP settings Godot and MPF share.

The files are Godot ConfigFile INI with JSON values, so both sides parse them the same way. [pup] env names the
game's environment prefix: <env>_PUP=0 (or PUP=0) disables the PuP whatever the files say, <env>_PUP_ZIP gives
the pack's zip (scripts/pup_setup.py).
"""
import json
import os

GAME = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT = os.path.dirname(GAME)
FILES = ("pup.cfg", "pup.local.cfg")
OFF = ("0", "false", "no", "off")


def _parse(path, into):
    section = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line[0] in ";#":
                continue
            if line.startswith("[") and line.endswith("]"):
                section = into.setdefault(line[1:-1].strip(), {})
                continue
            if "=" not in line or section is None:
                continue
            key, value = line.split("=", 1)
            try:
                section[key.strip()] = json.loads(value.strip())
            except ValueError:
                section[key.strip()] = value.strip().strip('"')


def env_name(cfg, what="PUP"):
    """<env>_PUP, <env>_PUP_ZIP...: the game's environment variable for `what` ([pup] env, e.g. "TF")."""
    prefix = str(cfg.get("pup", {}).get("env", "")).strip()
    return "{}_{}".format(prefix, what) if prefix else what


def load(game_dir=GAME):
    cfg = {}
    for name in FILES:
        path = os.path.join(game_dir, name)
        if os.path.exists(path):
            _parse(path, cfg)
    pup = cfg.setdefault("pup", {})
    for var in {env_name(cfg), "PUP"}:
        if os.environ.get(var, "").strip().lower() in OFF:
            pup["enabled"] = False
    return cfg


def _path(cfg, key, default, root):
    return os.path.join(root, cfg.get("pup", {}).get(key, default))


def pack_dir(cfg, root=ROOT):
    return _path(cfg, "pack_dir", "pup_pack", root)


def media_dir(cfg, root=ROOT):
    return _path(cfg, "media_dir", "pup_media", root)


def map_path(cfg, game_dir=GAME):
    return os.path.join(game_dir, cfg.get("pup", {}).get("trigger_map", "pup_map/trigger_map.yaml"))
