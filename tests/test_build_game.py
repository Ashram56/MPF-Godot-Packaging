"""common/games/build_game_package.py: build from a game folder, check the archive, publish to WebDAV."""
import contextlib
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "common", "games"))
import build_game_package as B  # noqa: E402

MAKE = os.path.join(os.path.dirname(HERE), "common", "games", "make_bundle.py")


class Put(http.server.BaseHTTPRequestHandler):
    root = ""

    def log_message(self, *a):
        pass

    def do_MKCOL(self):
        os.makedirs(os.path.join(Put.root, self.path.strip("/")), exist_ok=True)
        self.send_response(201)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PUT(self):
        data = self.rfile.read(int(self.headers["Content-Length"]))
        with open(os.path.join(Put.root, self.path.strip("/")), "wb") as f:
            f.write(data)
        self.send_response(201)
        self.send_header("Content-Length", "0")
        self.end_headers()


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "machine", "config"))
        with open(os.path.join(self.repo, "machine", "config", "config.yaml"), "w") as f:
            f.write("#config_version=6\n")
        self.out = os.path.join(self.tmp, "dist")

    def recipe(self, extra_args=(), setup=True):
        r = {"id": "fake", "target": "all",
             "setup": [["{python}", "-c", "open('ready', 'w').write('x')"]] if setup else [],
             "build": ["{python}", MAKE, "machine", "--id", "fake", "--version", "{version}", "--start", "mpf both", "-o", "{out}", *extra_args]}
        path = os.path.join(self.tmp, "fake.json")
        with open(path, "w") as f:
            json.dump(r, f)
        return path

    def run_tool(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            with mock.patch.object(sys, "argv", ["build_game_package.py", *args]):
                B.main()
        return out.getvalue()

    def test_build_and_check(self):
        text = self.run_tool(self.recipe(), "--repo", self.repo, "--version", "1.2", "--out", self.out)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "ready")))     # the setup ran in the repository
        self.assertIn("checked: fake 1.2", text)
        self.assertTrue(any(n.endswith(".tar.xz") for n in os.listdir(self.out)))

    def test_skip_setup(self):
        self.run_tool(self.recipe(), "--repo", self.repo, "--version", "1.2", "--out", self.out, "--skip-setup")
        self.assertFalse(os.path.exists(os.path.join(self.repo, "ready")))

    def test_refuses_cabinet_data_and_missing_addon(self):
        os.makedirs(os.path.join(self.repo, "machine", "data"))
        with open(os.path.join(self.repo, "machine", "data", "audits.yaml"), "w") as f:
            f.write("x: 1\n")
        with self.assertRaises(SystemExit) as e:
            self.run_tool(self.recipe(), "--repo", self.repo, "--version", "1.2", "--out", self.out)
        self.assertIn("cabinet data", str(e.exception))
        os.remove(os.path.join(self.repo, "machine", "data", "audits.yaml"))
        os.rmdir(os.path.join(self.repo, "machine", "data"))
        with self.assertRaises(SystemExit) as e:
            self.run_tool(self.recipe(["--platform-addon", "no_such_addon"]), "--repo", self.repo, "--version", "1.3", "--out", self.out)
        self.assertIn("no_such_addon", str(e.exception))

    def test_publish(self):
        Put.root = os.path.join(self.tmp, "dav")
        os.makedirs(Put.root)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Put)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with mock.patch.dict(os.environ, {"WEBDAV_USER": "u", "WEBDAV_PASS": "p"}):
            self.run_tool(self.recipe(), "--repo", self.repo, "--version", "2.0", "--out", self.out, "--publish", f"http://127.0.0.1:{srv.server_address[1]}/games")
        got = sorted(os.listdir(os.path.join(Put.root, "games", "fake")))
        self.assertEqual(len(got), 2)
        self.assertTrue(got[1].endswith(".tar.xz.sha256") or got[0].endswith(".tar.xz.sha256"))

    def test_dry_run_changes_nothing(self):
        text = self.run_tool(self.recipe(), "--repo", self.repo, "--version", "1.2", "--out", self.out, "--dry-run")
        self.assertIn("dry run", text)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "ready")))

    def test_game_named_by_url_or_clone(self):
        r, repo = B.load_recipe("https://github.com/Ashram56/Tron-Legacy-MPF", None)
        self.assertEqual((r["id"], repo), ("tron-legacy-mpf", "https://github.com/Ashram56/Tron-Legacy-MPF"))
        os.system(f"git -C {self.repo} init -q && git -C {self.repo} remote add origin git@x:y 2>/dev/null; git -C {self.repo} remote set-url origin https://github.com/ashram56/tron-legacy-mpf.git")
        self.assertEqual(B.load_recipe(self.repo, None)[0]["id"], "tron-legacy-mpf")
        with open(os.path.join(self.repo, "mpf-package.json"), "w") as f:
            json.dump({"id": "mine", "setup": [], "build": ["true"]}, f)
        os.system(f"git -C {self.repo} remote set-url origin https://example.com/other.git")
        self.assertEqual(B.load_recipe(self.repo, None)[0]["id"], "mine")      # the game's own recipe
        os.remove(os.path.join(self.repo, "mpf-package.json"))
        r, _ = B.load_recipe(self.repo, None)
        self.assertTrue(r.get("generic"))                                      # nothing known: bundle_spec.json is tried

    def test_preflight_reports_every_missing_thing_at_once(self):
        with mock.patch.object(B.shutil, "which", return_value=None):
            problems = B.preflight({"tools": ["git", "ffmpeg"], "min_python": "99.0", "disk_gb": 10 ** 9}, True, self.tmp, self.out)
        text = "\n".join(problems)
        self.assertIn("git is not installed", text)
        self.assertIn("ffmpeg is not installed", text)
        self.assertIn("Python 99.0", text)
        self.assertIn("GB needed", text)
        self.assertEqual(B.preflight({"tools": [], "disk_gb": 0}, False, self.tmp, self.out), [])

    def test_unknown_recipe(self):
        with self.assertRaises(SystemExit):
            self.run_tool("nope-no-such-recipe")


if __name__ == "__main__":
    unittest.main()
