#!/usr/bin/env python3
"""The PuP Pack part of the workspace: setup.py and run.py call it, or run it on its own.

    python scripts/pup_setup.py            # the pack's submodule, an ffmpeg with Theora, the converted media
                                           # (Windows: the native_video add-on, Linux: GDE GoZen, which
                                           # play the mp4s as they are)
    python scripts/pup_setup.py --status   # one line: is the PuP on, and if not why
    python scripts/pup_setup.py --pup-zip PACK.zip   # the pack from a zip (a file or an https URL) instead of
                                                     # the submodule; <env>_PUP_ZIP=PACK.zip does the
                                                     # same for setup.py and the installers

Kept out of setup.py and run.py (the game's files, one-line hooks only). Vendored from
Ashram56/Stern-SAM-Decryption tools/pup/runtime: a game sets everything in game/pup.cfg ([pup] env, pack_dir,
media_dir, submodule, pack_repo), it does not edit this file.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: E402
import toolchain as tc  # noqa: E402

sys.path.insert(0, tc.GAME)
from pup_runtime import settings  # noqa: E402


def status():
    """(on, text): whether Godot will start the PuP windows, and a line saying so or what is missing."""
    cfg = settings.load()
    if not cfg["pup"].get("enabled", False):
        return False, "PuP off ([pup] enabled=false or {}=0): original game only".format(settings.env_name(cfg))
    pack, media = settings.pack_dir(cfg), settings.media_dir(cfg)
    if not os.path.exists(os.path.join(pack, "triggers.pup")):
        return False, ("PuP off: no PuP Pack in {} (run `python scripts/setup.py`, or "
                       "`git submodule update --init {}`)".format(os.path.relpath(pack, tc.ROOT), submodule(cfg)))
    if not os.path.exists(os.path.join(media, "manifest.json")):
        return False, ("PuP off: the pack's videos are not converted yet (run `python scripts/setup.py`, or "
                       "`python scripts/pup_setup.py`)")
    pup = cfg["pup"]
    names = [n for n in pup.get("windows", ["backglass", "dmd", "topper"]) if cfg.get(n, {}).get("enabled", True)
             and (pup.get("third_screen", True) or n not in pup.get("optional", []))]
    music = "the pack's music" if pup.get("ost_music", True) else "ROM music"
    return True, "PuP on: {} windows, {}".format(", ".join(names), music)


def submodule(cfg):
    return cfg["pup"].get("submodule", "pup_pack")


def env(what):
    return settings.env_name(settings.load(), what)


NATIVE_SRC = os.path.join(tc.ROOT, "pup_addons", "native_video")
NATIVE_DST = os.path.join(tc.GAME, "addons", "native_video")
NATIVE_MIN_GODOT = (4, 6)           # native_video.gdextension compatibility_minimum


GOZEN_SRC = os.path.join(tc.ROOT, "pup_addons", "gde_gozen")
GOZEN_DST = os.path.join(tc.GAME, "addons", "gde_gozen")


def native_video(os_name=None):
    """True where the PuP plays the pack's mp4s with the native_video add-on (Windows and macOS, Godot 4.6+):
    Godot's own player only does Theora, so elsewhere the videos are converted (or played by GoZen, gozen()).
    <env>_NATIVE_VIDEO=0 converts them everywhere. Only where the game carries the add-on (pup_addons/)."""
    godot = tuple(int(n) for n in tc.GODOT_VERSION.split(".")[:2])
    if os.environ.get(env("NATIVE_VIDEO")) == "0":
        return False
    return tc.host_os(os_name) in ("windows", "macos") and godot >= NATIVE_MIN_GODOT and os.path.isdir(NATIVE_SRC)


def platform_gozen():
    """True when game/addons/gde_gozen is already there with its extension file: a prebuilt bundle's `platform_addons`
    (the platform installs its own GoZen build, none is kept in the game's repository). It is kept, not removed."""
    return os.path.isfile(os.path.join(GOZEN_DST, "gozen.gdextension"))


def gozen(os_name=None, arch=None):
    """True where the PuP plays the pack's mp4s with GDE GoZen (Linux x86_64 and arm64: FFmpeg, with the Jetson's
    hardware decoder when libnvmpi is installed, see pup_addons/gde_gozen/README.md). <env>_GOZEN=0 converts
    the videos to Theora instead. Only where the game carries the add-on (pup_addons/gde_gozen)."""
    if os.environ.get(env("GOZEN"), "").strip().lower() in ("0", "false", "no", "off"):
        return False
    host, cpu = tc.host_os(os_name), tc.host_arch(arch)
    return ((host == "linux" and cpu in ("x86_64", "arm64")) or (host == "windows" and cpu == "x86_64")) \
        and (os.path.isdir(GOZEN_SRC) or platform_gozen())


def register_extension(addon_dir):
    """Lists the add-on's .gdextension in game/.godot/extension_list.cfg. Godot loads a GDExtension only once an
    editor import has listed it there: a game that is only run (never opened in the editor) after the add-on is
    copied finds no GoZenVideo / NativeVideoStream class and falls back to Theora (observed, LOTR 2026-11-21)."""
    lst = os.path.join(tc.GAME, ".godot", "extension_list.cfg")
    have = open(lst, encoding="utf-8").read().split() if os.path.exists(lst) else []
    new = ["res://addons/{}/{}".format(os.path.basename(addon_dir), f) for f in sorted(os.listdir(addon_dir))
           if f.endswith(".gdextension")]
    new = [line for line in new if line not in have]
    if new:
        os.makedirs(os.path.dirname(lst), exist_ok=True)
        with open(lst, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(line + "\n" for line in have + new))


def install_native_video():
    """Copies pup_addons/native_video (the build with the gdzig heap fix, see its FIX.md) to game/addons/."""
    say("   native_video add-on -> game/addons/native_video (the pack's mp4s play without conversion)")
    fsutil.copy_tree(NATIVE_SRC, NATIVE_DST)
    register_extension(NATIVE_DST)


def install_gozen():
    """Copies pup_addons/gde_gozen (GoZen built for this repo, see its README.md) to game/addons/."""
    if not os.path.isdir(GOZEN_SRC):
        say("   GDE GoZen add-on: the platform's, already in game/addons/gde_gozen (the pack's mp4s play without conversion)")
        return
    say("   GDE GoZen add-on -> game/addons/gde_gozen (the pack's mp4s play without conversion)")
    fsutil.copy_tree(GOZEN_SRC, GOZEN_DST)
    register_extension(GOZEN_DST)


def say(text):
    print(text, flush=True)


def ensure_ffmpeg(py):
    """Installs imageio-ffmpeg in the venv unless an ffmpeg with libtheora is there for gen_pup.py."""
    for exe in (os.environ.get("FFMPEG"), shutil.which("ffmpeg")):
        if exe and "libtheora" in subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True,
                                                 text=True).stdout:
            return
    if subprocess.run([py, "-c", "import imageio_ffmpeg"], capture_output=True).returncode:
        say("   no ffmpeg with Theora: installing imageio-ffmpeg in the venv")
        subprocess.run([py, "-m", "pip", "install", "--quiet", "imageio-ffmpeg"], check=True)


