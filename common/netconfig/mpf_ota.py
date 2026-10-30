"""Over-the-air updates of games and PuP Packs from a WebDAV folder (standard library only).

The server address is the server only (https://host/…); the *folder* on it is a second field, "MPF Games" by default.
The server holds bundles (`*.tar.xz`, with an optional `*.tar.xz.sha256` beside) and PuP Packs (`<id>.pup.zip` or
`<id>@<version>.pup.zip`: the name says which game a pack is for) either in the configured folder or in sub-folders of it (one per
game). The page lists them (PROPFIND), installs the chosen one exactly like an upload (same checks, same new-version rules, see
common/games/README.md) and remembers what it installed, so the list says *installed* or *changed on the server*.

The address, user and password are typed on the page and kept on this machine only, in `ota.json` of the state folder (mode 0600,
on the data partition in read-only mode). Redirects are refused (the password must not follow one to another host).
"""
import base64
import json
import os
import platform
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import mpf_common as C
import mpf_games as G

DAV = "{DAV:}"
TIMEOUT = 30
DEFAULT_FOLDER = "MPF Games"


def conf_path():
    return os.path.join(C.STATE_DIR, "ota.json")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def load():
    return _read(conf_path())


def public():
    """What the page may see: never the password."""
    c = load()
    return {"url": c.get("url", ""), "folder": c.get("folder", DEFAULT_FOLDER), "user": c.get("user", ""),
            "has_password": bool(c.get("password"))}


def base(cfg):
    """Address of the folder the page lists: the server address, then the folder (every segment percent-encoded)."""
    segs = [urllib.parse.quote(x) for x in (cfg.get("folder", DEFAULT_FOLDER) or "").strip("/").split("/") if x]
    return cfg["url"].rstrip("/") + "/" + "".join(x + "/" for x in segs)


