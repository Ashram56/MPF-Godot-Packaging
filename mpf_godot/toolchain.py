"""The pinned toolchain and every per-OS path, in one place. Standard library only (it runs before any venv exists).

    <root>/.venv/                          Python venv: Scripts\\python.exe on Windows, bin/python elsewhere
    <root>/toolchain/godot/                Godot, unpacked from the official release zip for the host:
                                             Windows  Godot_v<ver>-stable_win64.exe      (windows_arm64.exe on ARM)
                                             macOS    Godot.app/Contents/MacOS/Godot     (universal)
                                             Linux    Godot_v<ver>-stable_linux.x86_64   (linux.arm64 on ARM)
    <root>/toolchain/addons/mpf-gmc/       the GMC add-on, patched (fixes/gmc/), ready to copy into a game
    <root>/addons/gde_gozen, native_video  video add-ons with our fixes (prebuilt, in git; build/ rebuilds them)

<root> is this repository's clone. Environment overrides: GODOT (a Godot you installed yourself),
MPF_GODOT_VENV (the venv, for a Docker image that keeps it outside a bind mount).
Every pin carries its reason here, and a fix document in fixes/ when it works around a bug.
"""
import os
import platform
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLCHAIN = os.path.join(ROOT, "toolchain")

PYTHON_MIN = (3, 10)
PYTHON_PREFERRED = (3, 11)       # what the installers install: every pin below is tested on it
MPF_VERSION = "0.80.1"
GODOT_VERSION = "4.6.3"          # the native_video add-on needs 4.6; GMC 1.0 needs 4.5+
GMC_VERSION = "1.0.0"
MPF_MONITOR_VERSION = "1.0.0"

# ruamel.yaml.clib 0.2.15 names its metadata ruamel_yaml_clib, which MPF's pkg_resources (setuptools 72) cannot
# match to ruamel.yaml's requirement: `mpf` fails to start once mpf-monitor is installed. Python 3.13+ does not
# use the C library. fixes/mpf/ruamel-yaml-clib-0.2.15.md
REQUIREMENTS = ["mpf==" + MPF_VERSION, 'ruamel.yaml.clib==0.2.14; python_version < "3.13"']
# PyQt6 6.8+ ships Linux arm64 wheels for glibc 2.39+ only; 6.7's need glibc 2.28 (JetPack 5: 2.31, JetPack 6:
# 2.35). Without a wheel pip builds the sdist, which needs qmake and fails. fixes/mpf-monitor/pyqt6-arm64-glibc.md
MONITOR_REQUIREMENTS = ["mpf-monitor==" + MPF_MONITOR_VERSION,
                        'PyQt6>=6.4.2,<6.8; sys_platform == "linux" and platform_machine == "aarch64"']
# mpf-monitor 1.0.0 on PyPI (wheel and sdist) lacks its Qt Designer files: `mpf monitor` stops with
# "searchable_tree.ui: No such file". Fetched from the release's git tag. fixes/mpf-monitor/missing-ui-files.md
MPF_MONITOR_UI_FILES = ("events_table.ui", "inspector.ui", "searchable_table.ui", "searchable_tree.ui")
MPF_MONITOR_UI_URL = ("https://raw.githubusercontent.com/missionpinball/mpf-monitor/v{}/mpfmonitor/core/ui/"
                      .format(MPF_MONITOR_VERSION))

BCP_PORT = 5050             # GMC (Godot) is the BCP server, MPF connects to it
MONITOR_PORT = 5051         # MPF's own BCP server, MPF Monitor connects to it

# Godot from GitHub releases (downloads.tuxfamily.org is unreachable from some networks and no longer updated)
GODOT_RELEASES = "https://github.com/godotengine/godot/releases/download/{0}-stable/".format(GODOT_VERSION)
GMC_ZIP = "https://github.com/missionpinball/mpf-gmc/archive/refs/tags/v{0}.zip".format(GMC_VERSION)
GMC_GIT = "https://github.com/missionpinball/mpf-gmc"


def host_os(system=None):
    """'windows', 'macos' or 'linux' (system defaults to platform.system())."""
    system = (system or platform.system()).lower()
    if system.startswith(("windows", "cygwin", "msys")) or system == "nt":
        return "windows"
    if system in ("darwin", "macos", "mac"):
        return "macos"
    if system == "linux":
        return "linux"
    raise SystemExit("unsupported OS {!r}: Windows, macOS or Linux only".format(system))


def host_arch(machine=None):
    """'x86_64' or 'arm64' (machine defaults to platform.machine())."""
    machine = (machine or platform.machine()).lower()
    if machine in ("x86_64", "amd64", "x64", "x86-64"):
        return "x86_64"
    if machine in ("arm64", "aarch64", "armv8", "armv8l"):
        return "arm64"
    raise SystemExit("unsupported CPU {!r}: x86_64 or arm64 only".format(machine))


# ---------------------------------------------------------------------- Python venv

