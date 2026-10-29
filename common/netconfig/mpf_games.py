"""Games on an MPF image: install a bundle, keep several, pick the active one, install a PuP Pack, start it. Standard library only.

A game is a *bundle* (common/games/README.md): a folder with a bundle.json that says what it is and how to start it. Any number can
be installed side by side, each in `<MPF_GAMES_DIR>/<id>@<version>/`; one of them is *active* (the one mpf-game.service starts).
Nothing here knows a particular game: what a bundle needs from the base system, how it starts, where its PuP Pack goes and what
the operator can set are all read from its bundle.json.
"""
import hashlib
import json
import os
import platform
import pwd
import re
import shlex
import shutil
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpf_common as C  # noqa: E402
from mpf_common import run  # noqa: E402

JOB = {"state": "idle", "msg": "", "log": ""}      # one install at a time; the page polls /job
JOB_LOCK = threading.Lock()
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
DEFAULT_START = "python3 scripts/package/start.py"
DEFAULT_OPTIONS_TOOL = "scripts/package/bundle_options.py"
DEFAULT_PUP_INSTALL = "python3 scripts/pup/pup_setup.py --pup-zip ZIP_PATH_OR_URL"


class JobError(Exception):
    pass


def job_set(**kw):
    JOB.update(kw)
    try:                    # the page may run in another process than an install started at boot (the inbox)
        with open(C.JOB_FILE, "w") as f:
            json.dump(JOB, f)
    except OSError:
        pass


def job_log(text):
    JOB["log"] = (JOB["log"] + text.rstrip("\n") + "\n")[-6000:]


def job_state():
    """What the page shows: this process's job, else the one an install started at boot left in the job file."""
    if JOB["state"] != "idle":
        return JOB
    try:
        return json.load(open(C.JOB_FILE))
    except (OSError, ValueError):
        return JOB


def sh(*cmd, cwd=None, user=False):
    """Run a command for the job, log its output, fail the job when it fails."""
    if user:
        cmd = ("runuser", "-u", C.USER, "--") + cmd
    job_log("$ " + " ".join(cmd))
    r = run(*cmd, cwd=cwd)
    job_log((r.stdout + r.stderr)[-2000:])
    if r.returncode:
        raise JobError(f"{cmd[0]} failed ({r.returncode})")
    return r


def game_env():
    return C.read_kv(C.GAME_ENV)


def game_python():
    venv = game_env().get("MPF_GAME_VENV")
    py = os.path.join(venv, "bin", "python") if venv else ""
    return py if py and os.path.exists(py) else "python3"


def free_gb(path):
    os.makedirs(path, exist_ok=True)
    return shutil.disk_usage(path).free / 1e9


# ---------------------------------------------------------------- the installed games
def read_bundle(path):
    try:
        with open(os.path.join(path, "bundle.json"), encoding="utf-8") as f:
            b = json.load(f)
        return b if isinstance(b, dict) else None
    except (OSError, ValueError):
        return None


def folder_name(b):
    return f"{b['id']}@{b['version']}"


def check_identity(b):
    if not ID_RE.match(str(b.get("id", ""))):
        raise JobError("bundle.json: id must be lowercase letters, digits, . _ - (at most 64)")
    if not VERSION_RE.match(str(b.get("version", ""))):
        raise JobError("bundle.json: version must be letters, digits, . _ + - (at most 64)")
    b["version"] = str(b["version"])


def installed_games():
    """[{folder, path, id, name, version, bundle, active}] sorted by name then version (newest folder first within a game)."""
    out = []
    try:
        names = sorted(os.listdir(C.GAMES))
    except OSError:
        names = []
    for n in names:
        p = os.path.join(C.GAMES, n)
        if n.startswith(".") or not os.path.isdir(p):
            continue
        b = read_bundle(p)
        if b:
            out.append({"folder": n, "path": p, "id": str(b.get("id", n)), "name": str(b.get("name", n)),
                        "version": str(b.get("version", "")), "bundle": b, "mtime": os.path.getmtime(os.path.join(p, "bundle.json"))})
    out.sort(key=lambda g: (g["name"].lower(), -g["mtime"]))
    act = active_folder([g["folder"] for g in out])
    for g in out:
        g["active"] = g["folder"] == act
    return out


def active_file():
    return os.path.join(C.STATE_DIR, "active-game")


def active_folder(folders=None):
    """Folder name of the active game: the one chosen on the page, else the only/first installed."""
    if folders is None:
        folders = [g["folder"] for g in installed_games()]
    try:
        want = open(active_file()).read().strip()
    except OSError:
        want = ""
    if want in folders:
        return want
    return folders[0] if folders else None


