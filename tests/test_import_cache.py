"""mpf_godot/import_cache.py against a fake WebDAV server (PUT, GET, MKCOL) on localhost."""
import http.server
import os
import tempfile
import threading
import unittest

from mpf_godot import import_cache as ic

IMPORT = ('[remap]\nimporter="texture"\nuid="uid://abc"\n'
          'dest_files=["res://.godot/imported/a.png-{h}.s3tc.ctex", "res://.godot/imported/a.png-{h}.md5"]\n'
          '\n[params]\ncompress/mode=2\n')
H = "0123456789abcdef0123456789abcdef"


class Dav(http.server.BaseHTTPRequestHandler):
    store = {}

    def log_message(self, *a):
        pass

    def auth(self):
        return self.headers.get("Authorization", "").startswith("Basic ")

    def reply(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_MKCOL(self):
        self.reply(201 if self.auth() else 401)

    def do_PROPFIND(self):
        names = [k for k in self.store if k.startswith(self.path)]
        if not names:
            return self.reply(404)
        self.reply(207, "".join("<D:href>{}</D:href>".format(k) for k in names).encode())

    def do_PUT(self):
        n = int(self.headers.get("Content-Length", 0))
        self.store[self.path] = self.rfile.read(n)
        self.reply(201)

    def do_GET(self):
        if self.path in self.store:
            self.reply(200, self.store[self.path])
        else:
            self.reply(404)


def write(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode())


class Cache(unittest.TestCase):
    def setUp(self):
        Dav.store = {}
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Dav)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:{}/dav".format(self.srv.server_port)
        os.environ["WEBDAV_PASS"] = "secret"
        self.tmp = tempfile.TemporaryDirectory()
        self.stage = self.tmp.name
        write(os.path.join(self.stage, "game", "project.godot"), "[rendering]\ntextures/vram_compression/import_s3tc_bptc=true\n")
        write(os.path.join(self.stage, "game", "img", "a.png"), b"PNG-A")

    def tearDown(self):
        self.srv.shutdown()
        self.tmp.cleanup()

    def cache(self, **kw):
        return ic.ImportCache(self.url, "4.6.3", "s3tc", os.path.join(self.stage, "game", "project.godot"), **kw)

    def fake_import(self):
        write(os.path.join(self.stage, "game", "img", "a.png.import"), IMPORT.format(h=H))
        write(os.path.join(self.stage, "game", ".godot", "imported", "a.png-%s.s3tc.ctex" % H), b"CTEX")
        write(os.path.join(self.stage, "game", ".godot", "imported", "a.png-%s.md5" % H), b"MD5")

    def test_roundtrip(self):
        c = self.cache()
        self.assertEqual(c.restore(self.stage, "game"), (0, 1))
        self.fake_import()
        self.assertEqual(c.store(self.stage, "game"), 1)
        self.assertEqual(len(Dav.store), 1)
        # a clean machine: no import, same medium
        import shutil
        shutil.rmtree(os.path.join(self.stage, "game", ".godot"))
        os.remove(os.path.join(self.stage, "game", "img", "a.png.import"))
        c2 = self.cache()
        self.assertEqual(c2.restore(self.stage, "game"), (1, 0))
        with open(os.path.join(self.stage, "game", ".godot", "imported", "a.png-%s.s3tc.ctex" % H), "rb") as f:
            self.assertEqual(f.read(), b"CTEX")
        self.assertEqual(c2.store(self.stage, "game"), 0)

    def test_key_changes(self):
        base = self.cache().key(self.stage, "game", "game/img/a.png")
        self.assertNotEqual(base, ic.ImportCache(self.url, "4.7.0", "s3tc", os.path.join(self.stage, "game", "project.godot"))
                            .key(self.stage, "game", "game/img/a.png"))
        self.assertNotEqual(base, ic.ImportCache(self.url, "4.6.3", "both", os.path.join(self.stage, "game", "project.godot"))
                            .key(self.stage, "game", "game/img/a.png"))
        write(os.path.join(self.stage, "game", "img", "a.png"), b"PNG-B")
        self.assertNotEqual(base, self.cache().key(self.stage, "game", "game/img/a.png"))

    def test_key_ignores_godot_rewrites_but_not_params(self):
        write(os.path.join(self.stage, "game", "img", "a.png.import"), IMPORT.format(h=H))
        k = self.cache().key(self.stage, "game", "game/img/a.png")
        write(os.path.join(self.stage, "game", "img", "a.png.import"), IMPORT.format(h=H).replace("uid://abc", "uid://zzz"))
        self.assertEqual(k, self.cache().key(self.stage, "game", "game/img/a.png"))
        write(os.path.join(self.stage, "game", "img", "a.png.import"), IMPORT.format(h=H).replace("mode=2", "mode=0"))
        self.assertNotEqual(k, self.cache().key(self.stage, "game", "game/img/a.png"))

    def test_unreachable_is_not_fatal(self):
        c = ic.ImportCache("http://127.0.0.1:9/dav", "4.6.3", "s3tc", os.path.join(self.stage, "game", "project.godot"))
        c.req = lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
        self.assertEqual(c.restore(self.stage, "game"), (0, 1))
        self.assertFalse(c.ok)

    def test_needs_password(self):
        del os.environ["WEBDAV_PASS"]
        with self.assertRaises(SystemExit):
            self.cache()


if __name__ == "__main__":
    unittest.main()
