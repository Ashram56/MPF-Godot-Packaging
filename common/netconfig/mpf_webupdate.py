"""Update of the setup page itself (the "web package", see mpf_launch.py) from GitHub (any branch) or from the WebDAV server.

Sources:
  github  a public repository (default Ashram56/MPF-Godot-Packaging) and a branch: the branch's tarball from codeload.github.com, of which
          only `common/netconfig/mpf_*.py` is kept (no git on the machine, nothing else touched).
  webdav  the update server of mpf_ota (same address, user and password) folder `web/` : `mpf-web-<id>.tar.xz` (+ `.sha256`) made by
          make_web_package.py.
The package goes to `<WEB_DIR>/<id>/`, is checked (manifest `api`, every file compiles), `current` is switched to it and the page
restarts. Safety: `previous` keeps the older link; mpf_launch.py counts the starts of a package that was not confirmed
(`pending.json`) and, after 3 starts without a confirm() (the page confirms 10 s after it listens), marks it `.bad` and goes back to
`previous`. The engine (Godot, GoZen, dmd_bridge, kernel) is not part of it: that is an image update.
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.error
import urllib.request

import mpf_common as C
import mpf_games as G
import mpf_launch as L
import mpf_ota as O

DEFAULT_REPO = "Ashram56/MPF-Godot-Packaging"
KEEP = 3                                  # packages kept on disk besides the one in use and the previous one
NAME = re.compile(r"^mpf_[a-z0-9_]+\.py$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
UA = {"User-Agent": "mpf-webupdate"}


def conf_path():
    return os.path.join(C.STATE_DIR, "webupdate.json")


def load():
    try:
        c = json.load(open(conf_path(), encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    return {"source": c.get("source", "github"), "repo": c.get("repo") or DEFAULT_REPO, "branch": c.get("branch") or "main"}


def save(source, repo, branch):
    if source not in ("github", "webdav"):
        raise ValueError("unknown source")
    repo, branch = (repo or DEFAULT_REPO).strip(), (branch or "main").strip()
    if not REPO.match(repo):
        raise ValueError("the repository must look like owner/name")
    if not BRANCH.match(branch) or ".." in branch:
        raise ValueError("invalid branch name")
    os.makedirs(C.STATE_DIR, exist_ok=True)
    json.dump({"source": source, "repo": repo, "branch": branch}, open(conf_path(), "w"))


def _wd():
    return L.WEB_DIR


def _manifest(folder):
    try:
        return json.load(open(os.path.join(folder, "manifest.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status():
    cur = os.path.join(_wd(), "current")
    link = os.path.realpath(cur) if os.path.isdir(cur) else ""
    man = _manifest(link) if link else None
    pend = _read_pending()
    return {"running": os.environ.get("MPF_WEB_PACKAGE", "image"), "api": L.API, "writable": os.access(_wd(), os.W_OK) or not os.path.exists(_wd()),
            "current": man, "previous": os.path.basename(pend.get("previous", "")) if pend else "",
            "pending": bool(pend), "has_previous": bool(_previous()), "config": load()}


def _read_pending():
    try:
        return json.load(open(os.path.join(_wd(), "pending.json")))
    except (OSError, ValueError):
        return None


def _previous():
    try:
        return json.load(open(os.path.join(_wd(), "previous.json"))).get("path", "")
    except (OSError, ValueError):
        return ""


def _get(url, headers=None, limit=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    try:
        return urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        raise ValueError(f"GitHub answered {e.code}" + (" (branch or repository not found)" if e.code == 404 else ""))
    except (urllib.error.URLError, OSError) as e:
        raise ValueError(f"cannot reach the server: {getattr(e, 'reason', e)}")


def branches(repo=None):
    """[{name, sha, date}] of the repository's branches (GitHub API, public repository)."""
    repo = repo or load()["repo"]
    if not REPO.match(repo):
        raise ValueError("invalid repository")
    out = []
    for page in (1, 2, 3):
        with _get(f"https://api.github.com/repos/{repo}/branches?per_page=100&page={page}") as r:
            part = json.loads(r.read(1 << 22))
        out += [{"name": b["name"], "sha": b["commit"]["sha"][:8]} for b in part]
        if len(part) < 100:
            break
    return out