def set_active(folder):
    if folder not in [g["folder"] for g in installed_games()]:
        raise ValueError("no such game")
    os.makedirs(C.STATE_DIR, exist_ok=True)
    tmp = active_file() + ".tmp"
    with open(tmp, "w") as f:
        f.write(folder + "\n")
    os.replace(tmp, active_file())


def installed_game(folder=None):
    """Path of a game (default: the active one), or None."""
    folder = folder or active_folder()
    return os.path.join(C.GAMES, folder) if folder and os.path.isfile(os.path.join(C.GAMES, folder, "bundle.json")) else None


def delete_game(folder):
    games = {g["folder"]: g for g in installed_games()}
    if folder not in games:
        raise ValueError("no such game")
    if games[folder]["active"] and game_running():
        raise ValueError("stop the game first")
    shutil.rmtree(games[folder]["path"])
    left = installed_games()
    if games[folder]["active"] and left:
        set_active(left[0]["folder"])


# ---------------------------------------------------------------- settings of a game (the bundle's own tool)
def options_tool(game):
    """Path of the bundle's settings tool, or None when the bundle has none."""
    b = read_bundle(game) or {}
    rel = (b.get("options") or {}).get("tool", DEFAULT_OPTIONS_TOOL)
    p = os.path.join(game, rel)
    return p if os.path.isfile(p) else None


def tool(game, *args):
    """Run the bundle's own settings tool as the game user; returns the CompletedProcess."""
    t = options_tool(game)
    if not t:
        raise ValueError("this game has no settings tool")
    return run("runuser", "-u", C.USER, "--", game_python(), t, *args, cwd=game)


def settings_schema(game):
    """The bundle's settings schema as this board sees it: its tool narrows the choices the board's profile limits
    (platforms/README.md, Platform limits); the file itself if the tool cannot run."""
    try:
        return json.loads(tool(game, "list").stdout)
    except ValueError:
        b = read_bundle(game) or {}
        return json.load(open(os.path.join(game, (b.get("options") or {}).get("schema", "scripts/package/options.json"))))


def settings_save(game, form):
    schema = settings_schema(game)
    cur = json.loads(tool(game, "get").stdout or "{}")
    sets, unsets = [], []
    for o in schema["options"]:
        v = form.get("o." + o["id"], "").strip()
        if v:
            sets += [o["id"], v]
        elif o["id"] in cur and not o.get("secret"):
            unsets.append(o["id"])
    if sets:
        r = tool(game, "set", *sets)
        if r.returncode:
            raise ValueError((r.stderr or r.stdout).strip()[-300:])
    if unsets:
        tool(game, "unset", *unsets)


def pup_dirs(b):
    """Folders of a bundle that hold a PuP Pack and its converted media (written once, then only read)."""
    pup = b.get("pup") or {}
    return {os.path.normpath(p) for p in (pup.get("pack_dir"), pup.get("media_dir")) if p}


def pup_installed(game, b=None):
    b = b or read_bundle(game) or {}
    d = (b.get("pup") or {}).get("pack_dir")
    return bool(d) and os.path.isdir(os.path.join(game, d))


def first_run_defaults(game, b):
    """No PuP until a pack is installed, and start at power-on: only for what nobody set yet."""
    if options_tool(game) and b.get("pup"):
        try:
            have = json.loads(tool(game, "get").stdout or "{}")
        except ValueError:
            have = {}
        # no display options here: how the display looks is a matter of the board (a Raspberry Pi 4 cannot draw an HD DMD), so it comes
        # from the bundle's board profile (board_profile below); a board without a profile keeps the bundle's default
        want = [x for x in (("pup.enabled", "true" if pup_installed(game, b) else "false"),) if x[0] not in have]
        if want:
            job_log(tool(game, "set", *[v for kv in want for v in kv]).stderr)
    set_autostart(True)


def board_profile(game, b):
    """The bundle's settings for this board (bundle.json "profiles", picked from the device tree by the bundle's own
    tool): applied once, only to what nobody set; the tool's lines go to the job log."""
    cmd = b.get("profiles", {}).get("apply")
    if not cmd:
        return
    args = shlex.split(cmd)
    if args[0] in ("python3", "python"):
        args[0] = game_python()
    r = run("runuser", "-u", C.USER, "--", *args, cwd=game)
    job_log((r.stdout + r.stderr).strip() or "board profile: nothing to apply")


