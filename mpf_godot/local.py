#!/usr/bin/env python3
"""The local platform: install and play any game bundle on a Windows, macOS or Linux desktop the way a cabinet's image does it.

    python -m mpf_godot local install BUNDLE.tar.xz|URL [--sha256 HEX] [--user NAME]   the same steps as the setup page
    python -m mpf_godot local pup PACK.zip [--game GAME]       the author's PuP Pack, unpacked untouched, assigned to the game
    python -m mpf_godot local serum ROM.cROMc                  a Serum colourisation into the library (one per ROM name)
    python -m mpf_godot local dmd [--output lcd|zedmd|pin2dmd|auto] [--color #RRGGBB] [--serum GAME=ROM|none|default] [--port COM5]
    python -m mpf_godot local list | use GAME | remove GAME | settings [GAME] | set [--game GAME] KEY=VALUE ...
    python -m mpf_godot local start [GAME] [--dmd OUTPUT] [--seconds N] [--monitor] [--dry-run] [-- run.start arguments]
    python -m mpf_godot local doctor                          what is found: Godot, MPF, dmd_bridge, a ZeDMD
    python -m mpf_godot local build-bridge                    macOS/Linux: builds libzedmd, libserum and dmd_bridge here

The cabinet's own code does the work (common/netconfig: mpf_contract.py for format 2 bundles, mpf_dmd.py for the DMD output, mpf_games.py
for the library and the PuP Pack), so a game checked here starts the same way on a machine. What differs is only what a desktop is: no
systemd, no game user, no read-only root, the game in a window, and a ZeDMD found by dmd_bridge on any serial port (Windows: the prebuilt
native/prebuilt/windows-x86_64/dmd_bridge/, built by native/build_windows_bridge.sh). Everything is kept in MPF_LOCAL_DIR (default
`~/MPF-Local`): games/, pups/, serum/, state/. platforms/local.md.
"""
import argparse
import getpass
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mpf_godot import toolchain as tc  # noqa: E402

ROOT = tc.ROOT
LOCAL = os.path.abspath(os.environ.get("MPF_LOCAL_DIR") or os.path.join(os.path.expanduser("~"), "MPF-Local"))
DIRS = {"MPF_GAMES_DIR": "games", "MPF_STATE_DIR": "state", "MPF_PUP_DIR": "pups", "MPF_SERUM_DIR": "serum",
        "MPF_UPLOAD_DIR": "uploads", "MPF_INBOX_DIR": "inbox"}
# the cabinet's modules read their folders from the environment when they are imported: point them at the local folders first
for _k, _d in DIRS.items():
    os.environ.setdefault(_k, os.path.join(LOCAL, _d))
os.environ.setdefault("MPF_JOB_FILE", os.path.join(LOCAL, "state", "job.json"))
os.environ.setdefault("MPF_READONLY_CONF", os.path.join(LOCAL, "state", "no-readonly.conf"))
os.environ.setdefault("MPF_NETCONFIG_FILE", os.path.join(LOCAL, "state", "mpf-network.txt"))
os.environ.setdefault("MPF_PLATFORM_DIR", ROOT)
sys.path.insert(0, os.path.join(ROOT, "common", "netconfig"))
import mpf_bundlecheck as BC  # noqa: E402
import mpf_common as C  # noqa: E402
import mpf_contract as K  # noqa: E402
import mpf_dmd as DMD  # noqa: E402
import mpf_games as M  # noqa: E402

IS_WINDOWS = os.name == "nt"
ME = tc.host_arch()
OS = tc.host_os()


class Fail(SystemExit):
    pass


def say(text):
    print(text, flush=True)


def logged(fn, *args, **kw):
    """Run a helper of mpf_games that reports through its job log; print the log, turn its JobError into a message."""
    M.JOB["log"] = ""
    try:
        return fn(*args, **kw)
    except M.JobError as e:
        raise Fail(str(e))
    finally:
        if M.JOB["log"].strip():
            say(M.JOB["log"].rstrip())
        M.JOB["log"] = ""