def _api_of(src):
    m = re.search(rb"^API\s*=\s*(\d+)", src, re.M)
    return int(m.group(1)) if m else None


def _stage(files, meta):
    """Write {name: bytes} to a fresh folder `<id>.new`, check it, rename it to `<id>`; returns its path."""
    pid = meta["id"]
    if not re.match(r"^[A-Za-z0-9._-]+$", pid):
        raise G.JobError("invalid package id")
    if "mpf_netconfig.py" not in files or "mpf_launch.py" not in files:
        raise G.JobError("this branch has no web package (mpf_netconfig.py / mpf_launch.py missing)")
    api = _api_of(files["mpf_launch.py"])
    if api != L.API:
        raise G.JobError(f"this version needs web API {api}, this image has {L.API}: it needs a new image")
    os.makedirs(_wd(), exist_ok=True)
    tmp, dest = os.path.join(_wd(), pid + ".new"), os.path.join(_wd(), pid)
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    for n, data in files.items():
        with open(os.path.join(tmp, n), "wb") as f:
            f.write(data)
        os.chmod(os.path.join(tmp, n), 0o755)
    man = {"format": 1, "id": pid, "api": api, "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}, **{k: v for k, v in meta.items() if k != "id"}}
    json.dump(man, open(os.path.join(tmp, "manifest.json"), "w"), indent=1)
    if not L.usable(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
        raise G.JobError("the package does not compile or is incomplete")
    shutil.rmtree(dest, ignore_errors=True)
    os.rename(tmp, dest)
    return dest


def _read_github(repo, branch):
    G.job_set(state="running", msg=f"Looking up {repo}@{branch}")
    with _get(f"https://api.github.com/repos/{repo}/commits/{branch}", {"Accept": "application/vnd.github+json"}) as r:
        sha = json.loads(r.read(1 << 22))["sha"][:8]
    G.job_set(msg=f"Downloading {repo}@{branch}")
    with _get(f"https://codeload.github.com/{repo}/tar.gz/refs/heads/{branch}") as r:
        data = r.read(200 << 20)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        for m in t:
            parts = m.name.split("/")
            if m.isreg() and len(parts) == 4 and parts[1:3] == ["common", "netconfig"] and NAME.match(parts[3]) and m.size < 4 << 20:
                files[parts[3]] = t.extractfile(m).read()
    pid = re.sub(r"[^A-Za-z0-9._-]+", "_", branch) + "-" + sha
    return files, {"id": pid, "branch": branch, "sha": sha, "source": f"github:{repo}"}


def _read_webdav(name):
    cfg = O.load()
    if not cfg.get("url"):
        raise G.JobError("set the update server address first (Install tab)")
    if not re.match(r"^mpf-web-[A-Za-z0-9._-]+\.tar\.xz$", name):
        raise G.JobError("invalid package name")
    url = O.base(cfg) + "web/" + name
    os.makedirs(C.UPLOADS, exist_ok=True)
    dest = os.path.join(C.UPLOADS, "web.tar.xz")
    O._download(cfg, url, dest, name)
    try:
        with O._open(cfg, url + ".sha256") as r:
            want = (r.read(4096).decode(errors="replace").split() or [""])[0]
    except ValueError:
        want = ""
    got = hashlib.sha256(open(dest, "rb").read()).hexdigest()
    if want and want != got:
        raise G.JobError("the checksum does not match: download again")
    files, man = {}, {}
    with tarfile.open(dest) as t:
        for m in t:
            parts = m.name.split("/")
            if m.isreg() and len(parts) == 2 and m.size < 4 << 20:
                if NAME.match(parts[1]):
                    files[parts[1]] = t.extractfile(m).read()
                elif parts[1] == "manifest.json":
                    man = json.loads(t.extractfile(m).read())
    os.remove(dest)
    pid = man.get("id") or name[len("mpf-web-"):-len(".tar.xz")]
    return files, {"id": pid, "branch": man.get("branch", ""), "sha": man.get("sha", ""), "source": "webdav"}


def list_webdav():
    cfg = O.load()
    if not cfg.get("url"):
        raise ValueError("set the update server address first (Install tab)")
    out = []
    for e in O.propfind(cfg, O.base(cfg) + "web/"):
        if not e["dir"] and re.match(r"^mpf-web-.*\.tar\.xz$", e["name"]):
            out.append({"name": e["name"], "size": e["size"], "mtime": e["mtime"]})
    return sorted(out, key=lambda x: x["mtime"] or "", reverse=True)


def _restart():
    subprocess.Popen(["sh", "-c", "sleep 2; systemctl restart mpf-netconfig-web.service"], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def switch(folder, restart=True):
    """Make `folder` the package in use (atomic link swap), remember the one it replaces, arm the start counter."""
    wd = _wd()
    cur = os.path.join(wd, "current")
    prev = os.path.realpath(cur) if os.path.isdir(cur) else ""
    json.dump({"path": prev}, open(os.path.join(wd, "previous.json"), "w"))
    json.dump({"id": os.path.basename(folder), "previous": prev, "starts": 0}, open(os.path.join(wd, "pending.json"), "w"))
    tmp = cur + ".new"
    if os.path.lexists(tmp):
        os.remove(tmp)
    os.symlink(folder, tmp)
    os.replace(tmp, cur)
    _prune(folder, prev)
    if restart:
        _restart()


def _prune(*keep):
    wd = _wd()
    keep = {os.path.realpath(k) for k in keep if k}
    olds = sorted((os.path.join(wd, d) for d in os.listdir(wd) if os.path.isdir(os.path.join(wd, d)) and not os.path.islink(os.path.join(wd, d))
                   and os.path.exists(os.path.join(wd, d, "manifest.json")) and os.path.realpath(os.path.join(wd, d)) not in keep),
                  key=os.path.getmtime, reverse=True)
    for d in olds[KEEP:]:
        shutil.rmtree(d, ignore_errors=True)


def install(source, branch="", repo="", name=""):
    """Run in the page's job thread (caller holds G.JOB_LOCK): fetch, check, switch, restart the page."""
    if source == "github":
        repo, branch = repo or load()["repo"], branch or load()["branch"]
        if not REPO.match(repo) or not BRANCH.match(branch) or ".." in branch:
            raise G.JobError("invalid repository or branch")
        files, meta = _read_github(repo, branch)
    else:
        files, meta = _read_webdav(name)
    G.job_set(msg="Checking the package")
    folder = _stage(files, meta)
    if os.path.realpath(folder) == os.path.realpath(os.path.join(_wd(), "current")):
        G.job_set(state="done", msg="This version is already in use")
        return
    switch(folder)
    G.job_set(state="done", msg=f"Page updated to {meta['id']}: it restarts in a few seconds (reload it)")


def rollback():
    """Back to the package (or the image's copy) that was in use before the last switch."""
    wd = _wd()
    prev = _previous()
    cur = os.path.join(wd, "current")
    if prev and os.path.isdir(prev):
        tmp = cur + ".new"
        if os.path.lexists(tmp):
            os.remove(tmp)
        os.symlink(prev, tmp)
        os.replace(tmp, cur)
    elif os.path.lexists(cur):
        os.remove(cur)                      # none before: the image's own copy
    else:
        raise ValueError("nothing to go back to")
    for f in ("pending.json", "previous.json"):
        try:
            os.remove(os.path.join(wd, f))
        except OSError:
            pass
    _restart()


def confirm():
    """The page is listening: the package in use works, stop counting its starts."""
    try:
        os.remove(os.path.join(_wd(), "pending.json"))
    except OSError:
        pass


def confirm_later(delay=10):
    threading.Timer(delay, confirm).start()