# ---------------------------------------------------------------- platform add-ons
def platform_addon(name):
    """The platform's own copy of a binary add-on (addons/<name>), or None."""
    cands = [C.PLATFORM_DIR, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))]
    if C.GOZEN_SO:
        cands.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(C.GOZEN_SO)))))
    marker = "gozen.gdextension" if name == "gde_gozen" else "plugin.cfg"
    for c in cands:
        # the add-ons of the platform checkout (GoZen), and the ones its toolchain made (mpf-gmc, patched: mpf_godot/gmc_patch.py)
        for sub in ("addons", os.path.join("toolchain", "addons")):
            if c and os.path.isfile(os.path.join(c, sub, name, marker)):
                return os.path.join(c, sub, name)
    return None


def install_platform_addons(dest, b, me):
    """Binary add-ons come from the platform, never from the game bundle: the same build for every game. Only
    this machine's binaries are copied."""
    for name in b.get("platform_addons", []):
        src = platform_addon(name)
        if not src:
            raise JobError(f"the bundle needs the platform's {name} and this system has none (set MPF_PLATFORM_DIR)")
        dst = os.path.join(dest, "game", "addons", name)
        shutil.rmtree(dst, ignore_errors=True)
        for base, _dirs, files in os.walk(src):
            for f in files:
                if os.path.relpath(base, src).startswith("bin") and f.startswith("libgozen") and \
                        not re.match(r"libgozen\.linux\..*\.%s\.so$" % ("arm64" if me == "arm64" else "x86_64"), f):
                    continue
                if os.path.relpath(base, src).startswith("bin") and f.endswith(".dll"):
                    continue
                t = os.path.join(dst, os.path.relpath(os.path.join(base, f), src))
                os.makedirs(os.path.dirname(t), exist_ok=True)
                shutil.copy2(os.path.join(base, f), t)
        # Godot loads an add-on's native extension only if .godot/extension_list.cfg names it (the editor writes that file;
        # a bundle exported without the add-on's binaries does not have it)
        lst = os.path.join(dest, "game", ".godot", "extension_list.cfg")
        for f in sorted(os.listdir(dst)):
            if f.endswith(".gdextension"):
                line = f"res://addons/{name}/{f}"
                have = open(lst).read().split() if os.path.isfile(lst) else []
                if line not in have:
                    os.makedirs(os.path.dirname(lst), exist_ok=True)
                    with open(lst, "a") as fh:
                        fh.write(line + "\n")
        job_log(f"{name}: the platform's build ({src}) installed for {me}")


