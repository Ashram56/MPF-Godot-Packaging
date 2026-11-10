"""The machine's DMD output: which display shows the game's DMD, and the Serum colourisation of a ZeDMD.

One output at a time: "auto" (what is detected at the game's start), "lcd" (the HD DMD on the screen), "pin2dmd" (the 128x32
monochrome frames straight from Godot) or "zedmd" (dmd_bridge: unmodified libzedmd, plus unmodified libserum when a colourisation
is assigned to the game). The game only draws its classic 128x32 DMD; every argument below is the platform's, the game composes none.
Settings: STATE_DIR/dmd.json. Colourisations: SERUM/<rom>/<rom>.cROMc|.cRZ|.cROM, one per ROM name, assigned per game."""
import json
import os
import platform
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpf_common as C  # noqa: E402

OUTPUTS = ("auto", "lcd", "pin2dmd", "zedmd", "web")
EXTS = (".cROMc", ".cRZ", ".cROM")
# "web": the same pictures a ZeDMD would get (Serum colour included) written by dmd_bridge to a file in RAM, which the setup page draws
PREVIEW = os.environ.get("MPF_DMD_PREVIEW") or "/run/mpf-dmd/preview.rgb"
PREVIEW_PNG = os.environ.get("MPF_DMD_PREVIEW_PNG") or "/run/mpf-dmd/preview.png"     # written by the dmd_out add-on (--dmd-preview=)
LOOKS = ("classic", "hd", "advanced")     # classic = the ROM's 128x32 dots; hd = LCD with a vector font; advanced = LCD with the game's extras
PREVIEW_SIZES = {128 * 32 * 3: (128, 32), 192 * 64 * 3: (192, 64), 256 * 64 * 3: (256, 64)}
PREVIEW_MAX_AGE = 5      # seconds: an older picture means the game is not running
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
    look = d.get("look")
    return {"output": out if out in OUTPUTS else "auto",
            "look": look if look in LOOKS else "",
            "color": color if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) else DEFAULT_COLOR,
            "serum": {k: v for k, v in (d.get("serum") or {}).items() if isinstance(v, str)}}


def save(s):
    os.makedirs(C.STATE_DIR, exist_ok=True)
    with C.writable(C.STATE_DIR):
        tmp = settings_file() + ".tmp"
        with open(tmp, "w") as f:
            json.dump(s, f, indent=1)
        os.replace(tmp, settings_file())


def set_output(output=None, color=None, look=None):
    s = load()
    if look is not None:
        if look not in LOOKS + ("",):
            raise ValueError("unknown DMD look")
        s["look"] = look
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
BRIDGE = "dmd_bridge.exe" if os.name == "nt" else "dmd_bridge"
# libserum's library as native/serum/build_libserum*.sh name it
SERUM_LIBS = ("serum64.dll",) if os.name == "nt" else ("libserum64.so", "libserum.so", "libserum64.dylib", "libserum.dylib")


def bridge_dir():
    """Folder of dmd_bridge (and its libzedmd / libserum), or None. Windows: the prebuilt native/prebuilt/windows-x86_64/dmd_bridge/
    (native/dmd_bridge/build_windows.sh) of the local platform (mpf_godot/local.py)."""
    roots = [os.environ.get("MPF_DMD_BRIDGE_DIR", ""), C.PLATFORM_DIR,
             os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))]
    arch = C.ARCH.get(platform.machine().lower(), platform.machine())
    subs = ["", os.path.join("native", "bin", arch, "dmd_bridge"), os.path.join("native", "bin", "dmd_bridge")]
    if os.name == "nt":
        subs.insert(1, os.path.join("native", "prebuilt", "windows-" + arch, "dmd_bridge"))
    elif sys.platform == "darwin":
        subs.insert(1, os.path.join("native", "bin", "macos-" + arch, "dmd_bridge"))
    for r in roots:
        for sub in subs:
            d = os.path.join(r, sub) if r else ""
            if d and os.path.isfile(os.path.join(d, BRIDGE)):
                return d
    return None


def serum_lib(d):
    """libserum next to dmd_bridge (or in its lib/), or ""."""
    for name in SERUM_LIBS:
        for p in (os.path.join(d, name), os.path.join(d, "lib", name)):
            if os.path.isfile(p):
                return p
    return ""


