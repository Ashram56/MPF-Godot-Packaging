"""A shared cache of Godot's import, on a WebDAV folder (platforms/game-bundles.md, "Import cache").

Godot's import (`.import` file next to a medium + `.godot/imported/*`) depends only on the medium's content, Godot's version
and the import settings. So it is stored once per medium, by a key made of those, and fetched instead of redone: a build on a
clean machine starts Godot only for the media nobody imported before.

    cache = ImportCache(url, godot_version, formats, project_godot_path)
    cache.restore(stage, game_rel)      # before `godot --import`: fetch what the cache has
    cache.store(stage, game_rel)        # after it: send what was missing

Layout on the server: `<url>/import-cache/<godot>/<xx>/<key>.tar` (xx = the key's first two characters), one small tar per
medium holding its `.import` and the files it lists in `dest_files` (+ the `.md5` Godot checks). Credentials: WEBDAV_USER and
WEBDAV_PASS in the environment. Standard library only. A server that cannot be reached is a warning, never a failed build.
"""
import base64
import concurrent.futures
import hashlib
import io
import os
import re
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

MEDIA_EXT = (".png", ".jpg", ".jpeg", ".webp", ".svg", ".ogg", ".wav", ".mp3")
SETTINGS_LINE = re.compile(r"^(textures/|importer_defaults|\[importer_defaults\]|audio/|rendering/textures)", re.M)