def reimport_scripts(dest, b):
    """A platform add-on made of scripts (mpf-gmc) that is put into a bundle exported without it leaves Godot's class cache
    (game/.godot/global_script_class_cache.cfg) without its classes: the game would stop at "Could not find base class". One
    headless import of the project (a few seconds) rebuilds it. Runs as the game user; the data goes under the game folder."""
    if not any(platform_addon(n) and not os.path.isdir(os.path.join(platform_addon(n), "bin")) for n in b.get("platform_addons", [])):
        return
    godot = game_env().get("GODOT") or shutil.which("godot") or ""
    project = os.path.join(dest, "game")
    if not godot or not os.path.isfile(os.path.join(project, "project.godot")):
        job_log("no Godot or no project.godot: the script classes of the platform add-ons are not re-imported")
        return
    pw = pwd.getpwnam(C.USER)
    env = dict(os.environ, HOME=pw.pw_dir, **ram_xdg_env())
    job_set(msg="Importing the project (a few seconds)")
    cmd = ["runuser", "-u", C.USER, "--", "env"] + [f"{k}={v}" for k, v in env.items() if k in ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME")]
    cmd += [godot, "--headless", "--path", project, "--import"]
    job_log("$ " + " ".join(cmd[-5:]))
    r = run(*cmd)
    job_log((r.stdout + r.stderr)[-1500:])
    if r.returncode:
        raise JobError(f"the Godot import failed ({r.returncode})")


# ---------------------------------------------------------------- install
def copy_keep(src, dst, linked):
    """Carry a kept path from an installed version to a new one. A PuP Pack and its media are large and never rewritten in
    place, so the files under `linked` (absolute folders of the old version) are hard-linked (no second copy on the disk);
    settings and scores are copied (a game rewrites those in place)."""
    if os.path.islink(dst) or os.path.isfile(dst):
        os.remove(dst)
    shutil.rmtree(dst, ignore_errors=True) if os.path.isdir(dst) else None
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.islink(src):          # a PuP Pack assigned from the library: the new version shares it
        os.symlink(os.readlink(src), dst)
        return
    if not os.path.isdir(src):
        shutil.copy2(src, dst)
        return

    def link_or_copy(s, d):
        if any(s.startswith(l + os.sep) for l in linked):
            try:
                os.link(s, d)
                return
            except OSError:
                pass
        shutil.copy2(s, d)
    shutil.copytree(src, dst, copy_function=link_or_copy, symlinks=True)


def previous_version(b, exclude):
    """Folder of the installed version of the same game that a new one inherits its settings, scores and PuP Pack from: the active
    one, else the most recently installed."""
    same = [g for g in installed_games() if g["id"] == b["id"] and g["folder"] != exclude]
    same.sort(key=lambda g: (not g["active"], -g["mtime"]))
    return same[0] if same else None


def install_game(archive, expect_sha, keep_old=True):
    job_set(state="running", msg="Checking the archive")
    h = hashlib.sha256()
    with open(archive, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if expect_sha and h.hexdigest() != expect_sha.lower():
        raise JobError("the archive's sha256 does not match the .sha256 file: upload it again")
    os.makedirs(C.GAMES, exist_ok=True)
    stage = os.path.join(C.GAMES, ".stage")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    job_set(msg="Unpacking (a few minutes)")
    sh("tar", "-xJf", archive, "-C", stage, "--no-same-owner")
    dirs = [d for d in os.listdir(stage) if os.path.isdir(os.path.join(stage, d))]
    if len(dirs) != 1 or not os.path.isfile(os.path.join(stage, dirs[0], "bundle.json")):
        raise JobError("not a game bundle: no bundle.json in the archive")
    root = os.path.join(stage, dirs[0])
    b = json.load(open(os.path.join(root, "bundle.json")))
    if b.get("format", 1) > 1:
        raise JobError(f"bundle format {b.get('format')} is newer than this page understands")
    check_identity(b)
    tgt, me = b.get("target", {}), C.ARCH.get(platform.machine(), platform.machine())
    # "arm64+x86_64": a bundle for several architectures (both texture formats, every native add-on); "all": no binary at all
    arches = str(tgt.get("arch", "all")).split("+")
    if tgt.get("os", "linux") != "linux" or ("all" not in arches and me not in arches):
        raise JobError(f"this bundle is for {tgt.get('os')}/{tgt.get('arch')}, this machine is linux/{me}")
    job_log(f"bundle {b.get('name')} {b.get('version')}")
    if os.path.isfile(os.path.join(root, "SHA256SUMS")):
        job_set(msg="Verifying every file (sha256sum)")
        sh("sha256sum", "-c", "SHA256SUMS", "--quiet", cwd=root)
    folder = folder_name(b)
    dest = os.path.join(C.GAMES, folder)
    old = dest + ".old"
    shutil.rmtree(old, ignore_errors=True)
    keep = b.get("keep_on_update", [])
    if os.path.isdir(dest):         # the same version again: it is replaced, what it kept moves to the new copy
        job_set(msg="Keeping settings, scores and PuP Pack")
        for rel in keep:
            src, dst = os.path.join(dest, rel), os.path.join(root, rel)
            if os.path.exists(src):
                shutil.rmtree(dst, ignore_errors=True) if os.path.isdir(dst) else None
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(src, dst)
        os.rename(dest, old)
    else:                           # another version of an installed game: it inherits a copy, the old one stays playable
        prev = previous_version(b, folder)
        if prev:
            job_set(msg=f"Carrying settings, scores and PuP Pack over from {prev['version']}")
            big = [os.path.join(prev["path"], d) for d in pup_dirs(prev["bundle"]) | pup_dirs(b)]
            for rel in keep:
                src, dst = os.path.join(prev["path"], rel), os.path.join(root, rel)
                if os.path.exists(src):
                    copy_keep(src, dst, big)
    os.rename(root, dest)
    volatile_game_dirs(dest)
    shutil.rmtree(stage, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    install_platform_addons(dest, b, me)
    if C.GAME_OVERRIDE and os.path.isfile(C.GAME_OVERRIDE):
        os.makedirs(os.path.join(dest, "game"), exist_ok=True)
        shutil.copy2(C.GAME_OVERRIDE, os.path.join(dest, "game", "override.cfg"))
        job_log(f"board settings ({C.GAME_OVERRIDE}) copied to game/override.cfg")
    if C.GOZEN_SO and os.path.isfile(C.GOZEN_SO):
        bindir = os.path.join(dest, "game/addons/gde_gozen/bin")
        for n in os.listdir(bindir) if os.path.isdir(bindir) else ():
            if n in b.get("gozen", {}) and all(f in b["gozen"][n] for f in C.GOZEN_NEEDS):
                job_log(f"{n}: the bundle's own build has {' '.join(C.GOZEN_NEEDS)}, kept")
            elif re.match(r"libgozen\.linux\..*%s\.so$" % me, n):
                shutil.copy(C.GOZEN_SO, os.path.join(bindir, n))
                job_log(f"{n}: replaced by this board's GoZen")
    pw = pwd.getpwnam(C.USER)
    sh("chown", "-R", f"{pw.pw_uid}:{pw.pw_gid}", dest)
    reimport_scripts(dest, b)
    os.remove(archive)
    first_run_defaults(dest, b)
    board_profile(dest, b)
    # an update of the active game takes its place; a first game is the active one; another game waits to be chosen on the page
    cur = {g["folder"]: g for g in installed_games()}
    act = active_folder([f for f in cur if f != folder])
    if act is None or cur.get(act, {}).get("id") == b["id"]:
        was_running = act is not None and game_running()
        set_active(folder)
        note = " and is now the active game"
        if was_running:         # the running process is the old version: restart so that state and process agree
            try:
                game_restart()
                note += " (the game is restarting)"
            except ValueError:
                pass
    else:
        note = "; choose it on the page to play it"
    if not keep_old:
        for g in installed_games():
            if g["id"] == b["id"] and g["folder"] != folder and not g["active"]:
                shutil.rmtree(g["path"], ignore_errors=True)
    job_set(state="done", msg=f"{b.get('name')} {b.get('version')} installed{note}")


def install_pup(zipfile, folder=None, remove=True):
    game = installed_game(folder)
    if not game:
        raise JobError("install the game first")
    b = read_bundle(game)
    if not b.get("pup"):
        raise JobError("this game has no PuP Pack support")
    job_set(state="running", msg="Installing the PuP Pack (videos are checked, a few minutes)")
    run_pup_installer(game, b, zipfile)
    if remove:
        os.remove(zipfile)
    if options_tool(game):
        tool(game, "set", "pup.enabled", "true")
    job_set(state="done", msg="PuP Pack installed and enabled" + (" (restart the game)" if b["pup"].get("needs_restart") else ""))


def run_pup_installer(game, b, zipfile):
    cmd = b["pup"].get("install", DEFAULT_PUP_INSTALL)
    args = [zipfile if a == "ZIP_PATH_OR_URL" else a for a in shlex.split(cmd)]
    if args[0] in ("python3", "python"):
        args[0] = game_python()
    env = ["env"] + [f"{k}={v}" for k, v in game_env().items()]
    sh(*env, *args, cwd=game, user=True)
    # a pack install that tidies the game's add-ons must not lose the platform's GoZen: put it back
    if b.get("platform_addons"):
        install_platform_addons(game, b, C.ARCH.get(platform.machine(), platform.machine()))
        reimport_scripts(game, b)
        sh("chown", "-R", f"{pwd.getpwnam(C.USER).pw_uid}:{pwd.getpwnam(C.USER).pw_gid}", os.path.join(game, "game", "addons"))


# ---------------------------------------------------------------- PuP Pack library
# A pack is uploaded once into the library (`<PUPS>/zips/<name>.zip`) and then *assigned* to a game: the game's own pack installer
# runs once per (pack, game id) and its folders move to `<PUPS>/installed/<pack>@<game id>/`; the game's pack and media folders become
# links to them. Assigning the pack to another version of the same game, or taking it away, costs no install.

def pup_zip(name):
    return os.path.join(C.PUPS, "zips", name)


def pup_library():
    """[{name, size}] of the packs in the library."""
    d = os.path.join(C.PUPS, "zips")
    try:
        names = sorted(n for n in os.listdir(d) if n.lower().endswith(".zip"))
    except OSError:
        return []
    return [{"name": n, "size": os.path.getsize(os.path.join(d, n))} for n in names]


def pup_store(path, name):
    """Move an uploaded pack into the library; its name is kept (a second upload of the same name replaces it)."""
    import zipfile as zf
    name = re.sub(r"[^A-Za-z0-9._@+-]", "_", os.path.basename(name))[:120]
    if not name.lower().endswith(".zip") or not zf.is_zipfile(path):
        raise JobError("not a .zip PuP Pack")
    os.makedirs(os.path.dirname(pup_zip(name)), exist_ok=True)
    shutil.move(path, pup_zip(name))
    return name


def _pup_key(name, b):
    return f"{name[:-4]}@{b['id']}"


def _pup_store_name(d):
    return d.replace("/", "__")


def pup_assigned(game, b=None):
    """Name of the library pack a game's pack folder links to; None when no pack (or one installed outside the library)."""
    b = b or read_bundle(game) or {}
    for d in sorted(pup_dirs(b)):
        p = os.path.join(game, d)
        if os.path.islink(p):
            tgt = os.path.realpath(p)
            root = os.path.realpath(os.path.join(C.PUPS, "installed")) + os.sep
            if tgt.startswith(root):
                return tgt[len(root):].split(os.sep)[0].rsplit("@", 1)[0] + ".zip"
    return None


def _drop(p):
    if os.path.islink(p) or os.path.isfile(p):
        os.remove(p)
    elif os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)


def assign_pup(folder, name):
    game = installed_game(folder)
    if not game:
        raise JobError("unknown game")
    b = read_bundle(game)
    if not b.get("pup"):
        raise JobError("this game has no PuP Pack support")
    src = pup_zip(name)
    if not os.path.isfile(src):
        raise JobError("this pack is not in the library")
    dirs = sorted(pup_dirs(b))
    lib = os.path.join(C.PUPS, "installed", _pup_key(name, b))
    if not os.path.isdir(lib) or not os.listdir(lib):
        job_set(state="running", msg="Installing the PuP Pack for this game (videos are checked, a few minutes)")
        for d in dirs:
            _drop(os.path.join(game, d))
        run_pup_installer(game, b, src)
        os.makedirs(lib, exist_ok=True)
        for d in dirs:
            p = os.path.join(game, d)
            if os.path.isdir(p) and not os.path.islink(p):
                dst = os.path.join(lib, _pup_store_name(d))
                shutil.rmtree(dst, ignore_errors=True)
                shutil.move(p, dst)
    job_set(state="running", msg="Linking the PuP Pack")
    for d in dirs:
        stored = os.path.join(lib, _pup_store_name(d))
        if os.path.isdir(stored):
            _drop(os.path.join(game, d))
            os.makedirs(os.path.dirname(os.path.join(game, d)), exist_ok=True)
            os.symlink(stored, os.path.join(game, d))
    sh("chown", "-R", f"{pwd.getpwnam(C.USER).pw_uid}:{pwd.getpwnam(C.USER).pw_gid}", lib)
    if options_tool(game):
        tool(game, "set", "pup.enabled", "true")
    job_set(state="done", msg="PuP Pack assigned" + (" (restart the game)" if b["pup"].get("needs_restart") else ""))


def unassign_pup(folder):
    game = installed_game(folder)
    if not game:
        raise JobError("unknown game")
    b = read_bundle(game)
    for d in pup_dirs(b):
        p = os.path.join(game, d)
        if os.path.islink(p):
            os.remove(p)
    if options_tool(game):
        tool(game, "set", "pup.enabled", "false")
    job_set(state="done", msg="PuP Pack taken away from this game")


def store_pup(path, name):
    stored = pup_store(path, name)
    job_set(state="done", msg=f"{stored} is in the PuP Pack library: assign it to a game")


def delete_pup_job(name):
    delete_pup(name)
    job_set(state="done", msg=f"{name} removed from the library")


def delete_pup(name):
    for g in installed_games():
        if pup_assigned(g["path"], g["bundle"]) == name:
            raise JobError(f"in use by {g['name']} {g['version']}: take it away first")
    try:
        os.remove(pup_zip(name))
    except OSError:
        raise JobError("this pack is not in the library")
    for d in glob_installed(name[:-4]):
        shutil.rmtree(d, ignore_errors=True)


def glob_installed(stem):
    root = os.path.join(C.PUPS, "installed")
    try:
        return [os.path.join(root, n) for n in os.listdir(root) if n.rsplit("@", 1)[0] == stem]
    except OSError:
        return []


def run_job(fn, *args):
    """Run one install in this thread; the caller took JOB_LOCK, it is released here."""
    try:
        fn(*args)
    except JobError as e:
        job_set(state="error", msg=str(e))
    except Exception as e:   # keep the page alive whatever happens
        job_set(state="error", msg=f"{type(e).__name__}: {e}")
    finally:
        if JOB["state"] != "done":      # a failed install leaves nothing behind (up to 1 GB)
            for f in ("game.tar.xz", "pup.zip"):
                try:
                    os.remove(os.path.join(C.UPLOADS, f))
                except OSError:
                    pass
            shutil.rmtree(os.path.join(C.GAMES, ".stage"), ignore_errors=True)
        JOB_LOCK.release()


# ---------------------------------------------------------------- the inbox: files dropped in a folder are installed at boot
def inbox_pup_target(name, games):
    """Folder a pack in the inbox is for: `<id>.pup.zip` (that game's active or newest version), `<id>@<version>.pup.zip`, else the active game."""
    stem = name[:-len(".pup.zip")] if name.endswith(".pup.zip") else ""
    for g in games:
        if stem == g["folder"]:
            return g["folder"]
    for g in sorted(games, key=lambda g: (not g["active"], -g["mtime"])):
        if stem == g["id"]:
            return g["folder"]
    return None


def process_inbox():
    """Install what is in the inbox folder, then remove it: bundles (`*.tar.xz`, with an optional `.sha256` beside) first, then
    PuP Packs (`*.zip`). A file that fails goes to inbox/failed/ with its log. Used for images made with common/games/inject_image.py and for
    anything copied there by hand."""
    d = C.INBOX
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return 0
    bundles = [n for n in names if n.endswith(".tar.xz")]
    packs = [n for n in names if n.lower().endswith(".zip")]
    done = 0
    for name in bundles + packs:
        path = os.path.join(d, name)
        if bundles and name in bundles:
            sha = ""
            try:
                sha = open(path + ".sha256").read().split()[0]
            except (OSError, IndexError):
                pass
            fn, args = install_game, (path, sha)
        else:
            games = installed_games()
            target = inbox_pup_target(name, games) if name.endswith(".pup.zip") else active_folder()
            fn, args = install_pup, (path, target or None)
        JOB_LOCK.acquire()
        job_set(state="running", msg=f"Installing {name} from the inbox", log="")
        run_job(fn, *args)
        if JOB["state"] == "done":
            done += 1
            for side in (path + ".sha256",):
                try:
                    os.remove(side)
                except OSError:
                    pass
        else:
            failed = os.path.join(d, "failed")
            os.makedirs(failed, exist_ok=True)
            with open(os.path.join(failed, name + ".log"), "w") as f:
                f.write(JOB["msg"] + "\n" + JOB["log"])
            for p in (path, path + ".sha256"):
                if os.path.exists(p):
                    shutil.move(p, os.path.join(failed, os.path.basename(p)))
    return done


# ---------------------------------------------------------------- start, stop, autostart
def game_running():
    return run("systemctl", "is-active", "--quiet", "mpf-game.service").returncode == 0


def volatile_game_dirs(game):
    """Read-only mode: the game's logs are written all the time, so game/logs becomes a link to a folder in RAM (the rest of the
    game folder is on the data partition and only changes when a setting, a score or an audit does)."""
    if not C.READONLY:
        return
    pw = pwd.getpwnam(C.USER)
    os.makedirs(C.VOLATILE_LOGS, exist_ok=True)
    os.chown(C.VOLATILE_LOGS, pw.pw_uid, pw.pw_gid)
    logs = os.path.join(game, "game", "logs")
    if os.path.islink(logs):
        return
    if os.path.isdir(logs):
        shutil.rmtree(logs, ignore_errors=True)
    os.makedirs(os.path.dirname(logs), exist_ok=True)
    try:
        os.symlink(C.VOLATILE_LOGS, logs)
    except FileExistsError:
        pass


def ram_xdg_env():
    """Godot writes user:// and its caches under XDG_*: data and config in RAM, the (rarely written) caches on the data partition."""
    if not C.READONLY:
        return {}
    pw = pwd.getpwnam(C.USER)
    for d in (C.XDG_RAM, C.XDG_RAM + "/data", C.XDG_RAM + "/config"):
        os.makedirs(d, exist_ok=True)
        os.chown(d, pw.pw_uid, pw.pw_gid)
    cache = os.path.join(C.DATA, "cache")
    os.makedirs(cache, exist_ok=True)
    os.chown(cache, pw.pw_uid, pw.pw_gid)
    return {"XDG_DATA_HOME": C.XDG_RAM + "/data", "XDG_CONFIG_HOME": C.XDG_RAM + "/config", "XDG_CACHE_HOME": cache}


def resolve_program(name):
    """python / python3 are the game's venv python; another name is looked up in the venv's bin first (mpf, pytest...), then on PATH."""
    if name in ("python", "python3"):
        return game_python()
    venv = game_env().get("MPF_GAME_VENV")
    if venv and os.path.isfile(os.path.join(venv, "bin", name)):
        return os.path.join(venv, "bin", name)
    return shutil.which(name) or name


def wants_game_args(b):
    """MPF_GAME_ARGS (the board's Godot arguments, /etc/default/mpf-game) go only to a game that takes them: `run.game_args` true,
    or, when the bundle does not say, a game started by the packaged launcher `scripts/package/start.py` (which forwards them)."""
    run_ = b.get("run") or {}
    if "game_args" in run_:
        return bool(run_["game_args"])
    return "scripts/package/start.py" in (run_.get("start") or DEFAULT_START)


def game_command(game, b, env):
    """(argv, cwd) that starts a bundle: its run.start (default: the game package's start.py) plus MPF_GAME_ARGS from /etc/default/mpf-game."""
    run_ = b.get("run") or {}
    argv = shlex.split(run_.get("start") or DEFAULT_START)
    argv[0] = resolve_program(argv[0])
    if wants_game_args(b):
        argv += shlex.split(env.get("MPF_GAME_ARGS", ""))
    return argv, os.path.normpath(os.path.join(game, run_.get("cwd") or "."))


def game_environment(b, env):
    """What a bundle is told about the base system. The base provides GODOT and MPF_GAME_VENV (/etc/default/mpf-game); a bundle names
    the variables it reads in `requires.env`: GODOT, and any name ending in VENV gets the venv folder."""
    child = {}
    if env.get("GODOT"):
        child["GODOT"] = env["GODOT"]
    venv = env.get("MPF_GAME_VENV")
    if venv:
        child["MPF_GAME_VENV"] = venv
        for k in (b.get("requires") or {}).get("env", {}):
            if k.endswith("VENV"):
                child[k] = venv
    for k, v in env.items():     # a variable of the base's own that a game reads under its name (TF_VENV=...)
        if k.endswith("_VENV") and k not in child:
            child[k] = v
    return child


def game_exec():
    """Entry of mpf-game.service: wait for the X session (unless the game needs no display), drop to the game user, become the game."""
    game = installed_game()
    if not game:
        sys.exit("no game installed")
    b = read_bundle(game) or {}
    env = game_env()
    pw = pwd.getpwnam(C.USER)
    if (b.get("run") or {}).get("needs_display", True):
        for _ in range(180):
            if os.path.exists("/tmp/.X11-unix/X0"):
                break
            time.sleep(1)
        else:
            sys.exit("no X session after 180 s")      # the service restarts and waits again
        time.sleep(3)           # let the window manager settle
    volatile_game_dirs(game)
    xdg = ram_xdg_env()
    argv, cwd = game_command(game, b, env)
    os.chdir(cwd)
    os.setgroups(os.getgrouplist(C.USER, pw.pw_gid))
    os.setgid(pw.pw_gid)
    os.setuid(pw.pw_uid)
    # the X cookie: where /etc/profile.d/mpf-readonly.sh puts it in read-only mode, else in the home folder
    xauth = f"/tmp/.Xauthority-{C.USER}" if C.READONLY else os.path.join(pw.pw_dir, ".Xauthority")
    child = dict(os.environ, HOME=pw.pw_dir, USER=C.USER, DISPLAY=env.get("DISPLAY", ":0"),
                 XAUTHORITY=env.get("XAUTHORITY", xauth), **xdg, **game_environment(b, env))
    os.execve(argv[0] if os.path.isabs(argv[0]) else (shutil.which(argv[0]) or argv[0]), argv, child)


def game_start():
    if not installed_game():
        raise ValueError("no game installed")
    r = run("systemctl", "start", "--no-block", "mpf-game.service")
    if r.returncode:
        raise ValueError((r.stderr or r.stdout).strip() or "could not start the game")


def game_stop():
    run("systemctl", "stop", "mpf-game.service")


def game_restart():
    r = run("systemctl", "restart", "--no-block", "mpf-game.service")
    if r.returncode:
        raise ValueError((r.stderr or r.stdout).strip() or "could not restart the game")


def game_autostart():
    return run("systemctl", "is-enabled", "--quiet", "mpf-game.service").returncode == 0


def set_autostart(on):
    """enable/disable writes a link under /etc/systemd: in read-only mode the root opens for that moment only."""
    if on == game_autostart():
        return
    with C.writable("/etc/systemd/system"):
        r = run("systemctl", "enable" if on else "disable", "mpf-game.service")
    if r.returncode:
        raise ValueError((r.stderr or r.stdout).strip() or "systemctl failed")
