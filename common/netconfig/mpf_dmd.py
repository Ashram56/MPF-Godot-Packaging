"""The machine's DMD output: which display shows the game's DMD, and the Serum colourisation of a ZeDMD.

One output at a time: "auto" (what is detected at the game's start), "lcd" (the HD DMD on the screen), "pin2dmd" (the 128x32
monochrome frames straight from Godot) or "zedmd" (dmd_bridge: unmodified libzedmd, plus unmodified libserum when a colourisation
is assigned to the game). The game only draws its classic 128x32 DMD; every argument below is the platform's, the game composes none.
Settings: STATE_DIR/dmd.json. Colourisations: SERUM/<rom>/<rom>.cROMc|.cRZ|.cROM, one per ROM name, assigned per game."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpf_common as C  # noqa: E402

OUTPUTS = ("auto", "lcd", "pin2dmd", "zedmd")
EXTS = (".cROMc", ".cRZ", ".cROM")
DEFAULT_COLOR = "#2a6cff"
SERUM = os.environ.get("MPF_SERUM_DIR") or os.path.join(C.DATA, "serum")
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def settings_file():
    return os.path.join(C.STATE_DIR, "dmd.json")


def load():
    try:
        with open(settings_file()) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    out = d.get("output")
    color = d.get("color")
    return {"output": out if out in OUTPUTS else "auto",
            "color": color if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) else DEFAULT_COLOR,
            "serum": {k: v for k, v in (d.get("serum") or {}).items() if isinstance(v, str)}}


def save(s):
    os.makedirs(C.STATE_DIR, exist_ok=True)
    with C.writable(C.STATE_DIR):
        tmp = settings_file() + ".tmp"
        with open(tmp, "w") as f:
            json.dump(s, f, indent=1)
        os.replace(tmp, settings_file())


def set_output(output=None, color=None):
    s = load()
    if output is not None:
        if output not in OUTPUTS:
            raise ValueError("unknown DMD output")
        s["output"] = output
    if color is not None:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("colour must be #RRGGBB")
        s["color"] = color.lower()
    save(s)
    return s


# ---------------------------------------------------------------- Serum library
def library():
    """[{rom, file, size}] of the uploaded colourisations."""
    out = []
    if os.path.isdir(SERUM):
        for rom in sorted(os.listdir(SERUM)):
            for ext in EXTS:
                f = os.path.join(SERUM, rom, rom + ext)
                if os.path.isfile(f):
                    out.append({"rom": rom, "file": rom + ext, "size": os.path.getsize(f)})
                    break
    return out


def serum_path(rom):
    for ext in EXTS:
        f = os.path.join(SERUM, rom, rom + ext)
        if NAME_RE.match(rom) and os.path.isfile(f):
            return f
    return None


def store_serum(src, name):
    """Install an uploaded file `<rom>.cROMc|.cRZ|.cROM` into the library (the ROM name is the file's name)."""
    base = os.path.basename(name)
    rom, ext = os.path.splitext(base)
    if ext not in EXTS or not NAME_RE.match(rom):
        raise ValueError("expected <rom>.cROMc, <rom>.cRZ or <rom>.cROM (e.g. trn_174h.cROMc)")
    dest = os.path.join(SERUM, rom)
    with C.writable(SERUM if os.path.isdir(SERUM) else os.path.dirname(SERUM)):
        os.makedirs(dest, exist_ok=True)
        for e in EXTS:
            if e != ext and os.path.exists(os.path.join(dest, rom + e)):
                os.remove(os.path.join(dest, rom + e))
        os.replace(src, os.path.join(dest, base)) if os.path.dirname(src) == dest else _move(src, os.path.join(dest, base))
        _own(dest)
    return rom


def _move(src, dst):
    import shutil
    shutil.move(src, dst)


def _own(dest):
    """The game user reads the library."""
    try:
        import pwd
        pw = pwd.getpwnam(C.USER)
        for root, dirs, files in os.walk(dest):
            for n in dirs + files:
                os.chown(os.path.join(root, n), pw.pw_uid, pw.pw_gid)
        os.chown(dest, pw.pw_uid, pw.pw_gid)
        os.chmod(dest, 0o755)
    except (KeyError, OSError, ImportError):
        pass


def delete_serum(rom):
    import shutil
    if not NAME_RE.match(rom) or not os.path.isdir(os.path.join(SERUM, rom)):
        raise ValueError("no such colourisation")
    with C.writable(SERUM):
        shutil.rmtree(os.path.join(SERUM, rom))
    s = load()
    s["serum"] = {g: r for g, r in s["serum"].items() if r != rom}
    save(s)


def assign_serum(game_id, rom):
    """rom "" = the default (the one named like the game's ROM, if uploaded), "none" = no colour, else a library entry."""
    s = load()
    if rom in ("", None):
        s["serum"].pop(game_id, None)
    elif rom == "none" or serum_path(rom):
        s["serum"][game_id] = rom
    else:
        raise ValueError("no such colourisation")
    save(s)


def game_rom(bundle):
    """The ROM name of a game: `dmd.rom` of its bundle recipe."""
    return ((bundle or {}).get("dmd") or {}).get("rom") or ""


def chosen_serum(game_id, bundle, s=None):
    """ROM name of the colourisation that goes with this game, or ""."""
    s = s or load()
    pick = s["serum"].get(game_id, "")
    if pick == "none":
        return ""
    if pick and serum_path(pick):
        return pick
    rom = game_rom(bundle)
    return rom if rom and serum_path(rom) else ""


# ---------------------------------------------------------------- launch
def bridge_dir():
    """Folder of dmd_bridge (and its libzedmd / libserum64.so), or None."""
    roots = [os.environ.get("MPF_DMD_BRIDGE_DIR", ""), C.PLATFORM_DIR,
             os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))]
    arch = C.ARCH.get(os.uname().machine, os.uname().machine)
    for r in roots:
        for sub in ("", os.path.join("native", "bin", arch, "dmd_bridge"), os.path.join("native", "bin", "dmd_bridge")):
            d = os.path.join(r, sub) if r else ""
            if d and os.path.isfile(os.path.join(d, "dmd_bridge")):
                return d
    return None


