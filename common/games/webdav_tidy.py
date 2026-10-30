#!/usr/bin/env python3
"""Put the files of the updates folder in sub-folders: one per game (named by its id), `PuP Packs` for the packs.

    WEBDAV_USER=... WEBDAV_PASS=... python3 webdav_tidy.py https://server.example/MPF%20Games            # shows what it would move
    WEBDAV_USER=... WEBDAV_PASS=... python3 webdav_tidy.py https://server.example/MPF%20Games --apply    # moves it
    ... python3 webdav_tidy.py URL --put-pack my-pack.zip                                               # adds a pack in `PuP Packs`

build_game_package.py --publish already writes `<game id>/<archive>`; loose files at the root come from uploads by hand. The game of
an archive is found in `mpf-games.json` (the file name is listed there) or, failing that, from its name (`<id>-<version>-...tar.xz`
or `<id>@<version>...`). What cannot be placed is left where it is and reported. The manifest follows the move.
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

PACKS = "PuP Packs"
DAV = "{DAV:}"


def target_for(name, manifest):
    """Sub-folder an archive belongs in (None when unknown)."""
    if name.lower().endswith(".zip"):
        return PACKS
    for i in manifest:
        if i.get("file", "").rsplit("/", 1)[-1] == name and i.get("id"):
            return i["id"]
    m = re.match(r"^([A-Za-z0-9_.]+?)(?:@|-\d|-v\d|-[0-9a-f]{7,})", name)
    return m.group(1) if m and name.endswith((".tar.xz", ".tar.xz.sha256")) else None


def plan(loose, manifest):
    """([(file, folder)], [file left]) for the files at the root: `x.tar.xz.sha256` follows its archive."""
    moves, left = [], []
    for n in sorted(loose):
        if not n.endswith((".tar.xz", ".tar.xz.sha256", ".zip")):
            continue
        folder = target_for(n[:-7] if n.endswith(".sha256") else n, manifest)
        (moves if folder else left).append((n, folder) if folder else n)
    return moves, left


class Dav:
    def __init__(self, url, user, pw):
        self.root = url.rstrip("/") + "/"
        self.auth = "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()

    def req(self, method, url, data=None, headers=None):
        r = urllib.request.Request(url, data=data, method=method, headers=dict({"Authorization": self.auth}, **(headers or {})))
        try:
            with urllib.request.urlopen(r, timeout=600) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, b""

    def files(self):
        code, body = self.req("PROPFIND", self.root, b'<?xml version="1.0"?><propfind xmlns="DAV:"><prop><resourcetype/></prop></propfind>',
                              {"Depth": "1", "Content-Type": "application/xml"})
        if code not in (200, 207):
            raise SystemExit(f"cannot list {self.root}: HTTP {code}")
        out = []
        here = urllib.parse.unquote(urllib.parse.urlparse(self.root).path).rstrip("/")
        for r in ET.fromstring(body).iter(DAV + "response"):
            path = urllib.parse.unquote(urllib.parse.urlparse(r.findtext(DAV + "href") or "").path)
            if path.rstrip("/") != here and r.find(f"{DAV}propstat/{DAV}prop/{DAV}resourcetype/{DAV}collection") is None:
                out.append(os.path.basename(path))
        return out

    def manifest(self):
        code, body = self.req("GET", self.root + "mpf-games.json")
        try:
            return json.loads(body) if code == 200 else {"format": 1, "items": []}
        except ValueError:
            return {"format": 1, "items": []}

    def q(self, *parts):
        return self.root + "/".join(urllib.parse.quote(p) for p in parts)

    def move(self, name, folder):
        self.req("MKCOL", self.q(folder) + "/")
        code, _ = self.req("MOVE", self.q(name), headers={"Destination": self.q(folder, name), "Overwrite": "F"})
        return code in (201, 204)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", help="the updates folder on the WebDAV server")
    ap.add_argument("--apply", action="store_true", help="do the moves (without it only shows them)")
    ap.add_argument("--put-pack", metavar="ZIP", help="upload a PuP Pack into the `PuP Packs` sub-folder")
    a = ap.parse_args()
    user, pw = os.environ.get("WEBDAV_USER", ""), os.environ.get("WEBDAV_PASS", "")
    if not user or not pw:
        sys.exit("WEBDAV_USER and WEBDAV_PASS must be in the environment")
    d = Dav(a.url, user, pw)
    if a.put_pack:
        d.req("MKCOL", d.q(PACKS) + "/")
        with open(a.put_pack, "rb") as f:
            code, _ = d.req("PUT", d.q(PACKS, os.path.basename(a.put_pack)), f.read())
        sys.exit(0 if code in (200, 201, 204) else f"upload failed: HTTP {code}")
    doc = d.manifest()
    moves, left = plan(d.files(), doc.get("items", []))
    for n, folder in moves:
        print(("moving " if a.apply else "would move ") + f"{n} -> {folder}/")
        if a.apply and not d.move(n, folder):
            print(f"  FAILED: {n}")
    for n in left:
        print(f"left (game unknown): {n}")
    if a.apply and moves:
        for i in doc.get("items", []):
            f = i.get("file", "")
            if "/" not in f and any(n == f for n, _ in moves):
                i["file"] = i["id"] + "/" + f
        d.req("PUT", d.root + "mpf-games.json", json.dumps(doc, indent=1).encode())
    if not moves and not left:
        print("nothing loose at the root")
    elif not a.apply and moves:
        print("add --apply to move them")


if __name__ == "__main__":
    main()
