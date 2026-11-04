"""Updates from a WebDAV folder (common/netconfig/mpf_ota.py), against a small local server."""
import sys as _sys
import unittest as _unittest

if not _sys.platform.startswith("linux"):
    raise _unittest.SkipTest("the platform page and its netconfig code run on the Linux images only")

import hashlib
import http.server
import json
import os
import threading
import unittest
from xml.sax.saxutils import escape

from tests import test_games as TG

C, G = TG.C, TG.G
import mpf_ota as O  # noqa: E402


class Dav(http.server.BaseHTTPRequestHandler):
    root = ""
    auth = "Basic " + __import__("base64").b64encode(b"claude:secret").decode()
    seen = []
    gets = []
    deleted = []

    def log_message(self, *a):
        pass

    def _ok(self):
        Dav.seen.append(self.headers.get("Authorization"))
        if self.headers.get("Authorization") != Dav.auth:
            self.send_response(401)
            self.end_headers()
            return False
        return True

    def do_PROPFIND(self):
        if not self._ok():
            return
        p = os.path.join(Dav.root, self.path.strip("/"))
        if not os.path.isdir(p):
            self.send_response(404)
            self.end_headers()
            return
        rows = [(self.path, True, 0)]
        for n in sorted(os.listdir(p)):
            f = os.path.join(p, n)
            rows.append((self.path.rstrip("/") + "/" + n + ("/" if os.path.isdir(f) else ""), os.path.isdir(f), os.path.getsize(f)))
        body = '<?xml version="1.0"?><multistatus xmlns="DAV:">' + "".join(
            f"<response><href>{escape(h)}</href><propstat><prop><getcontentlength>{sz}</getcontentlength>"
            f"<getlastmodified>Tue, 01 Jan 2030 00:00:00 GMT</getlastmodified><resourcetype>{'<collection/>' if d else ''}</resourcetype></prop></propstat></response>"
            for h, d, sz in rows) + "</multistatus>"
        self.send_response(207)
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())

    def do_DELETE(self):
        if not self._ok():
            return
        f = os.path.join(Dav.root, self.path.strip("/").replace("%20", " "))
        Dav.deleted.append(self.path)
        try:
            os.remove(f)
            self.send_response(204)
        except OSError:
            self.send_response(404)
        self.end_headers()

    def do_PUT(self):
        if not self._ok():
            return
        data = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        open(os.path.join(Dav.root, self.path.strip("/")), "wb").write(data)
        self.send_response(201)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._ok():
            return
        f = os.path.join(Dav.root, self.path.strip("/"))
        if not os.path.isfile(f):
            self.send_response(404)
            self.end_headers()
            return
        Dav.gets.append(self.path)
        data = open(f, "rb").read()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Ota(TG.Base):
    def setUp(self):
        super().setUp()
        t = self.t.name
        self.remote = os.path.join(t, "remote")
        os.makedirs(os.path.join(self.remote, "demo"))
        Dav.root, Dav.seen = self.remote, []
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Dav)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/"
        self.saved_state = C.STATE_DIR
        C.STATE_DIR = os.path.join(t, "state")

    def tearDown(self):
        self.srv.shutdown()
        C.STATE_DIR = self.saved_state
        super().tearDown()

    def put_bundle(self, name="demo-1.0-linux-all.tar.xz", **kw):
        path = os.path.join(self.remote, "demo", name)
        TG.make_bundle(path, **kw)
        with open(path + ".sha256", "w") as f:
            f.write(hashlib.sha256(open(path, "rb").read()).hexdigest() + "  " + name + "\n")
        return path

    def test_web_packages_are_not_listed_as_games(self):
        self.put_bundle()
        os.makedirs(os.path.join(self.remote, "web"))
        open(os.path.join(self.remote, "web", "mpf-web-x-1.tar.xz"), "wb").write(b"x")
        O.save(self.url, "claude", "secret", "")
        self.assertEqual([i["name"] for i in O.list_remote()], ["demo-1.0-linux-all.tar.xz"])

    def publish_delta(self, version, branch, files):
        """What build_game_package.py --publish writes for one build: files.json, the objects, and the manifest entry."""
        import tarfile
        import mpf_delta as D
        t = self.t.name
        arc = os.path.join(t, f"b-{version}-{branch}.tar.xz")
        TG.make_bundle(arc, version=version, files=files)
        x = os.path.join(t, f"x-{version}-{branch}")
        with tarfile.open(arc) as tf:
            tf.extractall(x)
        top = os.path.join(x, "demo")
        rels = sorted(os.path.relpath(os.path.join(dp, n), top) for dp, _, fn in os.walk(top) for n in fn)
        sums = "".join(f"{D.sha_file(os.path.join(top, n))}  {n}\n" for n in rels)
        open(os.path.join(top, "SHA256SUMS"), "w").write(sums)
        out = os.path.join(t, f"out-{version}-{branch}")
        os.makedirs(out)
        fj, _ = D.export(top, out, branch)
        g = os.path.join(self.remote, "demo")
        d = os.path.join(g, branch, version)
        os.makedirs(d, exist_ok=True)
        os.replace(fj, os.path.join(d, "files.json"))
        for dp, _, fn in os.walk(os.path.join(out, "objects")):
            for n in fn:
                dst = os.path.join(g, "objects", n[:2])
                os.makedirs(dst, exist_ok=True)
                os.replace(os.path.join(dp, n), os.path.join(dst, n))
        mf = os.path.join(self.remote, "mpf-games.json")
        items = json.load(open(mf))["items"] if os.path.exists(mf) else []
        items.append({"id": "demo", "name": "Demo", "version": version, "arch": "all", "branch": branch, "file": f"demo/{branch}/b-{version}.tar.xz",
                      "size": 1, "sha256": "", "delta": f"demo/{branch}/{version}/files.json", "objects": "demo/objects/"})
        json.dump({"format": 1, "items": items}, open(mf, "w"))

    def test_delta_install_downloads_only_what_changed_and_keeps_branches_apart(self):
        big = {"media/a.bin": b"A" * 5000, "media/b.bin": b"B" * 5000, "code.py": b"v1"}
        self.publish_delta("1.0", "main", big)
        self.publish_delta("1.1", "dev", dict(big, **{"code.py": b"v2 changed"}))
        O.save(self.url, "claude", "secret", "")
        items = {(i["version"], i["branch"]): i for i in O.list_remote()}
        self.assertTrue(items[("1.0", "main")]["delta"] and items[("1.1", "dev")]["objects"].endswith("/demo/objects/"))
        G.JOB_LOCK.acquire()
        G.run_job(O.install_item, items[("1.0", "main")], "delta")
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"] + G.JOB["log"])
        self.assertEqual([g["folder"] for g in G.installed_games()], ["demo@1.0"])
        # a file the game rewrote since its install (Godot caches): the stale SHA256SUMS must not make the delta reuse it
        inst = G.installed_games()[0]["path"]
        open(os.path.join(inst, "media", "a.bin"), "wb").write(b"rewritten at run time")
        Dav.gets.clear()
        G.JOB_LOCK.acquire()
        G.run_job(O.install_item, items[("1.1", "dev")], "delta")
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"] + G.JOB["log"])
        self.assertEqual(sorted(g["folder"] for g in G.installed_games()), ["demo@1.0", "demo@1.1+dev"])
        objects = [p for p in Dav.gets if "/objects/" in p]
        self.assertLessEqual(len(objects), 4, objects)          # code.py, SHA256SUMS, bundle.json changed and a.bin was rewritten locally; b.bin came from 1.0
        self.assertTrue(any(hashlib.sha256(b"A" * 5000).hexdigest() in p for p in objects))     # a.bin was changed locally: fetched again
        self.assertFalse(any(hashlib.sha256(b"B" * 5000).hexdigest() in p for p in objects))
        game = [g for g in G.installed_games() if g["folder"] == "demo@1.1+dev"][0]
        self.assertEqual(open(os.path.join(game["path"], "media", "a.bin"), "rb").read(), b"A" * 5000)
        self.assertEqual(open(os.path.join(game["path"], "code.py"), "rb").read(), b"v2 changed")
        self.assertEqual(game["bundle"]["branch"], "dev")
        self.assertEqual({(i["version"], i["branch"]): i["installed"] for i in O.list_remote()}, {("1.0", "main"): True, ("1.1", "dev"): True})

    def test_config_never_exposes_the_password_and_keeps_it(self):
        O.save(self.url, "claude", "secret")
        self.assertEqual(O.public(), {"url": self.url, "folder": "MPF Games", "user": "claude", "has_password": True})
        O.save(self.url, "claude", "", "")                       # an empty field keeps the saved password
        self.assertEqual(O.load()["password"], "secret")
        self.assertEqual(os.stat(O.conf_path()).st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            O.save("ftp://x", "u", "p")

    def test_list_and_install_a_bundle_then_changed(self):
        self.put_bundle()
        O.save(self.url, "claude", "secret", "")
        items = O.list_remote()
        self.assertEqual([(i["group"], i["name"], i["kind"], i["installed"]) for i in items], [("demo", "demo-1.0-linux-all.tar.xz", "game", False)])
        self.assertTrue(items[0]["sha_url"])
        G.JOB_LOCK.acquire()
        G.run_job(O.install_item, items[0])
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"] + G.JOB["log"])
        self.assertEqual([g["folder"] for g in G.installed_games()], ["demo@1.0"])
        self.assertTrue(O.list_remote()[0]["installed"])
        self.assertFalse(O.list_remote()[0]["changed"])
        G.delete_game("demo@1.0")                                                  # removed on the machine: offered again, not "done"
        self.assertFalse(O.list_remote()[0]["installed"])
        G.JOB_LOCK.acquire()
        G.run_job(O.install_item, O.list_remote()[0])
        self.assertTrue(O.list_remote()[0]["installed"])
        self.put_bundle(extra={"description": "now bigger"}, files={"x": b"1" * 100})              # replaced on the server
        self.assertTrue(O.list_remote()[0]["changed"])

    def test_bad_sha_and_wrong_password(self):
        path = self.put_bundle()
        open(path + ".sha256", "w").write("0" * 64 + "\n")
        O.save(self.url, "claude", "secret", "")
        G.JOB_LOCK.acquire()
        G.run_job(O.install_item, O.list_remote()[0])
        self.assertEqual(G.JOB["state"], "error")
        self.assertEqual(G.installed_games(), [])
        O.save(self.url, "claude", "wrong", "")
        with self.assertRaises(ValueError):
            O.list_remote()

    def test_pack_goes_to_the_library(self):
        self.put_bundle(extra={"pup": {"pack_dir": "pup_pack/p", "install": "true"}})
        import io
        import zipfile
        buf = io.BytesIO()
        zipfile.ZipFile(buf, "w").writestr("a.txt", "x")
        open(os.path.join(self.remote, "demo", "demo.pup.zip"), "wb").write(buf.getvalue())
        O.save(self.url, "claude", "secret", "")
        by = {i["name"]: i for i in O.list_remote()}
        self.assertEqual(by["demo-1.0-linux-all.tar.xz"]["for"], "")              # nothing installed yet: a new game
        G.JOB_LOCK.acquire()
        G.run_job(O.install_item, by["demo-1.0-linux-all.tar.xz"])
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"])
        self.assertTrue(O.list_remote()[0]["for"].startswith("Demo"))             # now it names the game it updates
        G.JOB_LOCK.acquire()
        G.run_job(O.install_item, by["demo.pup.zip"])
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"] + G.JOB["log"])
        self.assertEqual([p["name"] for p in G.pup_library()], ["demo.pup.zip"])

    def test_manifest_offers_only_what_fits(self):
        path = self.put_bundle()                                                    # demo 1.0 under demo/
        import hashlib
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        O.save(self.url, "claude", "secret", "")
        file = "demo/" + os.path.basename(path)
        doc = {"format": 1, "items": [
            {"id": "demo", "name": "Demo", "version": "1.0", "arch": "all", "file": file, "size": os.path.getsize(path), "sha256": digest},
            {"id": "demo", "name": "Demo", "version": "9.9", "arch": "other-arch", "file": file, "size": 1, "sha256": "0" * 64}]}
        json.dump(doc, open(os.path.join(self.remote, "mpf-games.json"), "w"))
        items = O.list_remote()
        self.assertEqual([(i["version"], i["for"], i["update"]) for i in items if i["kind"] == "game"], [("1.0", "", False)])   # wrong arch dropped; nothing installed: new game
        G.JOB_LOCK.acquire()
        G.run_job(O.install_item, items[0])
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"] + G.JOB["log"])          # the manifest's hash was checked on the way
        again = [i for i in O.list_remote() if i["kind"] == "game"][0]
        self.assertTrue(again["installed"] and not again["update"] and again["for"].startswith("Demo"))
        doc["items"][0]["version"] = "1.1"
        json.dump(doc, open(os.path.join(self.remote, "mpf-games.json"), "w"))
        newer = [i for i in O.list_remote() if i["kind"] == "game"][0]
        self.assertTrue(newer["update"] and not newer["installed"])
        doc["items"][0]["sha256"] = "0" * 64
        json.dump(doc, open(os.path.join(self.remote, "mpf-games.json"), "w"))
        G.JOB_LOCK.acquire()
        G.run_job(O.install_item, [i for i in O.list_remote() if i["kind"] == "game"][0])
        self.assertEqual(G.JOB["state"], "error")                                      # a wrong hash in the manifest is refused

    def test_a_bundle_is_removed_from_the_server_with_its_hash_and_manifest_entry(self):
        path = self.put_bundle()
        O.save(self.url, "claude", "secret", "")
        file = "demo/" + os.path.basename(path)
        json.dump({"format": 1, "items": [{"id": "demo", "name": "Demo", "version": "1.0", "arch": "all", "file": file, "size": 1, "sha256": "0" * 64},
                                          {"id": "demo", "name": "Demo", "version": "2.0", "arch": "all", "file": "demo/other.tar.xz", "size": 1, "sha256": "0" * 64}]},
                  open(os.path.join(self.remote, "mpf-games.json"), "w"))
        item = [i for i in O.list_remote() if i["key"] == file][0]
        O.delete_remote(item)
        self.assertFalse(os.path.exists(path))
        self.assertFalse(os.path.exists(path + ".sha256"))
        kept = json.load(open(os.path.join(self.remote, "mpf-games.json")))["items"]
        self.assertEqual([i["version"] for i in kept], ["2.0"])
        O.delete_remote(item)                                       # already gone: not an error
        O.save(self.url, "", "", "")
        with self.assertRaises(ValueError):
            O.delete_remote(item)                                   # no credentials, no deletion

    def test_manifest_with_combined_arch_and_games_it_does_not_list(self):
        """The server's manifest names one game with arch "arm64+x86_64"; the other games are only archives in their folders.
        With nothing installed every one of them must be offered."""
        path = self.put_bundle()
        me = O.C.ARCH.get(O.platform.machine(), O.platform.machine())
        other = os.path.join(self.remote, "other")
        os.makedirs(other)
        import shutil
        shutil.copy(path, os.path.join(other, "other-2.0-linux-all.tar.xz"))
        O.save(self.url, "claude", "secret", "")
        doc = {"format": 1, "items": [{"id": "demo", "name": "Demo", "version": "1.0", "arch": "arm64+x86_64",
                                       "file": "demo/" + os.path.basename(path), "size": 1, "sha256": "0" * 64}]}
        json.dump(doc, open(os.path.join(self.remote, "mpf-games.json"), "w"))
        if me in ("arm64", "x86_64"):
            games = [i for i in O.list_remote() if i["kind"] == "game"]
            self.assertEqual(sorted(i["key"] for i in games), ["demo/" + os.path.basename(path), "other/other-2.0-linux-all.tar.xz"])
            self.assertTrue(all(i["compatible"] and not i["installed"] for i in games))

    def test_folder_field(self):
        O.save(self.url, "claude", "secret")                                     # default folder
        self.assertEqual(O.base(O.load()), self.url + "MPF%20Games/")
        O.save(self.url, "claude", "", "A/b c/")
        self.assertEqual(O.base(O.load()), self.url + "A/b%20c/")
        with self.assertRaises(ValueError):
            O.save(self.url, "claude", "", "../x")

    def test_redirect_is_refused(self):
        class Redir(http.server.BaseHTTPRequestHandler):
            def do_PROPFIND(self):
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:1/")
                self.end_headers()

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redir)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            O.save(f"http://127.0.0.1:{srv.server_address[1]}/", "u", "p", "")
            with self.assertRaises(ValueError):
                O.list_remote()
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