def detect():
    """"pin2dmd", "zedmd" or "" (an LCD DMD)."""
    try:
        from mpf_godot import dmd_panel
        return dmd_panel.find()
    except Exception:       # no sysfs, no pyserial rights...: the screen
        return ""


def resolve(s=None, detected=None):
    """The output that is used: the setting, or what is detected for "auto"."""
    s = s or load()
    if s["output"] != "auto":
        return s["output"]
    return {"pin2dmd": "pin2dmd", "zedmd": "zedmd"}.get(detected if detected is not None else detect(), "lcd")


LAST = "lcd"        # the output of the last plan(): exported to the game as MPF_DMD_OUTPUT


def plan(game_id, bundle, detected=None):
    """(launcher_args, godot_user_args) for the game packaged launcher: the part before `--` and the part after `-- --`."""
    global LAST
    s = load()
    out = resolve(s, detected)
    LAST = out if out == "pin2dmd" or (out == "zedmd" and bridge_dir()) else "lcd"
    if out == "pin2dmd":
        return [f"--pin2dmd={s['color']}"], []
    if out != "zedmd":
        return [], []
    d = bridge_dir()
    if not d:
        return [], []           # no bridge on this system: the screen DMD
    user = ["--zedmd-shades", "--zedmd-feed=" + os.path.join(d, "dmd_bridge")]
    rom = chosen_serum(game_id, bundle, s)
    if rom:
        lib = next((p for p in (os.path.join(d, "libserum64.so"), os.path.join(d, "lib", "libserum64.so")) if os.path.isfile(p)), "")
        if lib:
            for a in ("--serum-lib", lib, "--rom", rom, "--altcolor", SERUM):
                user.append("--zedmd-feed-arg=" + a)
    return [f"--zedmd={s['color']}"], user


def merge_args(board, game_id, bundle):
    """The board's own arguments (MPF_GAME_ARGS) plus the DMD output's: the launcher's part goes before the first `--`, the Godot
    user arguments after `-- --`."""
    pre, user = plan(game_id, bundle)
    if "--" in board:
        i = board.index("--")
        head, tail = board[:i], board[i:]
    else:
        head, tail = board, []
    if user:
        tail = (tail if tail[:2] == ["--", "--"] else ["--", "--"] + tail[2:] if tail else ["--", "--"]) + user
    return head + pre + tail