# ---------------------------------------------------------------- files
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def opener(url, user=None):
    """urllib opener; with a user (a WebDAV share) the password comes from MPF_WEBDAV_PASSWORD, else it is asked once."""
    if not user:
        return urllib.request.build_opener()
    pw = os.environ.get("MPF_WEBDAV_PASSWORD") or getpass.getpass(f"password of {user} on {urllib.parse.urlsplit(url).netloc}: ")
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, url, user, pw)
    return urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(mgr), urllib.request.HTTPDigestAuthHandler(mgr))


def download(url, dest, user=None, quiet=False):
    with opener(url, user).open(url, timeout=60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        for chunk in iter(lambda: r.read(1 << 20), b""):
            f.write(chunk)
            done += len(chunk)
            if not quiet and total:
                print(f"\r   {done >> 20} / {total >> 20} MB", end="", flush=True)
        if not quiet and total:
            print()
    return dest


def fetch(src, user=None, want_sha=True):
    """(local path, expected sha256 or "", temporary) of a file or an http(s) URL; the `.sha256` beside it is read when there is one."""
    if re.match(r"^https?://", src):
        tmp = tempfile.mkdtemp(prefix="mpf-local-", dir=LOCAL)
        name = urllib.parse.unquote(os.path.basename(urllib.parse.urlsplit(src).path)) or "download"
        path = os.path.join(tmp, name)
        say(f"Downloading {src}")
        download(src, path, user)
        sha = ""
        if want_sha:
            try:
                download(src + ".sha256", path + ".sha256", user, quiet=True)
                sha = open(path + ".sha256").read().split()[0]
            except Exception:
                pass
        return path, sha, tmp
    if not os.path.isfile(src):
        raise Fail(f"no such file: {src}")
    sha = ""
    if want_sha and os.path.isfile(src + ".sha256"):
        sha = (open(src + ".sha256").read().split() or [""])[0]
    return os.path.abspath(src), sha, None


def is_link(path):
    """A symbolic link, or a junction on Windows (os.readlink reads both there)."""
    if os.path.islink(path):
        return True
    if IS_WINDOWS:
        try:
            os.readlink(path)
            return True
        except (OSError, ValueError):
            return False
    return False


def drop(path):
    """Remove a file, a link (never what it points to) or a folder."""
    if is_link(path):
        os.rmdir(path) if IS_WINDOWS and os.path.isdir(path) else os.remove(path)
    elif os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def make_link(target, link):
    """A folder link: a junction on Windows (no administrator rights needed), a symbolic link elsewhere."""
    drop(link)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if IS_WINDOWS:
        import _winapi
        _winapi.CreateJunction(os.path.abspath(target), os.path.abspath(link))
    else:
        os.symlink(os.path.abspath(target), link)


def check_sums(root):
    """SHA256SUMS of the bundle (`<hash>  <path>` lines), checked in Python (no sha256sum on Windows)."""
    bad = []
    with open(os.path.join(root, "SHA256SUMS"), encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split(None, 1)
            if len(parts) != 2:
                continue
            want, rel = parts[0], parts[1].lstrip("*").strip()
            p = os.path.join(root, *rel.split("/"))
            if not os.path.isfile(p) or sha256(p) != want.lower():
                bad.append(rel)
    if bad:
        raise Fail("SHA256SUMS: {} file(s) missing or changed, e.g. {}".format(len(bad), ", ".join(bad[:3])))


def unpack(archive, stage):
    with tarfile.open(archive, "r:*") as t:
        if hasattr(tarfile, "data_filter"):
            t.extractall(stage, filter="data")
        else:                       # Python before 3.11.4 (3.10): refuse absolute paths and ..
            for m in t.getmembers():
                if m.name.startswith(("/", "\\")) or ".." in re.split(r"[\\/]", m.name):
                    raise Fail(f"unsafe path in the archive: {m.name}")
            t.extractall(stage)


# ---------------------------------------------------------------- install a bundle
def host_ok(b):
    """A bundle for this computer: one without binaries ("all") runs on any desktop; one with binaries needs this CPU."""
    tgt = b.get("target") or {}
    arches = str(tgt.get("arch", "all")).split("+")
    if "all" in arches:
        return True, ""
    if ME not in arches:            # the arch says which GPU texture formats were imported (a bundle carries no binary)
        return False, f"this bundle's textures are for {tgt.get('arch')}, this computer is {ME}"
    return True, ""


def trial(root, b):
    """What keeps the unpacked bundle from starting (the page's checks, mpf_games.trial, without the game user)."""
    py = tc.python()
    if K.is_v2(b):
        game_dir = os.path.join(root, b.get("game_dir") or "game")
        return K.problems(b, root) or BC.problems(root, py, b, starts=BC.python_files(game_dir))
    bad = BC.problems(root, py, b)
    cmd = BC.check_command(b)
    if cmd and not bad:
        if cmd[0] in ("python3", "python"):
            cmd[0] = py
        env = dict(os.environ, MPF_BUNDLE_CHECK="1", **game_environment(b))
        try:
            r = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=BC.check_timeout(b))
            if r.returncode:
                bad.append(f"the game's own check (run.check) failed ({r.returncode}): " + (r.stdout + r.stderr).strip()[-600:])
        except subprocess.TimeoutExpired:
            bad.append(f"the game's own check (run.check): no answer after {BC.check_timeout(b)} s")
    return bad


def addon_source(name):
    """The platform's copy of an add-on: this checkout's addons/ (GoZen, dmd_out) or the patched GMC in toolchain/addons/."""
    marker = "gozen.gdextension" if name == "gde_gozen" else "plugin.cfg"
    for sub in ("addons", os.path.join("toolchain", "addons")):
        d = os.path.join(ROOT, sub, name)
        if os.path.isfile(os.path.join(d, marker)) or (name == "dmd_out" and os.path.isfile(os.path.join(d, "dmd_out.gd"))):
            return d
    return None


NATIVE = {"windows": r"\.windows\..*\.dll$", "macos": r"\.macos\..*\.dylib$", "linux": r"\.linux\..*\.so$"}


def install_addons(dest, b, game_dir):
    """The platform's add-ons a bundle names (`platform_addons`), with this computer's native files only; Godot is told about each
    native extension (.godot/extension_list.cfg), as the page does."""
    for name in b.get("platform_addons", []):
        src = addon_source(name)
        if not src:
            raise Fail(f"the bundle needs the platform's {name} and this checkout has none (run `python -m mpf_godot setup`)")
        dst = os.path.join(game_dir, "addons", name)
        shutil.rmtree(dst, ignore_errors=True)
        for base, _dirs, files in os.walk(src):
            rel = os.path.relpath(base, src)
            for f in files:
                if rel.split(os.sep)[0] == "bin" and re.search(r"\.(so|dll|dylib)$", f) and not re.search(NATIVE[OS], f):
                    continue
                t = os.path.join(dst, rel, f)
                os.makedirs(os.path.dirname(t), exist_ok=True)
                shutil.copy2(os.path.join(base, f), t)
        lst = os.path.join(game_dir, ".godot", "extension_list.cfg")
        for f in sorted(os.listdir(dst)):
            if f.endswith(".gdextension"):
                line = f"res://addons/{name}/{f}"
                have = open(lst).read().split() if os.path.isfile(lst) else []
                if line not in have:
                    os.makedirs(os.path.dirname(lst), exist_ok=True)
                    with open(lst, "a") as fh:
                        fh.write(line + "\n")
        say(f"   {name}: the platform's copy ({src})")


def godot_import(game_dir):
    """One headless import: the class cache gets the scripts of the platform's add-ons, and this computer's GPU formats are made."""
    exe = tc.godot_path()
    if not os.path.exists(exe):
        raise Fail(f"no Godot at {exe}: run `python -m mpf_godot setup` first")
    say("Importing the Godot project (first time: a few minutes)")
    r = subprocess.run([exe, "--headless", "--path", game_dir, "--import"], capture_output=True, text=True, timeout=1800)
    if r.returncode:
        raise Fail("the Godot import failed ({}): {}".format(r.returncode, (r.stdout + r.stderr).strip()[-800:]))


def carry_over(b, root, folder):
    """Settings, scores and the PuP link of the installed copy of the same game go to the new one (mpf_games.install_game)."""
    keep = b.get("keep_on_update", []) + ([K.PLATFORM_DIR] if K.is_v2(b) else [])
    dest = os.path.join(C.GAMES, folder)
    prev = {"path": dest} if os.path.isdir(dest) else M.previous_version(b, folder)
    if not prev:
        return
    for rel in keep:
        src, dst = os.path.join(prev["path"], rel), os.path.join(root, rel)
        if not os.path.lexists(src):
            continue
        drop(dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if is_link(src):
            make_link(os.path.realpath(src), dst)
        elif os.path.isdir(src):
            for base, dirs, files in os.walk(src):
                for d in list(dirs):            # a pack link inside a kept folder (.platform/pup) stays a link
                    p = os.path.join(base, d)
                    if is_link(p):
                        make_link(os.path.realpath(p), os.path.join(dst, os.path.relpath(p, src)))
                        dirs.remove(d)
                for f in files:
                    t = os.path.join(dst, os.path.relpath(os.path.join(base, f), src))
                    os.makedirs(os.path.dirname(t), exist_ok=True)
                    shutil.copy2(os.path.join(base, f), t)
        else:
            shutil.copy2(src, dst)
        say(f"   kept {rel}")


def install(src, sha=None, user=None, keep_old=True):
    path, side, tmp = fetch(src, user)
    try:
        want = (sha or side or "").lower()
        if want:
            say("Checking the archive's sha256")
            if sha256(path) != want:
                raise Fail("the archive's sha256 does not match: download it again")
        os.makedirs(C.GAMES, exist_ok=True)
        stage = os.path.join(C.GAMES, ".stage")
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage)
        say("Unpacking")
        unpack(path, stage)
        dirs = [d for d in os.listdir(stage) if os.path.isdir(os.path.join(stage, d))]
        if len(dirs) != 1 or not os.path.isfile(os.path.join(stage, dirs[0], "bundle.json")):
            raise Fail("not a game bundle: no bundle.json in the archive")
        root = os.path.join(stage, dirs[0])
        b = json.load(open(os.path.join(root, "bundle.json"), encoding="utf-8"))
        if int(b.get("format", 1)) > K.FORMAT:
            raise Fail(f"bundle format {b.get('format')} is newer than this platform understands")
        logged(M.check_identity, b)
        ok, note = host_ok(b)
        if not ok:
            raise Fail(note)
        if note:
            say("   " + note)
        say(f"Bundle {b.get('name')} {b.get('version')} (format {b.get('format', 1)})")
        if os.path.isfile(os.path.join(root, "SHA256SUMS")):
            say("Verifying every file")
            check_sums(root)
        say("Checking that the game can start")
        bad = trial(root, b)
        if bad:
            raise Fail("this bundle cannot start, so it was not installed: " + " | ".join(bad[:6]))
        folder = M.folder_name(b)
        carry_over(b, root, folder)
        dest = os.path.join(C.GAMES, folder)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.replace(root, dest)
        shutil.rmtree(stage, ignore_errors=True)
        game_dir = os.path.join(dest, b.get("game_dir") or "game")
        install_addons(dest, b, game_dir)
        godot_import(game_dir)
        M.set_active(folder)
        if not keep_old:
            for g in M.installed_games():
                if g["id"] == b["id"] and g["folder"] != folder:
                    shutil.rmtree(g["path"], ignore_errors=True)
        say(f"{b.get('name')} {b.get('version')} installed in {dest} and is the active game")
        return folder
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- the PuP Pack, Serum, settings
def game_or_fail(name=None):
    """Folder path of a game: by folder (`id@version`), by id (its newest version), or the active one."""
    if name:
        for g in sorted(M.installed_games(), key=lambda g: -g["mtime"]):
            if name in (g["folder"], g["id"]):
                return g["path"]
        raise Fail(f"no installed game {name} (`local list`)")
    p = M.installed_game()
    if not p:
        raise Fail("no game installed: `python -m mpf_godot local install BUNDLE`")
    return p


def assign_pup(src, game=None, user=None):
    """The author's zip into the library, unpacked untouched (nothing of the game runs), linked into the game (mpf_games.assign_pup)."""
    game = game_or_fail(game)
    b = M.read_bundle(game)
    if not b.get("pup"):
        raise Fail("this game has no PuP Pack support")
    if not (K.is_v2(b) or b["pup"].get("extract_only")):
        raise Fail("this format 1 bundle installs its pack with its own script: use the game's one-line install for the PuP")
    path, _, tmp = fetch(src, user, want_sha=False)
    try:
        name = re.sub(r"[^A-Za-z0-9._@+-]", "_", os.path.basename(path))[:120]
        if not name.lower().endswith(".zip"):
            raise Fail("a PuP Pack is the author's .zip")
        os.makedirs(os.path.dirname(M.pup_zip(name)), exist_ok=True)
        if os.path.abspath(path) != os.path.abspath(M.pup_zip(name)):
            shutil.copy2(path, M.pup_zip(name))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    lib = os.path.join(C.PUPS, "installed", M._pup_key(name, b))
    if not os.path.isdir(lib) or not os.listdir(lib):
        say("Unpacking the PuP Pack (a few minutes)")
        os.makedirs(lib, exist_ok=True)
        logged(M.extract_pup_zip, M.pup_zip(name), b, lib)
    for d in sorted(M.pup_dirs(b)):
        stored = os.path.join(lib, M._pup_store_name(d))
        if os.path.isdir(stored):
            make_link(stored, os.path.join(game, d))
            say(f"   {d} -> {stored}")
    if not K.is_v2(b) and v1_tool(game):
        v1_tool_run(game, "set", "pup.enabled", "true")
    say(f"PuP Pack {name} assigned to {os.path.basename(game)}")


def v1_tool(game):
    b = M.read_bundle(game) or {}
    rel = (b.get("options") or {}).get("tool", M.DEFAULT_OPTIONS_TOOL)
    p = os.path.join(game, rel)
    return p if os.path.isfile(p) else None


def v1_tool_run(game, *args):
    r = subprocess.run([tc.python(), v1_tool(game)] + list(args), cwd=game, capture_output=True, text=True,
                       env=dict(os.environ, **game_environment(M.read_bundle(game) or {})))
    if r.returncode:
        raise Fail((r.stderr or r.stdout).strip()[-400:] or "the game's settings tool failed")
    return r.stdout


def show_settings(game):
    b = M.read_bundle(game)
    if K.is_v2(b):
        s, cur, eff = K.schema(game, b), K.saved(game), K.effective(game, b)
        for o in s.get("options", []):
            extra = " choices: " + ", ".join(map(str, o["choices"])) if "choices" in o else ""
            mark = "" if o["id"] in cur else " (default)"
            say(f"{o['id']} = {eff.get(o['id'], '')}{mark}   {o.get('label', '')}{extra}")
        return
    if not v1_tool(game):
        raise Fail("this game has no settings")
    s = json.loads(v1_tool_run(game, "list"))
    cur = json.loads(v1_tool_run(game, "get") or "{}")
    for o in s.get("options", []):
        extra = " choices: " + ", ".join(map(str, o["choices"])) if "choices" in o else ""
        say(f"{o['id']} = {cur.get(o['id'], o.get('default', ''))}   {o.get('label', '')}{extra}")


def set_settings(game, pairs):
    b = M.read_bundle(game)
    kv = []
    for p in pairs:
        if "=" not in p:
            raise Fail(f"KEY=VALUE expected, got {p}")
        kv.append(tuple(p.split("=", 1)))
    if K.is_v2(b):
        try:
            K.set_values(game, b, [(k, v) for k, v in kv if v != ""], [k for k, v in kv if v == ""])
        except ValueError as e:
            raise Fail(str(e))
    else:
        if not v1_tool(game):
            raise Fail("this game has no settings")
        sets = [x for k, v in kv if v != "" for x in (k, v)]
        if sets:
            v1_tool_run(game, "set", *sets)
        unsets = [k for k, v in kv if v == ""]
        if unsets:
            v1_tool_run(game, "unset", *unsets)
    say("saved")


def port_file():
    return os.path.join(C.STATE_DIR, "zedmd-port")


def zedmd_port():
    """The ZeDMD's serial port chosen with `local dmd --port`; "" lets libzedmd look on every port."""
    try:
        return open(port_file(), encoding="utf-8").read().strip()
    except OSError:
        return ""


def dmd_settings(output=None, color=None, serum=None, port=None):
    if output or color:
        DMD.set_output(output, color)
    if serum:
        gid, _, rom = serum.partition("=")
        try:
            DMD.assign_serum(gid, "" if rom == "default" else rom)
        except ValueError as e:
            raise Fail(str(e))
    if port is not None:
        os.makedirs(C.STATE_DIR, exist_ok=True)
        with open(port_file(), "w", encoding="utf-8") as f:
            f.write(port.strip() + "\n")
    s = DMD.load()
    lib = DMD.library()
    say(f"output {s['output']}, colour {s['color']}, ZeDMD port " + (zedmd_port() or "found by libzedmd"))
    say("colourisations: " + (", ".join(f"{x['rom']} ({x['file']})" for x in lib) or "none"))
    for g in M.installed_games():
        rom = DMD.chosen_serum(g["id"], g["bundle"])
        say(f"   {g['id']}: " + (f"Serum {rom}" if rom else "no colour"))


# ---------------------------------------------------------------- start
def game_environment(b):
    """GODOT and the venv under the names the base system gives a game (mpf_games.game_environment), plus the platform's package."""
    env = {"GODOT": tc.godot_path(), "MPF_GAME_VENV": os.path.dirname(os.path.dirname(tc.python()))}
    child = M.game_environment(b, env)
    child["MPF_PLATFORM_DIR"] = ROOT
    child["PYTHONPATH"] = ROOT + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
    return child


def zedmd_answers():
    """dmd_bridge --probe (with the saved port): a ZeDMD is plugged in and answers."""
    d = DMD.bridge_dir()
    if not d:
        return False
    cmd = [os.path.join(d, DMD.BRIDGE), "--probe"] + (["--device", zedmd_port()] if zedmd_port() else [])
    try:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                              timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_output(output=None):
    """This run's output: a ZeDMD asked for (here or saved) that does not answer gives the screen, so a desktop never shows no DMD."""
    wanted = output or DMD.load()["output"]
    if wanted == "zedmd" and DMD.bridge_dir() and not zedmd_answers():
        say("no ZeDMD answers: the DMD is shown on the screen for this run")
        return "lcd"
    return output


def dmd_plan(gid, b, output=None):
    """(launcher args, Godot user args, MPF_DMD_OUTPUT): mpf_dmd.plan with this run's output and the saved ZeDMD port."""
    saved = DMD.load()
    port = zedmd_port()
    load = DMD.load
    if output:
        DMD.load = lambda: dict(saved, output=output)
    try:
        pre, user = DMD.plan(gid, b)
    finally:
        DMD.load = load
    if DMD.LAST == "zedmd" and port:
        user = user + port_args(port)
    wanted = output or saved["output"]
    if wanted == "zedmd" and DMD.LAST != "zedmd":
        say("no dmd_bridge on this computer: the DMD stays on the screen (`local doctor`)")
    return pre, user, DMD.LAST


def dmd_merge(board, gid, b, output=None):
    """mpf_dmd.merge_args (format 1 start: the board's arguments plus the DMD output's) with this run's output."""
    if not output:
        return DMD.merge_args(board, gid, b)
    saved, load = DMD.load(), DMD.load
    DMD.load = lambda: dict(saved, output=output)
    try:
        return DMD.merge_args(board, gid, b)
    finally:
        DMD.load = load


def port_args(port):
    return ["--zedmd-feed-arg=--device", "--zedmd-feed-arg=" + port]


def start(name=None, output=None, seconds=None, monitor=False, dry_run=False, extra=()):
    game = game_or_fail(name)
    b = M.read_bundle(game)
    gid = os.path.basename(game).split("@")[0]
    output = run_output(output)
    pre, dmd, out = dmd_plan(gid, b, output)
    env = game_environment(b)
    env["MPF_DMD_OUTPUT"] = out
    board = shlex.split(os.environ.get("MPF_GAME_ARGS", ""))
    if K.is_v2(b):
        P = K.plan(game, b)
        env.update(P["env"])
        head, engine, user = M.split_board_args(board)
        godot = engine + ["--"] + user + P["godot_args"] + pre + dmd + list(extra)
        say(f"{os.path.basename(game)}: configs {','.join(P['configs'])}, DMD {out}")
        say("   Godot: " + " ".join(godot))
        say("   env: " + " ".join(f"{k}={v}" for k, v in sorted(env.items()) if k.startswith("MPF_")))
        if dry_run:
            return 0
        K.apply_ini(game, P["ini"])
        os.makedirs(P["env"]["MPF_GAME_DATA"], exist_ok=True)
        os.environ.update(env)
        from mpf_godot import launcher
        return launcher.run(P["game_dir"], configs=",".join(P["configs"]), monitor=monitor, seconds=seconds, godot_args=godot)
    run_ = b.get("run") or {}
    argv = shlex.split(run_.get("start") or M.DEFAULT_START)
    if argv[0] in ("python", "python3"):
        argv[0] = tc.python()
    if M.wants_game_args(b):
        argv += dmd_merge(board, gid, b, output)       # the cabinet's order: run.py options, then Godot's -- --
        if out == "zedmd" and zedmd_port():
            argv += port_args(zedmd_port())          # Godot user arguments: merge_args ends with them
    head = [a for a in (["--seconds", str(seconds)] if seconds else []) + (["--monitor"] if monitor else [])]
    if head:                                          # run.py options go before Godot's --
        i = argv.index("--") if "--" in argv else len(argv)
        argv = argv[:i] + head + argv[i:]
    argv += list(extra)
    say(f"{os.path.basename(game)} (format 1): DMD {out}\n   $ " + " ".join(argv))
    if dry_run:
        return 0
    return subprocess.call(argv, cwd=os.path.normpath(os.path.join(game, run_.get("cwd") or ".")), env=dict(os.environ, **env))


# ---------------------------------------------------------------- doctor, bridge build
def doctor():
    ok = True
    py = tc.python()
    say(f"local folder   {LOCAL}")
    say(f"Python         {py}")
    r = subprocess.run([py, "-c", "import mpf, sys; print(mpf.__version__)"], capture_output=True, text=True)
    say("MPF            " + (r.stdout.strip() if r.returncode == 0 else "missing: run `python -m mpf_godot setup`"))
    ok &= r.returncode == 0
    g = tc.godot_path()
    say("Godot          " + (g if os.path.exists(g) else f"missing ({g}): run `python -m mpf_godot setup`"))
    ok &= os.path.exists(g)
    say("GMC            " + (addon_source("mpf-gmc") or "missing: run `python -m mpf_godot setup`"))
    d = DMD.bridge_dir()
    if d:
        say(f"dmd_bridge     {os.path.join(d, DMD.BRIDGE)}")
        say("libserum       " + (DMD.serum_lib(d) or "none (ZeDMD in one colour only)"))
        say("ZeDMD          " + ("answers" if DMD.probe_bridge() else "none answers (plugged in? port taken by another program?)"))
    else:
        say("dmd_bridge     none" + (": `python -m mpf_godot local build-bridge`" if not IS_WINDOWS else ""))
    s = DMD.load()
    say(f"DMD output     {s['output']} ({DMD.resolve(s) if s['output'] == 'auto' else s['output']} now)")
    for x in M.installed_games():
        say(f"game           {x['folder']}{' (active)' if x['active'] else ''}")
    return 0 if ok else 1


def build_bridge():
    """macOS (and Linux): libzedmd, libserum and dmd_bridge built on this computer into native/bin/<os>-<arch>/dmd_bridge/."""
    if IS_WINDOWS:
        raise Fail("Windows uses the prebuilt native/prebuilt/windows-x86_64/dmd_bridge/ (native/build_windows_bridge.sh on Linux)")
    sub = ("macos-" if OS == "macos" else "") + ME
    out = os.path.join(ROOT, "native", "bin", sub, "dmd_bridge")
    os.makedirs(out, exist_ok=True)
    for cmd in (["bash", os.path.join(ROOT, "native", "libzedmd", "build_libzedmd.sh"), out],
                ["bash", os.path.join(ROOT, "native", "dmd_bridge", "build.sh"), out],
                ["bash", os.path.join(ROOT, "native", "serum", "build_libserum.sh"), out]):
        say("$ " + " ".join(cmd))
        if subprocess.call(cmd):
            raise Fail(f"{os.path.basename(cmd[1])} failed: it needs git, cmake, a C++ compiler and autoconf/automake/libtool "
                       "(macOS: Xcode's command line tools and `brew install cmake autoconf automake libtool`)")
    say(f"dmd_bridge built in {out}")
    return 0


# ---------------------------------------------------------------- command line
def parser():
    p = argparse.ArgumentParser(prog="python -m mpf_godot local", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("install", help="install a game bundle (.tar.xz file or URL)")
    s.add_argument("bundle")
    s.add_argument("--sha256", help="the archive's sha256 (default: the .sha256 file beside it, if any)")
    s.add_argument("--user", help="user name for a WebDAV URL (password: MPF_WEBDAV_PASSWORD or asked)")
    s.add_argument("--replace", action="store_true", help="remove the other installed versions of this game")
    s = sub.add_parser("pup", help="assign the author's PuP Pack zip to a game")
    s.add_argument("zip")
    s.add_argument("--game")
    s.add_argument("--user")
    s = sub.add_parser("serum", help="store a Serum colourisation (<rom>.cROMc, .cRZ or .cROM)")
    s.add_argument("file")
    s = sub.add_parser("dmd", help="the DMD output and its colour, Serum per game, the ZeDMD's port")
    s.add_argument("--output", choices=DMD.OUTPUTS)
    s.add_argument("--color")
    s.add_argument("--serum", metavar="GAME=ROM|none|default")
    s.add_argument("--port", help="the ZeDMD's serial port (COM5, /dev/cu.usbserial-...); empty: found by libzedmd")
    sub.add_parser("list", help="the installed games")
    s = sub.add_parser("use", help="make a game the active one")
    s.add_argument("game")
    s = sub.add_parser("remove", help="delete an installed game")
    s.add_argument("game")
    s = sub.add_parser("settings", help="a game's settings and their values")
    s.add_argument("game", nargs="?")
    s = sub.add_parser("set", help="change a game's settings: KEY=VALUE (KEY= returns to the default)")
    s.add_argument("pairs", nargs="+")
    s.add_argument("--game")
    s = sub.add_parser("start", help="play a game (default: the active one)")
    s.add_argument("game", nargs="?")
    s.add_argument("--dmd", choices=DMD.OUTPUTS, help="this run's DMD output (default: the saved one)")
    s.add_argument("--seconds", type=float)
    s.add_argument("--monitor", action="store_true")
    s.add_argument("--dry-run", action="store_true", help="print what would start")
    sub.add_parser("doctor", help="what this computer has")
    sub.add_parser("build-bridge", help="build dmd_bridge here (macOS, Linux)")
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    a = parser().parse_args(argv)
    os.makedirs(LOCAL, exist_ok=True)
    if a.cmd == "install":
        install(a.bundle, a.sha256, a.user, keep_old=not a.replace)
    elif a.cmd == "pup":
        assign_pup(a.zip, a.game, a.user)
    elif a.cmd == "serum":
        try:
            tmp = os.path.join(LOCAL, "uploads", os.path.basename(a.file))
            os.makedirs(os.path.dirname(tmp), exist_ok=True)
            shutil.copy2(a.file, tmp)
            say(f"colourisation {DMD.store_serum(tmp, os.path.basename(a.file))} stored; games whose ROM has this name use it")
        except ValueError as e:
            raise Fail(str(e))
    elif a.cmd == "dmd":
        dmd_settings(a.output, a.color, a.serum, a.port)
    elif a.cmd == "list":
        games = M.installed_games()
        for g in games:
            pup = "PuP" if any(os.path.isdir(os.path.join(g["path"], d)) for d in M.pup_dirs(g["bundle"])) else "no PuP"
            say(f"{'*' if g['active'] else ' '} {g['folder']:40} {g['name']}  (format {g['bundle'].get('format', 1)}, {pup})")
        if not games:
            say("no game installed")
    elif a.cmd == "use":
        M.set_active(os.path.basename(game_or_fail(a.game)))
        say("active: " + M.active_folder())
    elif a.cmd == "remove":
        p = game_or_fail(a.game)
        shutil.rmtree(p)
        say(f"removed {p}")
    elif a.cmd == "settings":
        show_settings(game_or_fail(a.game))
    elif a.cmd == "set":
        set_settings(game_or_fail(a.game), a.pairs)
    elif a.cmd == "start":
        return start(a.game, a.dmd, a.seconds, a.monitor, a.dry_run, extra) or 0
    elif a.cmd == "doctor":
        return doctor()
    elif a.cmd == "build-bridge":
        return build_bridge()
    return 0


if __name__ == "__main__":
    sys.exit(main())