def save(url, user, password, folder=DEFAULT_FOLDER):
    url = url.strip()
    if url and not re.match(r"^https?://[^/\s]+", url):
        raise ValueError("the address must start with https:// (or http:// on a trusted network)")
    old = load()
    folder = (folder or "").strip().strip("/")
    if ".." in folder.split("/"):
        raise ValueError("the folder must not contain ..")
    cfg = {"url": url.rstrip("/") + "/" if url else "", "folder": folder, "user": user.strip(), "password": password or old.get("password", "")}
    if (old.get("url"), old.get("folder"), old.get("user")) != (cfg["url"], cfg["folder"], cfg["user"]):
        cfg["installed"] = {}
    else:
        cfg["installed"] = old.get("installed", {})
    _write(conf_path(), cfg)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _open(cfg, url, method="GET", headers=None, body=None):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    if cfg.get("user"):
        tok = base64.b64encode(f"{cfg['user']}:{cfg.get('password', '')}".encode()).decode()
        req.add_header("Authorization", "Basic " + tok)
    try:
        return urllib.request.build_opener(_NoRedirect).open(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ValueError("the server refused the user or password")
        if e.code == 404:
            raise ValueError("folder not found on the server")
        raise ValueError(f"the server answered {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise ValueError(f"cannot reach the server: {getattr(e, 'reason', e)}")


def propfind(cfg, url):
    """[{url, name, dir, size, mtime}] of the entries of one folder (not the folder itself)."""
    body = b'<?xml version="1.0"?><propfind xmlns="DAV:"><prop><getcontentlength/><getlastmodified/><resourcetype/></prop></propfind>'
    with _open(cfg, url, "PROPFIND", {"Depth": "1", "Content-Type": "application/xml"}, body) as r:
        tree = ET.fromstring(r.read())
    here = urllib.parse.urlparse(url).path.rstrip("/")
    out = []
    for resp in tree.iter(DAV + "response"):
        href = resp.findtext(DAV + "href") or ""
        path = urllib.parse.unquote(urllib.parse.urlparse(href).path)
        if path.rstrip("/") == urllib.parse.unquote(here):
            continue
        prop = resp.find(f"{DAV}propstat/{DAV}prop")
        is_dir = prop is not None and prop.find(f"{DAV}resourcetype/{DAV}collection") is not None
        size = int((prop.findtext(DAV + "getcontentlength") or "0") if prop is not None else 0) if not is_dir else 0
        mtime = (prop.findtext(DAV + "getlastmodified") or "") if prop is not None else ""
        out.append({"url": urllib.parse.urljoin(url, urllib.parse.quote(path)), "name": os.path.basename(path.rstrip("/")),
                    "dir": is_dir, "size": size, "mtime": mtime})
    return out


MANIFEST = "mpf-games.json"


def read_manifest(cfg):
    """The `mpf-games.json` build_game_package.py --publish keeps at the root of the folder, or None when there is none.
    {"format": 1, "items": [{id, name, version, arch, file, size, sha256}]}"""
    try:
        with _open(cfg, base(cfg) + MANIFEST) as r:
            doc = json.loads(r.read(1 << 20))
    except ValueError:
        return None          # no such file (404) or not JSON: the folder is listed as it is
    items = doc.get("items") if isinstance(doc, dict) and doc.get("format") == 1 else None
    return [i for i in items if isinstance(i, dict) and i.get("file") and i.get("id")] if isinstance(items, list) else None


def manifest_items(cfg, entries, installed, me):
    """Game items from the manifest: only the ones for this machine, each saying what it does to the installed games."""
    out = []
    for e in entries:
        arch = e.get("arch", "all")
        if arch not in ("all", me):
            continue
        have = [g for g in installed if g["id"] == e["id"]]
        names = {g["version"] for g in have}
        key = e["file"]
        newer = bool(have) and str(e.get("version", "")) not in names
        out.append({"key": key, "name": e["file"].rsplit("/", 1)[-1], "group": "", "kind": "game", "size": int(e.get("size") or 0), "mtime": e.get("published", ""),
                    "url": base(cfg) + "/".join(urllib.parse.quote(x) for x in e["file"].split("/")), "sha_url": "", "sha": e.get("sha256", ""),
                    "compatible": True, "installed": bool(have) and not newer,
                    "changed": False, "version": str(e.get("version", "")), "label": e.get("name", e["id"]),
                    "for": (have[0]["name"] + " " + ", ".join(sorted(names))) if have else "", "update": newer})
    return out


def list_remote(cfg=None):
    """Bundles and packs on the server (the folder and its sub-folders), each with what the page needs to show and install it."""
    cfg = cfg or load()
    if not cfg.get("url"):
        raise ValueError("set the server address first")
    me = C.ARCH.get(platform.machine(), platform.machine())
    entries = []
    for e in propfind(cfg, base(cfg)):
        if e["dir"]:
            entries += [dict(x, group=e["name"]) for x in propfind(cfg, e["url"] + ("" if e["url"].endswith("/") else "/")) if not x["dir"]]
        else:
            entries.append(dict(e, group=""))
    names = {(e["group"], e["name"]) for e in entries}
    manifest = read_manifest(cfg)
    done = cfg.get("installed", {})
    installed = G.installed_games()
    items = []
    for e in sorted(entries, key=lambda e: (e["group"], e["name"])):
        n = e["name"]
        if n.endswith(".tar.xz"):
            if manifest is not None:
                continue          # a manifest says which bundles are offered
            kind = "game"
        elif n.lower().endswith(".zip"):
            kind = "pup"
        else:
            continue
        compatible = not ("linux-" in n and kind == "game" and not n.endswith((f"linux-{me}.tar.xz", "linux-all.tar.xz")))
        key = (e["group"] + "/" if e["group"] else "") + n
        stamp = f"{e['size']}|{e['mtime']}"
        target = next((g for g in installed if n.startswith(g["id"] + "-") or n.startswith(g["id"] + "@")
                       or (e["group"] and e["group"].lower() == g["id"].lower())), None) if kind == "game" else None
        items.append({"key": key, "for": (target["name"] + " " + target["version"]) if target else "", "name": n, "group": e["group"], "kind": kind, "size": e["size"], "mtime": e["mtime"], "url": e["url"],
                      "sha_url": e["url"] + ".sha256" if (e["group"], n + ".sha256") in names else "",
                      "compatible": compatible, "installed": key in done, "loose": not e["group"],
                      "changed": key in done and done[key] != stamp})
    if manifest is not None:
        items = manifest_items(cfg, manifest, installed, me) + items
    return items


def _download(cfg, url, dest, label):
    G.job_set(state="running", msg=f"Downloading {label}")
    got, last = 0, 0
    with _open(cfg, url) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        if total and G.free_gb(os.path.dirname(dest)) * 1e9 < total * 4 + 5e8:
            raise G.JobError("not enough free disk space for this file")
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if got - last > 8 << 20:
                last = got
                G.job_set(msg=f"Downloading {label}: {got >> 20} MB" + (f" of {total >> 20} MB" if total else ""))
    if total and got != total:
        raise G.JobError("the download was cut: try again")


def install_item(item):
    """Download one listed item and install it (run in the page's job thread; the caller holds G.JOB_LOCK)."""
    cfg = load()
    name = item["name"]
    os.makedirs(C.UPLOADS, exist_ok=True)
    if item["kind"] == "game":
        dest = os.path.join(C.UPLOADS, "game.tar.xz")
        sha = item.get("sha") or ""
        if not sha and item.get("sha_url"):
            with _open(cfg, item["sha_url"]) as r:
                sha = (r.read(4096).decode(errors="replace").split() or [""])[0]
        _download(cfg, item["url"], dest, name)
        G.install_game(dest, sha)
    else:
        dest = os.path.join(C.UPLOADS, "pup.zip")
        _download(cfg, item["url"], dest, name)
        G.pup_store(dest, name)           # into the library: the page assigns it to a game
        G.job_set(state="done", msg=f"{name} is in the PuP Pack library: assign it to a game")
    cfg = load()
    cfg.setdefault("installed", {})[item["key"]] = f"{item['size']}|{item['mtime']}"
    _write(conf_path(), cfg)
