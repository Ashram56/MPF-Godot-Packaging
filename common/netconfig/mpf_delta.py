"""Delta install of a game: only the files this machine does not already have are downloaded (standard library only).

Publisher (build_game_package.py --publish, on the build machine), for each built bundle `<game>/<branch>/<version>/`:
  files.json   {"format": 1, "id", "version", "branch", "top", "files": [{path, size, sha256, mode}], "links": [{path, target}], "dirs": [...]}
               `top` is the bundle's top folder name, `path` is relative to it.
  and the files themselves, once per content, as `<game>/objects/<sha[:2]>/<sha256>.xz` (xz of the file): a file that did not change
  between two versions or two branches is stored and downloaded once.
Machine: `install(item)` reads `files.json`, rebuilds the bundle folder in the install stage taking each file from an installed game
that has it (their SHA256SUMS say which, no hashing; hard link when possible) or from the server (sha256 checked), then runs the
same checks and install as an archive (mpf_games.install_staged). An empty cache is a complete install; nothing needs the old
archive. If the server has no files.json the page offers the archive only.
"""
import hashlib
import json
import lzma
import os
import shutil
import threading
import time
import concurrent.futures

import mpf_common as C
import mpf_games as G


WORKERS = 8
MAX_OUT = 4 << 20


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export(root, out_dir, branch="main"):
    """Publisher side: write `files.json` and the missing objects of the bundle folder `root` under `out_dir`.
    Returns (files_json_path, [object paths written])."""
    b = json.load(open(os.path.join(root, "bundle.json")))
    files, links, dirs, written = [], [], [], []
    for dp, dn, fn in os.walk(root):
        rel = os.path.relpath(dp, root)
        if rel != ".":
            dirs.append(rel)
        for n in dn:                                  # a symlink to a folder is listed with the directories by os.walk
            full = os.path.join(dp, n)
            if os.path.islink(full):
                links.append({"path": os.path.relpath(full, root), "target": os.readlink(full)})
        for n in fn:
            full, r = os.path.join(dp, n), os.path.relpath(os.path.join(dp, n), root)
            if os.path.islink(full):
                links.append({"path": r, "target": os.readlink(full)})
                continue
            sha = sha_file(full)
            files.append({"path": r, "size": os.path.getsize(full), "sha256": sha, "mode": os.stat(full).st_mode & 0o777})
            obj = os.path.join(out_dir, "objects", sha[:2], sha + ".xz")
            if not os.path.exists(obj):
                os.makedirs(os.path.dirname(obj), exist_ok=True)
                with open(full, "rb") as f, lzma.open(obj + ".tmp", "wb", preset=6) as g:
                    shutil.copyfileobj(f, g, 1 << 20)
                os.replace(obj + ".tmp", obj)
                written.append(obj)
    doc = {"format": 1, "id": b["id"], "version": str(b["version"]), "branch": branch, "top": os.path.basename(root.rstrip("/")),
           "files": sorted(files, key=lambda f: f["path"]), "links": links, "dirs": sorted(dirs)}
    path = os.path.join(out_dir, "files.json")
    json.dump(doc, open(path, "w"), indent=1)
    return path, written


def local_index():
    """{sha256: path} of the files of every installed game, read from the SHA256SUMS each bundle carries (no hashing)."""
    idx = {}
    for g in G.installed_games():
        try:
            for line in open(os.path.join(g["path"], "SHA256SUMS"), encoding="utf-8", errors="replace"):
                sha, _, name = line.strip().partition("  ")
                full = os.path.join(g["path"], name.lstrip("*"))
                if len(sha) == 64 and name and os.path.isfile(full) and not os.path.islink(full):
                    idx.setdefault(sha, full)
        except OSError:
            continue
    return idx


def _safe(rel):
    parts = rel.split("/")
    if rel.startswith("/") or ".." in parts or "" in parts:
        raise G.JobError(f"unsafe path in files.json: {rel}")
    return rel