def say(text):
    print(text, flush=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def settings_digest(project_godot):
    """The project settings that change what an import produces."""
    with open(project_godot, encoding="utf-8") as f:
        text = f.read()
    return hashlib.sha256("\n".join(l for l in text.split("\n") if SETTINGS_LINE.match(l)).encode()).hexdigest()


def import_files(stage, game_rel):
    """(media path relative to the stage) for every medium with an .import file, outside .godot."""
    out = []
    top = os.path.join(stage, game_rel)
    for base, dirs, names in os.walk(top):
        dirs[:] = [d for d in dirs if d != ".godot"]
        for name in names:
            if name.endswith(".import") and os.path.isfile(os.path.join(base, name[:-7])):
                out.append(os.path.relpath(os.path.join(base, name[:-7]), stage).replace(os.sep, "/"))
    return sorted(out)


def listed_files(import_text):
    """res:// paths a .import file lists in dest_files, with the .md5 Godot writes beside them."""
    m = re.search(r"^dest_files=\[(.*)\]", import_text, re.M)
    files = re.findall(r'"res://([^"]*)"', m.group(1)) if m else []
    out = list(files)
    for f in files:
        k = re.match(r"(.*-[0-9a-f]{32})\.", f)
        if k and k.group(1) + ".md5" not in out:
            out.append(k.group(1) + ".md5")
    return out


class ImportCache:
    def __init__(self, url, godot_version, formats, project_godot, salt="", jobs=32):
        user, pw = os.environ.get("WEBDAV_USER", ""), os.environ.get("WEBDAV_PASS", "")
        if not user or not pw:
            raise SystemExit("--import-cache needs WEBDAV_USER and WEBDAV_PASS in the environment")
        self.auth = "Basic " + base64.b64encode("{}:{}".format(user, pw).encode()).decode()
        self.base = url.rstrip("/") + "/import-cache/" + urllib.parse.quote(godot_version) + "/"
        self.godot, self.formats, self.salt, self.jobs = godot_version, formats, salt, jobs
        self.project_godot = project_godot
        self.missing = {}          # media path -> key, filled by restore, stored by store
        self.dirs = set()
        self.ok = True

    # -- WebDAV --
    def req(self, method, target, data=None):
        r = urllib.request.Request(target, data=data, method=method, headers={"Authorization": self.auth})
        for k in range(4):
            try:
                with urllib.request.urlopen(r, timeout=120) as resp:
                    return resp.status, resp.read()
            except urllib.error.HTTPError as e:
                if e.code in (423, 500, 502, 503) and k < 3:
                    time.sleep(2 ** k)
                    continue
                return e.code, b""
            except OSError:
                if k == 3:
                    raise
                time.sleep(2 ** k)
        return 0, b""

    def mkcol(self, target):
        if target in self.dirs:
            return
        code, _ = self.req("MKCOL", target)
        if code not in (200, 201, 301, 405):
            raise OSError("cannot create {}: HTTP {}".format(target, code))
        self.dirs.add(target)

    def url_of(self, key):
        return "{}{}/{}.tar".format(self.base, key[:2], key)

    def key(self, stage, game_rel, media):
        """sha256 of: the medium, its .import before the import (may be absent), Godot, formats, project import settings, salt."""
        pre = ""
        p = os.path.join(stage, media + ".import")
        if os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                pre = f.read()
        h = hashlib.sha256()
        for part in (sha256_file(os.path.join(stage, media)), pre, self.godot, self.formats,
                     settings_digest(self.project_godot), self.salt):
            h.update(part.encode() + b"\0")
        return h.hexdigest()

    # -- restore / store --
    def restore(self, stage, game_rel):
        """Fetch the import of every medium the cache has; returns (hits, misses). The misses are left for Godot."""
        media = import_files(stage, game_rel)
        # the .import files that exist now are the seeded/tracked ones; media without one are found by extension
        top = os.path.join(stage, game_rel)
        for base, dirs, names in os.walk(top):
            dirs[:] = [d for d in dirs if d != ".godot"]
            for name in names:
                rel = os.path.relpath(os.path.join(base, name), stage).replace(os.sep, "/")
                if name.lower().endswith(MEDIA_EXT) and rel not in media:
                    media.append(rel)
        media.sort()
        keys = {m: self.key(stage, game_rel, m) for m in media}

        def one(m):
            try:
                code, body = self.req("GET", self.url_of(keys[m]))
            except OSError:
                return m, None, True
            if code != 200:
                return m, None, False
            with tarfile.open(fileobj=io.BytesIO(body)) as t:
                for member in t.getmembers():
                    name = member.name
                    if member.isfile() and not name.startswith(("/", "..")) and ".." not in name.split("/"):
                        dst = os.path.join(stage, name)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        with open(dst, "wb") as f:
                            f.write(t.extractfile(member).read())
            return m, keys[m], False

        hits = 0
        failed = False
        with concurrent.futures.ThreadPoolExecutor(self.jobs) as ex:
            for m, got, down in ex.map(one, media):
                failed = failed or down
                if got:
                    hits += 1
                else:
                    self.missing[m] = keys[m]
        if failed:
            self.ok = False
            say("   WARNING: the import cache could not be read completely; the missing media are imported by Godot")
        return hits, len(self.missing)

    def store(self, stage, game_rel):
        """Send the import of the media restore did not find. Returns the number uploaded."""
        if not self.ok and not self.missing:
            return 0
        todo = []
        for m, key in self.missing.items():
            ip = os.path.join(stage, m + ".import")
            if not os.path.isfile(ip):
                continue
            with open(ip, encoding="utf-8", errors="replace") as f:
                text = f.read()
            members = [m + ".import"] + [(game_rel + "/" + p if not p.startswith(game_rel + "/") and game_rel not in (".", "") and False else p)
                                         for p in listed_files(text)]
            # paths in dest_files are res:// of the Godot project: relative to game_rel in the stage
            members = [m + ".import"] + [game_rel + "/" + p if game_rel not in (".", "") else p for p in listed_files(text)]
            if all(os.path.isfile(os.path.join(stage, x)) for x in members):
                todo.append((key, members))
        if not todo:
            return 0
        try:
            self.mkcol(self.base.rsplit("/", 2)[0] + "/")
            self.mkcol(self.base)
            for pre in sorted({k[:2] for k, _ in todo}):
                self.mkcol("{}{}/".format(self.base, pre))
        except OSError as e:
            say("   WARNING: import cache not updated: {}".format(e))
            return 0

        def one(item):
            key, members = item
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as t:
                for x in members:
                    t.add(os.path.join(stage, x), arcname=x, recursive=False)
            try:
                code, _ = self.req("PUT", self.url_of(key), buf.getvalue())
            except OSError:
                return 0
            return 1 if code in (200, 201, 204) else 0

        with concurrent.futures.ThreadPoolExecutor(self.jobs) as ex:
            sent = sum(ex.map(one, todo))
        if sent < len(todo):
            say("   WARNING: {} of {} import objects could not be uploaded".format(len(todo) - sent, len(todo)))
        return sent
