"""Updates from a WebDAV folder (common/netconfig/mpf_ota.py), against a small local server."""
import hashlib
import http.server
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

    def do_GET(self):
        if not self._ok():
            return
        f = os.path.join(Dav.root, self.path.strip("/"))
        if not os.path.isfile(f):
            self.send_response(404)
            self.end_headers()
            return
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