def install(item, fetch, keep_old=True):
    """Run in the page's job thread (caller holds G.JOB_LOCK). `fetch(url)` opens a server file as a context manager with .read() (user and password inside);
    item["delta"] is the address of files.json, item["objects"] the address of the objects folder (with a trailing /)."""
    G.job_set(state="running", msg="Reading the file list")
    with fetch(item["delta"]) as r:
        doc = json.loads(r.read(64 << 20))
    if doc.get("format") != 1:
        raise G.JobError("this file list is newer than the page understands")
    G.check_identity({"id": doc.get("id", ""), "version": doc.get("version", "")})
    top = str(doc.get("top", ""))
    if not top or "/" in top or top in (".", ".."):
        raise G.JobError("bad top folder name")
    files = doc["files"]
    need = sum(f["size"] for f in files)
    if G.free_gb(C.GAMES if os.path.isdir(C.GAMES) else "/") * 1e9 < need * 2 + 5e8:
        raise G.JobError("not enough free disk space for this game")
    os.makedirs(C.GAMES, exist_ok=True)
    stage = os.path.join(C.GAMES, ".stage")
    shutil.rmtree(stage, ignore_errors=True)
    root = os.path.join(stage, top)
    os.makedirs(root)
    for d in doc.get("dirs", []):
        os.makedirs(os.path.join(root, _safe(d)), exist_ok=True)
    idx = local_index()
    reused, remote = 0, []
    for f in files:
        dest = os.path.join(root, _safe(f["path"]))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        src = idx.get(f["sha256"])
        if src:
            try:
                os.link(src, dest)
            except OSError:
                shutil.copy2(src, dest)
            os.chmod(dest, f.get("mode", 0o644))
            reused += 1
        else:
            remote.append((f, dest))
    total = sum(f["size"] for f, _ in remote)
    G.job_set(msg=f"Delta: {reused} files already here, {len(remote)} to download ({total >> 20} MB)")
    state = {"files": 0, "bytes": 0, "t": 0.0, "stop": False}
    lock = threading.Lock()

    def progress(done_bytes, done_file=False):
        with lock:
            state["bytes"] += done_bytes
            state["files"] += 1 if done_file else 0
            if time.time() - state["t"] >= 1.0:
                state["t"] = time.time()
                G.job_set(msg=f"Delta: {state['files']}/{len(remote)} files, {state['bytes'] >> 20} of {total >> 20} MB downloaded ({reused} kept)")

    def get(job):
        f, dest = job
        h, dec = hashlib.sha256(), lzma.LZMADecompressor()
        try:
            with fetch(item["objects"] + f"{f['sha256'][:2]}/{f['sha256']}.xz") as r, open(dest, "wb") as out:
                while True:
                    if state["stop"]:
                        return
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    data = dec.decompress(chunk, MAX_OUT)       # a megabyte of zeros is a few bytes of xz: never expand it all at once
                    while True:
                        h.update(data)
                        out.write(data)
                        progress(len(data))
                        if dec.needs_input or dec.eof:
                            break
                        data = dec.decompress(b"", MAX_OUT)
        except lzma.LZMAError:
            raise G.JobError(f"{f['path']}: the download is damaged, try again")
        if h.hexdigest() != f["sha256"] or not dec.eof:
            raise G.JobError(f"{f['path']}: checksum mismatch, try again")
        os.chmod(dest, f.get("mode", 0o644))
        progress(0, True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:     # one connection per file: many small ones are slow one by one
        futures = [pool.submit(get, j) for j in remote]
        try:
            for fu in concurrent.futures.as_completed(futures):
                fu.result()
        except BaseException:
            state["stop"] = True
            for fu in futures:
                fu.cancel()
            raise
    got, fetched = len(remote), state["bytes"]
    for l in doc.get("links", []):
        dest = os.path.join(root, _safe(l["path"]))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.lexists(dest):
            os.remove(dest)
        if l["target"].startswith("/") or ".." in l["target"].split("/"):
            raise G.JobError(f"unsafe link in files.json: {l['path']}")
        os.symlink(l["target"], dest)
    G.job_log(f"delta: {reused} files already here, {got} downloaded ({fetched >> 20} MB)")
    G.job_set(msg="Checking the game (trial start)")
    G.install_staged(stage, None, keep_old, str(item.get("branch") or doc.get("branch") or ""))