def probe_bridge(timeout=15):
    """True when dmd_bridge --probe finds a ZeDMD (libzedmd looks on every serial port: Windows and macOS, where dmd_panel has no
    sysfs)."""
    d = bridge_dir()
    if not d:
        return False
    try:
        return subprocess.run([os.path.join(d, BRIDGE), "--probe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              stdin=subprocess.DEVNULL, timeout=timeout).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def detect():
    """"pin2dmd", "zedmd" or "" (an LCD DMD). Linux: sysfs (mpf_godot/dmd_panel.py); Windows and macOS: a ZeDMD that answers dmd_bridge."""
    if not sys.platform.startswith("linux"):
        return "zedmd" if probe_bridge() else ""
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


def bundle_looks(bundle):
    """{look: [Godot user arguments]} the bundle declares in `dmd.looks` (bundle.json), {} when it declares none."""
    looks = ((bundle or {}).get("dmd") or {}).get("looks")
    out = {}
    for k, v in (looks.items() if isinstance(looks, dict) else []):
        if k in LOOKS and isinstance(v, list) and all(isinstance(a, str) for a in v):
            out[k] = list(v)
    return out


def allowed_looks(bundle, board_name=None):
    """bundle_looks narrowed to the board's limit (`profiles.<board>.dmd_looks`, e.g. a Pi 4: ["classic"])."""
    looks = bundle_looks(bundle)
    try:
        import mpf_contract as K
        allowed = (K.profile(bundle, board_name) or {}).get("dmd_looks")
    except Exception:
        allowed = None
    return {k: v for k, v in looks.items() if k in allowed} if isinstance(allowed, list) else looks


def effective_look(s, bundle, out, board_name=None):
    """The look that runs: only an LCD shows more than the exact 128x32 classic dots (PIN2DMD, ZeDMD with or without Serum, the page's
    preview of those). On an LCD: always "advanced" when the bundle offers it (and the board allows it): the LCD DMD is the game's full one,
    there is no intermediate HD look to choose. A bundle without "advanced" keeps the old rule: the stored setting if it offers it, else
    its `dmd.looks` default (`dmd.look`), else its first look."""
    looks = allowed_looks(bundle, board_name)
    if not looks:
        return ""
    if out != "lcd":
        return "classic" if "classic" in looks else ""
    if "advanced" in looks:
        return "advanced"
    want = s.get("look") or ((bundle or {}).get("dmd") or {}).get("look")
    return want if want in looks else next(iter(looks))


def look_args(s, bundle, out):
    return allowed_looks(bundle).get(effective_look(s, bundle, out), [])


def plan(game_id, bundle, detected=None):
    """(launcher_args, godot_user_args) for the game packaged launcher: the part before `--` and the part after `-- --`."""
    global LAST
    s = load()
    out = resolve(s, detected)
    LAST = out if out == "pin2dmd" or (out in ("zedmd", "web") and bridge_dir()) else "lcd"
    if LAST == "web":
        LAST = "zedmd"          # the game hides its screen DMD: the pictures go to the page
    shown = "lcd" if LAST == "lcd" else out        # a device without its bridge falls back to the screen DMD
    looks = look_args(s, bundle, shown)
    if out == "pin2dmd":
        return [f"--pin2dmd={s['color']}"], looks
    if out not in ("zedmd", "web"):
        if effective_look(s, bundle, "lcd") and not any(a.startswith("--dmd-preview") for a in looks):
            prepare_preview()
            looks = looks + ["--dmd-preview=" + PREVIEW_PNG]       # the page's view of the screen DMD
        return [], looks
    d = bridge_dir()
    if not d:
        print(f"dmd: the output is {out} but dmd_bridge was not found (MPF_DMD_BRIDGE_DIR, native/bin/<arch>/dmd_bridge): the game shows "
              "its DMD on the screen instead", file=sys.stderr)
        return [], look_args(s, bundle, "lcd")           # no bridge on this system: the screen DMD
    user = looks + ["--zedmd-shades", "--zedmd-feed=" + os.path.join(d, BRIDGE)]
    if out == "web":
        prepare_preview()
        user += ["--zedmd-feed-arg=--rgb-out", "--zedmd-feed-arg=" + PREVIEW]
    rom = chosen_serum(game_id, bundle, s)
    if rom:
        lib = serum_lib(d)
        if lib:
            for a in ("--serum-lib", lib, "--rom", rom, "--altcolor", SERUM):
                user.append("--zedmd-feed-arg=" + a)
    return [f"--zedmd={s['color']}"], user


def prepare_preview():
    """The folder of the picture file, in RAM and writable by the game's user."""
    try:
        d = os.path.dirname(PREVIEW)
        os.makedirs(d, exist_ok=True)
        os.chmod(d, 0o777)
        for f in (PREVIEW, PREVIEW_PNG):
            if os.path.exists(f):
                os.remove(f)
    except OSError:
        pass


def preview_frame():
    """(width, height, rgb888 bytes) of the last picture the bridge wrote, or None (no game, no picture yet, or one being written)."""
    try:
        if time.time() - os.path.getmtime(PREVIEW) > PREVIEW_MAX_AGE:
            return None
        with open(PREVIEW, "rb") as f:
            data = f.read(300000)
    except OSError:
        return None
    size = PREVIEW_SIZES.get(len(data))
    return (size[0], size[1], data) if size else None


def preview_image():
    """The PNG bytes of the screen DMD the dmd_out add-on last wrote (`--dmd-preview=`), or None when the game is not running."""
    try:
        if time.time() - os.path.getmtime(PREVIEW_PNG) > PREVIEW_MAX_AGE:
            return None
        with open(PREVIEW_PNG, "rb") as f:
            data = f.read(4000000)
    except OSError:
        return None
    return data if data.startswith(b"\x89PNG") else None


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