ZIP_STAMP = ".pup_zip"               # in the pack folder: which zip it was extracted from
ZIP_CACHE = os.path.join(tc.ROOT, ".cache", "pup_pack.zip")


def pack_zip():
    """The zip given with --pup-zip or <env>_PUP_ZIP (a path or an http(s) URL), or None for the submodule."""
    return os.environ.get(env("PUP_ZIP"), "").strip() or None


def _fetch_zip(src, dry):
    if not src.lower().startswith(("http://", "https://")):
        path = os.path.abspath(os.path.expanduser(src))
        if not os.path.isfile(path):
            raise SystemExit("PuP Pack zip not found: {}".format(path))
        return path
    say("   downloading the PuP Pack zip: " + src)
    if dry:
        return None
    os.makedirs(os.path.dirname(ZIP_CACHE), exist_ok=True)
    tmp = ZIP_CACHE + ".part"
    with urllib.request.urlopen(src) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out)
    os.replace(tmp, ZIP_CACHE)
    return ZIP_CACHE


def _digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def extract_pack(zip_path, pack):
    """Extracts the folder of the zip that holds triggers.pup (the pack itself, at any depth, e.g.
    tf_180/ or PUPVideos/tf_180/) into `pack`. Returns the number of files written."""
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        tops = sorted((n for n in names if n.replace("\\", "/").rsplit("/", 1)[-1].lower() == "triggers.pup"),
                      key=lambda n: n.count("/"))
        if not tops:
            raise SystemExit("{} holds no triggers.pup: not a PuP Pack zip".format(zip_path))
        prefix = tops[0].replace("\\", "/")[:-len("triggers.pup")]
        tmp = tempfile.mkdtemp(prefix="pup_pack_", dir=os.path.dirname(os.path.abspath(pack)))
        try:
            count = _extract(z, names, prefix, tmp)
        except BaseException:
            fsutil.remove_dir(tmp)
            raise
    if os.path.isdir(pack):
        fsutil.remove_dir(pack)
    os.replace(tmp, pack)
    return count


