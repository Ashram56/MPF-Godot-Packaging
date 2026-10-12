#!/usr/bin/env python3
"""Install MPF, MPF Monitor, Godot and GMC, with our fixes, on Windows, macOS or Linux (x86_64 or arm64).
Standard library only; the installers in install/ run it once Python 3.11 and Git are there.

    python -m mpf_godot setup                  # everything; safe to re-run (steps in place are skipped)
    python -m mpf_godot setup --no-monitor     # without MPF Monitor (mpf-monitor, Qt)
    python -m mpf_godot setup --dry-run        # print the plan (URLs, paths) and change nothing
    python -m mpf_godot setup --dry-run --os windows --arch x86_64   # the plan for another host

Steps: .venv/ with the pinned MPF (and MPF Monitor with its missing .ui files); Godot (official build for the
host) in toolchain/godot/; the GMC add-on in toolchain/addons/mpf-gmc/, patched (mpf_godot/gmc_patch.py); a check
that both start. Versions, paths and the reason for every pin: mpf_godot/toolchain.py.
"""
import argparse
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mpf_godot import fsutil, gmc_patch  # noqa: E402
from mpf_godot import toolchain as tc  # noqa: E402


class Setup:

    def __init__(self, args):
        self.args = args
        self.os = tc.host_os(args.os)
        self.arch = tc.host_arch(args.arch)
        self.native = args.os is None and args.arch is None
        self.dry = args.dry_run or not self.native

    def say(self, text):
        print(text, flush=True)

    def run(self, cmd, **kw):
        self.say("   $ " + " ".join(cmd))
        if not self.dry:
            subprocess.run(cmd, check=True, **kw)

    # ------------------------------------------------------------------ steps

    def venv(self):
        self.say("== Python venv ({}) with MPF {}".format(tc.venv_dir(), tc.MPF_VERSION))
        if sys.version_info[:2] < tc.PYTHON_MIN:
            raise SystemExit("Python {}.{}+ is needed, this is {}".format(*tc.PYTHON_MIN, sys.version.split()[0]))
        py = tc.venv_python(self.os)
        mpf = tc.venv_exe("mpf", self.os)
        reqs = list(tc.REQUIREMENTS) + list(self.args.extra or [])
        if self.args.monitor:
            reqs += tc.MONITOR_REQUIREMENTS
        if not os.path.exists(py) or self.dry:
            # a .venv whose Python is gone (the interpreter it was made from was removed or replaced) is remade:
            # platforms/linux.md "A dead venv"
            clear = ["--clear"] if not os.path.exists(py) and os.path.isdir(tc.venv_dir()) else []
            self.run([sys.executable, "-m", "venv"] + clear + [tc.venv_dir()])
        missing = self.dry or (not os.path.exists(mpf) or self.args.upgrade
                               or (self.args.monitor and not self.has_module(py, "mpfmonitor")))
        if missing:
            self.run([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
            self.run([py, "-m", "pip", "install", "--quiet"] + reqs)
        else:
            self.say("   in place")
        self.run([mpf, "--version"])
        if not self.dry:
            # `<venv python> -m mpf_godot ...` from any folder (a game's): this clone on the venv's path
            site = subprocess.run([py, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                                  capture_output=True, text=True, check=True).stdout.strip()
            with open(os.path.join(site, "mpf_godot.pth"), "w", encoding="utf-8") as f:
                f.write(tc.ROOT + "\n")
        if self.args.monitor:
            self.say("== MPF Monitor's window layouts ({} files missing from its PyPI release)".format(
                len(tc.MPF_MONITOR_UI_FILES)))
            self.say("   url:  " + tc.MPF_MONITOR_UI_URL)
            if not self.dry:
                install_monitor_ui(py)

    def has_module(self, py, name):
        return subprocess.run([py, "-c", "import " + name], capture_output=True).returncode == 0

    def godot(self):
        self.say("== Godot {} ({} {})".format(tc.GODOT_VERSION, self.os, self.arch))
        exe = tc.godot_path(self.os, self.arch)
        url = tc.godot_url(self.os, self.arch)
        self.say("   url:  " + url)
        self.say("   exe:  " + exe)
        if os.environ.get("GODOT") and self.native:
            self.say("   GODOT is set: using " + os.environ["GODOT"])
            exe = os.environ["GODOT"]
        elif os.path.exists(exe) and not self.dry:
            self.say("   in place")
        elif not self.dry:
            os.makedirs(tc.godot_dir(), exist_ok=True)
            unzip(download(url), tc.godot_dir(), self.os)
            if self.os != "windows":
                os.chmod(exe, os.stat(exe).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if self.os == "linux" and not self.dry and not os.environ.get("GODOT"):
            link = os.path.join(tc.godot_dir(), "godot")       # a short name for scripts and docs
            if os.path.lexists(link):
                os.remove(link)
            os.symlink(os.path.relpath(exe, tc.godot_dir()), link)
        self.run([exe, "--headless", "--version"])

    def gmc(self):
        self.say("== GMC add-on {} ({})".format(tc.GMC_VERSION, tc.gmc_dir()))
        self.say("   url:  " + tc.GMC_ZIP)
        if self.dry:
            self.say("   then: patched with " + ", ".join(gmc_patch.FIX_IDS) + " (fixes/gmc/)")
            return
        if os.path.exists(os.path.join(tc.gmc_dir(), "plugin.cfg")):
            self.say("   in place")
        else:
            fetch_gmc(tc.gmc_dir(), self.say)
        self.say("   patch: " + gmc_patch.patch(tc.gmc_dir(), quiet=True))

    def proc(self):
        self.say("== P-ROC driver: libpinproc + pypinproc")
        if self.os == "windows":
            self.say("   Windows: MPF ships pypinproc; install/install_windows.ps1 -Proc adds the VC++ runtime and "
                     "checks FTDI's D2XX driver (platforms/windows.md)")
            return
        cmd = ["bash", os.path.join(tc.ROOT, "install", "build_pinproc.sh"), "--python", tc.venv_python(self.os)]
        if self.dry:
            cmd.append("--dry-run")
            self.say("   $ " + " ".join(cmd))
            return
        subprocess.run(cmd, check=True)


def download(url):
    """The bytes at url. urllib first; curl (Windows 10+, macOS, Linux) when Python lacks CA certificates
    (python.org builds on macOS before 'Install Certificates': platforms/macos.md)."""
    print("   downloading " + url, flush=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError:
        raise
    except OSError as e:
        curl = shutil.which("curl")
        if not curl:
            raise
        print("   urllib failed ({}), retrying with curl".format(e), flush=True)
        r = subprocess.run([curl, "-fsSL", url], stdout=subprocess.PIPE)
        if r.returncode:
            raise OSError("curl could not download {} (exit code {})".format(url, r.returncode))
        return r.stdout


def fetch_gmc(dest, say=print):
    """GMC's addons/mpf-gmc from the release zip, else a git clone of the tag."""
    prefix = "mpf-gmc-{}/addons/mpf-gmc/".format(tc.GMC_VERSION)
    try:
        if not extract_folder(download(tc.GMC_ZIP), prefix, dest):
            raise SystemExit("no {} in {}".format(prefix, tc.GMC_ZIP))
    except (OSError, zipfile.BadZipFile) as e:
        if not shutil.which("git"):
            raise
        say("   zip download failed ({}), cloning with git".format(e))
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "-c", "advice.detachedHead=false", "clone", "--quiet", "--depth", "1",
                            "--branch", "v" + tc.GMC_VERSION, tc.GMC_GIT, os.path.join(tmp, "gmc")], check=True)
            fsutil.copy_tree(os.path.join(tmp, "gmc", "addons", "mpf-gmc"), dest)


def install_monitor_ui(py):
    """Put mpf-monitor's core/ui/*.ui files into the environment of py when they are missing; returns how many."""
    out = subprocess.run([py, "-c", "import mpfmonitor, os; print(os.path.dirname(mpfmonitor.__file__))"],
                         capture_output=True, text=True, check=True)
    ui_dir = os.path.join(out.stdout.strip(), "core", "ui")
    os.makedirs(ui_dir, exist_ok=True)
    added = 0
    for name in tc.MPF_MONITOR_UI_FILES:
        dst = os.path.join(ui_dir, name)
        if os.path.exists(dst):
            continue
        data = download(tc.MPF_MONITOR_UI_URL + name)
        if b"<ui" not in data[:200]:
            raise SystemExit("{} is not a Qt Designer file".format(tc.MPF_MONITOR_UI_URL + name))
        with open(dst, "wb") as f:
            f.write(data)
        added += 1
    print("   {} added, {} in place ({})".format(added, len(tc.MPF_MONITOR_UI_FILES) - added, ui_dir), flush=True)
    return added


def extract_folder(data, prefix, dest):
    """Unpack the files under prefix ("top/sub/") of a zip into dest; returns how many."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if n.startswith(prefix) and not n.endswith("/")]
        for name in names:
            dst = os.path.join(dest, *name[len(prefix):].split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(z.read(name))
    return len(names)


def unzip(data, dest, os_name):
    if os_name == "macos" and shutil.which("ditto"):
        # ditto keeps the app bundle's permissions, symlinks and code signature
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(data)
        try:
            subprocess.run(["ditto", "-x", "-k", f.name, dest], check=True)
        finally:
            os.unlink(f.name)
        return
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            z.extract(info, dest)
            mode = info.external_attr >> 16
            if mode and os_name != "windows":
                os.chmod(os.path.join(dest, info.filename), mode & 0o777)


def parser():
    p = argparse.ArgumentParser(prog="python -m mpf_godot setup", description=__doc__.split("\n")[0])
    p.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    p.add_argument("--os", choices=["windows", "macos", "linux"], help="plan for another OS (implies --dry-run)")
    p.add_argument("--arch", choices=["x86_64", "arm64"], help="plan for another CPU (implies --dry-run)")
    p.add_argument("--monitor", dest="monitor", action="store_true",
                   help="install MPF Monitor {} (the default)".format(tc.MPF_MONITOR_VERSION))
    p.add_argument("--no-monitor", dest="monitor", action="store_false", help="leave MPF Monitor out")
    p.set_defaults(monitor=True)
    p.add_argument("--proc", action="store_true", help="also the P-ROC driver (builds libpinproc/pypinproc on "
                                                       "Linux and macOS)")
    p.add_argument("--extra", action="append", metavar="REQ",
                   help="another pip requirement for the venv (repeatable), e.g. --extra pillow")
    p.add_argument("--upgrade", action="store_true", help="re-run pip install even if MPF is there")
    p.add_argument("--skip-godot", action="store_true", help="no Godot or GMC (MPF only)")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    s = Setup(args)
    s.say("MPF + Godot toolchain in {} on {} {}{}".format(tc.ROOT, s.os, s.arch, " (dry run)" if s.dry else ""))
    s.venv()
    if not args.skip_godot:
        s.godot()
        s.gmc()
    if args.proc:
        s.proc()
    s.say("Done.")
    if not s.dry:
        s.say(tc.summary())
        s.say("A game: `{} -m mpf_godot addons <game folder>` copies the patched GMC (and with --video the video "
              "add-ons) into it; `{} -m mpf_godot run <game folder>` starts Godot then MPF.".format(
                  tc.venv_python(), tc.venv_python()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
