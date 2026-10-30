"""Settings and helpers shared by the MPF setup modules (mpf_netconfig, mpf_games, mpf_web), standard library only.

Everything here is read from the environment (set by /etc/default/mpf-netconfig) and from /etc/mpf-readonly.conf, once, when
the module is imported. A test changes a value by setting the attribute on this module: the other modules read it as `C.NAME`.
"""
import contextlib
import os
import subprocess
import sys


def read_kv(path):
    """KEY=VALUE lines of a text file (comments and quotes dropped); {} when it cannot be read."""
    out = {}
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return out


CONF = os.environ.get("MPF_NETCONFIG_FILE", "/boot/firmware/mpf-network.txt")
USER = os.environ.get("MPF_USER", "pi")
WLAN = os.environ.get("MPF_WLAN", "wlan0")
PORT = int(os.environ.get("MPF_WEB_PORT", "8080"))
GAMES = os.environ.get("MPF_GAMES_DIR", "/opt/games")
GAME_ENV = os.environ.get("MPF_GAME_ENV", "/etc/default/mpf-game")
GOZEN_SO = os.environ.get("MPF_GOZEN_SO", "")
GAME_OVERRIDE = os.environ.get("MPF_GAME_OVERRIDE", "")


def find_platform_dir(user=None, here=None):
    """This platform's checkout: MPF_PLATFORM_DIR, else the copy the image builds put in the game user's home (~/MPF-Godot), else the
    checkout these files run from. The platform starts format 2 games with its `mpf_godot` package and installs its add-ons from it."""
    if os.environ.get("MPF_PLATFORM_DIR"):
        return os.environ["MPF_PLATFORM_DIR"]
    here = here or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for d in (os.path.join("/home", user or USER, "MPF-Godot"), "/opt/MPF-Godot", here):
        if os.path.isfile(os.path.join(d, "mpf_godot", "__init__.py")):
            return d
    return ""


PLATFORM_DIR = find_platform_dir()
GOZEN_NEEDS = os.environ.get("MPF_GOZEN_NEEDS", "v4l2m2m zero_copy").split()
RO_CONF = os.environ.get("MPF_READONLY_CONF", "/etc/mpf-readonly.conf")

RO = read_kv(RO_CONF)
READONLY = bool(RO)                              # the image runs in read-only production mode (common/readonly)
DATA = RO.get("MPF_DATA_MOUNT", "/data")         # its one read/write partition
BOOT_MOUNT = RO.get("MPF_BOOT_MOUNT", "")
# where this machine keeps what it writes: the data partition in read-only mode, ordinary folders otherwise
STATE_DIR = os.environ.get("MPF_STATE_DIR") or (os.path.join(DATA, "mpf") if READONLY else "/var/lib/mpf-netconfig")
UPLOADS = os.environ.get("MPF_UPLOAD_DIR") or (os.path.join(DATA, "uploads") if READONLY else "/var/lib/mpf-uploads")
PUPS = os.environ.get("MPF_PUP_DIR") or (os.path.join(DATA, "pups") if READONLY else "/var/lib/mpf-pups")      # PuP Pack library: zips and installed packs
INBOX = os.environ.get("MPF_INBOX_DIR") or (os.path.join(DATA, "inbox") if READONLY else "/var/lib/mpf-inbox")
JOB_FILE = os.environ.get("MPF_JOB_FILE", "/run/mpf-job.json")
VOLATILE_LOGS = "/var/log/mpf-game"              # the game's logs/ folder is a link to this folder in RAM
XDG_RAM = "/run/mpf-xdg"                         # Godot's user:// (logs, shader caches) in RAM
ARCH = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "x86_64", "amd64": "x86_64"}


def run(*cmd, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, **kw)
    except FileNotFoundError as e:      # a tool the image does not have: the caller sees a failed command, not a crash
        return subprocess.CompletedProcess(cmd, 127, "", str(e))


def read_conf(path=None):
    return read_kv(path or CONF)


@contextlib.contextmanager
def writable(path):
    """The mount that holds `path` is writable inside the block, then back as it was (read-only production mode: the boot
    partition and the root only open for the few writes that cannot go to the data partition)."""
    target = run("findmnt", "-n", "-o", "TARGET", "--target", path).stdout.strip() if READONLY else ""
    was_ro = bool(target) and "ro" in run("findmnt", "-n", "-o", "OPTIONS", target).stdout.strip().split(",")
    if was_ro and run("mount", "-o", "remount,rw", target).returncode:
        raise OSError(f"cannot make {target} writable")
    try:
        yield
    finally:
        if was_ro:
            os.sync()
            if run("mount", "-o", "remount,ro", target).returncode:
                print(f"{target} stays writable until the next reboot", file=sys.stderr)


def mode_status():
    """('production' | 'maintenance', stays_after_reboot) of a read-only image; None on an ordinary one."""
    if not READONLY:
        return None
    ro = "ro" in run("findmnt", "-n", "-o", "OPTIONS", "/").stdout.strip().split(",")
    return ("production" if ro else "maintenance", os.path.exists(os.path.join(DATA, "mpf", "maintenance")))


def set_mode(mode, stay=False):
    if not READONLY:
        raise ValueError("this image is not in read-only mode")
    if mode not in ("maintenance", "production"):
        raise ValueError("mode: maintenance or production")
    r = run("mpf-mode", mode, *(["--stay"] if stay and mode == "maintenance" else []))
    if r.returncode:
        raise ValueError((r.stderr or r.stdout).strip() or f"mpf-mode {mode} failed")