def _extract(z, names, prefix, tmp):
    count = 0
    for name in names:
        rel = name.replace("\\", "/")
        if not rel.startswith(prefix):
            continue
        rel = rel[len(prefix):]
        parts = rel.split("/")
        if not rel or rel.startswith("/") or ".." in parts or ":" in parts[0]:
            continue                        # nothing may land outside the pack folder
        dst = os.path.join(tmp, *parts)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with z.open(name) as src, open(dst, "wb") as out:
            shutil.copyfileobj(src, out)
        count += 1
    return count


def pack_from_zip(src, pack, dry=False):
    """The pack from a zip instead of the submodule (so a user installs the pack they downloaded from its
    author). Re-extracts only when the zip changed. Returns 0, or 1 when the pack cannot be used."""
    say("   PuP Pack from a zip ({} / --pup-zip): ".format(env("PUP_ZIP")) + src)
    stamp = os.path.join(pack, ZIP_STAMP)
    if os.path.exists(os.path.join(pack, "triggers.pup")) and not os.path.exists(stamp):
        say("   {} is already there (the pack's submodule): the zip is not used; delete that folder to use "
            "it".format(os.path.relpath(pack, tc.ROOT)))
        return 0
    path = _fetch_zip(src, dry)
    if dry:
        say("   (dry run) would extract it into " + os.path.relpath(pack, tc.ROOT))
        return 0
    digest = _digest(path)
    if os.path.exists(stamp):
        with open(stamp, encoding="utf-8") as f:
            if f.read().split()[:1] == [digest]:
                say("   in place (same zip)")
                return 0
    os.makedirs(os.path.dirname(pack), exist_ok=True)
    count = extract_pack(path, pack)
    with open(os.path.join(pack, ZIP_STAMP), "w", encoding="utf-8") as f:
        f.write("{} {}\n".format(digest, src))
    say("   {} files -> {}".format(count, os.path.relpath(pack, tc.ROOT)))
    return 0


def setup(py=None, dry=False):
    py = py or tc.python()
    cfg = settings.load()
    say("== PuP Pack ({} submodule, videos converted for Godot into {})".format(
        submodule(cfg), os.path.relpath(settings.media_dir(cfg), tc.ROOT)))
    if not cfg["pup"].get("enabled", True):
        say("   " + status()[1])
        return 0
    pack = settings.pack_dir(cfg)
    if pack_zip():
        if pack_from_zip(pack_zip(), pack, dry):
            return 1
    elif not os.path.exists(os.path.join(pack, "triggers.pup")):
        cmd = ["git", "submodule", "update", "--init", "--depth", "1", submodule(cfg)]
        say("   $ " + " ".join(cmd))
        if not dry and subprocess.run(cmd, cwd=tc.ROOT).returncode:
            say("   could not fetch the PuP Pack (private repo: your git needs access to {}; or give the "
                "author's zip with {}=<zip>). The game runs without the PuP.".format(
                    cfg["pup"].get("pack_repo", "the pack's repository"), env("PUP_ZIP")))
            return 1
    if dry:
        return 0
    ensure_ffmpeg(py)
    native = native_video() or gozen()
    # Windows gets both: GoZen plays, native_video is one setting away ([pup] video_player, game/pup/pup_player.gd)
    for wanted, install, addon in ((gozen(), install_gozen, GOZEN_DST),
                                   (native_video(), install_native_video, NATIVE_DST)):
        if wanted:
            install()
        elif os.path.isdir(addon):        # a loaded add-on would play the mp4s instead of the conversions
            fsutil.remove_dir(addon)
    if not native:
        say("   converting the pack's videos (the first time takes a while; later runs only redo changed files)")
    code = subprocess.run([py, os.path.join(tc.ROOT, "scripts", "gen_pup.py")] + (["--native"] if native else []),
                          cwd=tc.ROOT).returncode
    say("   " + status()[1])
    return code


if __name__ == "__main__":
    if sys.argv[1:] == ["--status"]:
        on, text = status()
        say(text)
        sys.exit(0 if on else 1)
    if sys.argv[1:2] == ["--pup-zip"] and len(sys.argv) == 3:
        os.environ[env("PUP_ZIP")] = sys.argv[2]
    elif sys.argv[1:]:
        sys.exit(__doc__)
    sys.exit(setup())