def venv_dir(root=ROOT):
    """root/.venv, or $MPF_GODOT_VENV for this clone when it is set."""
    if os.environ.get("MPF_GODOT_VENV") and root == ROOT:
        return os.environ["MPF_GODOT_VENV"]
    return os.path.join(root, ".venv")


def venv_bin(os_name=None, root=ROOT):
    return os.path.join(venv_dir(root), "Scripts" if host_os(os_name) == "windows" else "bin")


def venv_exe(name, os_name=None, root=ROOT):
    """A console script or the interpreter of the venv: venv_exe('python'), venv_exe('mpf')."""
    exe = name + ".exe" if host_os(os_name) == "windows" else name
    return os.path.join(venv_bin(os_name, root), exe)


def venv_python(os_name=None, root=ROOT):
    return venv_exe("python", os_name, root)


def python():
    """The venv's Python when it exists, else the one running this script."""
    exe = venv_python()
    return exe if os.path.exists(exe) else sys.executable


def mpf_command():
    """How to start MPF: the venv's mpf script, else `python -m mpf` from the running interpreter."""
    exe = venv_exe("mpf")
    return [exe] if os.path.exists(exe) else [python(), "-m", "mpf"]


# ---------------------------------------------------------------------- Godot

def godot_asset(os_name=None, arch=None):
    """The release zip of the official Godot build for this OS and CPU."""
    os_name, arch = host_os(os_name), host_arch(arch)
    suffix = {("windows", "x86_64"): "win64.exe", ("windows", "arm64"): "windows_arm64.exe",
              ("macos", "x86_64"): "macos.universal", ("macos", "arm64"): "macos.universal",
              ("linux", "x86_64"): "linux.x86_64", ("linux", "arm64"): "linux.arm64"}[(os_name, arch)]
    return "Godot_v{}-stable_{}.zip".format(GODOT_VERSION, suffix)


def godot_url(os_name=None, arch=None):
    return GODOT_RELEASES + godot_asset(os_name, arch)


def godot_dir(root=ROOT):
    return os.path.join(root, "toolchain", "godot")


def godot_relpath(os_name=None, arch=None):
    """The executable inside toolchain/godot/, as the release zip unpacks it."""
    if host_os(os_name) == "macos":
        return os.path.join("Godot.app", "Contents", "MacOS", "Godot")
    return godot_asset(os_name, arch)[:-len(".zip")]       # the zip holds one file named like itself


def godot_path(os_name=None, arch=None, root=ROOT):
    """The Godot executable: $GODOT if set, else the pinned build in toolchain/godot/."""
    if os.environ.get("GODOT") and os_name is None:
        return os.environ["GODOT"]
    return os.path.join(godot_dir(root), godot_relpath(os_name, arch))


# ---------------------------------------------------------------------- add-ons

def gmc_dir(root=ROOT):
    """The patched GMC add-on this clone keeps, copied into a game by `mpf_godot addons`."""
    return os.path.join(root, "toolchain", "addons", "mpf-gmc")


def addon_dir(name, root=ROOT):
    """A video add-on shipped in this repository (gde_gozen, native_video)."""
    return os.path.join(root, "addons", name)


def gozen_supported(os_name=None, arch=None):
    """GDE GoZen (FFmpeg, hardware decoding): Linux x86_64 and arm64, Windows x86_64."""
    return (host_os(os_name), host_arch(arch)) in (("linux", "x86_64"), ("linux", "arm64"), ("windows", "x86_64"))


def native_video_supported(os_name=None, arch=None):
    """native_video (Media Foundation / AVFoundation): Windows and macOS."""
    return host_os(os_name) in ("windows", "macos")


# ---------------------------------------------------------------------- display

def needs_virtual_display(os_name=None, environ=None):
    """True on Linux without a display server: run Godot under Xvfb (xvfb-run)."""
    environ = os.environ if environ is None else environ
    return host_os(os_name) == "linux" and not (environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY"))


def is_jetson(release="/etc/nv_tegra_release"):
    return os.path.exists(release)


def summary():
    lines = [("host", "{} {}".format(host_os(), host_arch())),
             ("python", "{} ({})".format(venv_python(), "present" if os.path.exists(venv_python()) else "missing")),
             ("mpf", "{} ({})".format(venv_exe("mpf"), "present" if os.path.exists(venv_exe("mpf")) else "missing")),
             ("godot", "{} ({})".format(godot_path(), "present" if os.path.exists(godot_path()) else "missing")),
             ("gmc", "{} ({})".format(gmc_dir(), "present" if os.path.exists(os.path.join(gmc_dir(), "plugin.cfg"))
                                      else "missing")),
             ("versions", "MPF {}, Godot {}, GMC {}, MPF Monitor {}".format(
                 MPF_VERSION, GODOT_VERSION, GMC_VERSION, MPF_MONITOR_VERSION))]
    return "\n".join("{:<9} {}".format(k, v) for k, v in lines)


if __name__ == "__main__":
    print(summary())
