"""common/games/build_game_package.py: build from a game folder, check the archive, publish to WebDAV."""
import contextlib
import http.server
import io
import json
import os
import subprocess
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

    def do_GET(self):
        path = os.path.join(Put.root, self.path.strip("/").replace("%20", " "))
        if not os.path.isfile(path):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            return self.end_headers()
        data = open(path, "rb").read()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
        with mock.patch.dict(os.environ, {"WEBDAV_USER": "u", "WEBDAV_PASS": "p"}):      # a second version: the manifest keeps both
            self.run_tool(self.recipe(), "--repo", self.repo, "--version", "2.1", "--out", self.out, "--publish", f"http://127.0.0.1:{srv.server_address[1]}/games")
            self.run_tool(self.recipe(), "--repo", self.repo, "--version", "2.1", "--out", self.out, "--publish", f"http://127.0.0.1:{srv.server_address[1]}/games")
        doc = json.load(open(os.path.join(Put.root, "games", "mpf-games.json")))
        self.assertEqual(doc["format"], 1)
        self.assertEqual(sorted(i["version"] for i in doc["items"]), ["2.0", "2.1"])         # 2.1 published twice: one entry
        first = doc["items"][0]
        self.assertTrue(first["file"].startswith("fake/") and first["file"].endswith(".tar.xz"))
        self.assertEqual(len(first["sha256"]), 64)
        got = sorted(os.listdir(os.path.join(Put.root, "games", "fake")))
        self.assertEqual(len(got), 4)
        self.assertTrue(got[1].endswith(".tar.xz.sha256") or got[0].endswith(".tar.xz.sha256"))

    def test_dry_run_changes_nothing(self):
        text = self.run_tool(self.recipe(), "--repo", self.repo, "--version", "1.2", "--out", self.out, "--dry-run")
        self.assertIn("dry run", text)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "ready")))

    def test_game_named_by_url_or_clone(self):
        r, repo = B.load_recipe("https://example.com/Some-Game.git", None)
        self.assertEqual((r["id"], repo, r.get("generic")), ("some-game", "https://example.com/Some-Game.git", True))
        r, _ = B.load_recipe(self.repo, None)
        self.assertTrue(r.get("generic"))                                      # nothing declared: the convention or bundle_spec.json
        with open(os.path.join(self.repo, "mpf-package.json"), "w") as f:
            json.dump({"id": "mine", "setup": [], "build": ["true"]}, f)
        self.assertEqual(B.load_recipe(self.repo, None)[0]["id"], "mine")      # the game's own recipe

    def test_preflight_reports_every_missing_thing_at_once(self):
        with mock.patch.object(B.shutil, "which", return_value=None):
            problems = B.preflight({"tools": ["git", "ffmpeg"], "min_python": "99.0", "disk_gb": 10 ** 9}, True, self.tmp, self.out)
        text = "\n".join(problems)
        self.assertIn("git is not installed", text)
        self.assertIn("ffmpeg is not installed", text)
        self.assertIn("Python 99.0", text)
        self.assertIn("GB needed", text)
        self.assertEqual(B.preflight({"tools": [], "disk_gb": 0}, False, self.tmp, self.out), [])

    def git(self, *args, cwd=None):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", *args], cwd=cwd or self.repo, check=True, capture_output=True, env=env)

    def test_refuses_a_branch_that_is_not_merged(self):
        origin = os.path.join(self.tmp, "origin.git")
        self.git("init", "-q", "--bare", "-b", "main", origin, cwd=self.tmp)
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "one")
        self.git("remote", "add", "origin", origin)
        self.git("push", "-q", "origin", "main")
        self.git("checkout", "-q", "-b", "work")
        with open(os.path.join(self.repo, "machine", "new.txt"), "w") as f:
            f.write("x")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "two, not merged")
        with self.assertRaises(SystemExit) as e:
            B.check_source(self.repo, False)
        self.assertIn("not the merged main", str(e.exception))
        with contextlib.redirect_stdout(io.StringIO()):
            B.check_source(self.repo, True)                  # --allow-branch: a test package on purpose
            self.git("checkout", "-q", "main")
            B.check_source(self.repo, False)                 # main is fine

    def archive(self, meta, files):
        top = os.path.join(self.tmp, "pack", "fake@1")
        import shutil
        shutil.rmtree(os.path.join(self.tmp, "pack"), ignore_errors=True)
        os.makedirs(top)
        files = dict(files, **{"bundle.json": json.dumps(dict({"format": 1, "id": "fake", "version": "1", "target": {"arch": "all"}}, **meta))})
        for name, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(top, name)), exist_ok=True)
            with open(os.path.join(top, name), "w") as f:
                f.write(text)
        path = os.path.join(self.tmp, "fake@1.tar.xz")
        subprocess.run(["tar", "-cJf", path, "-C", os.path.join(self.tmp, "pack"), "fake@1"], check=True)
        if os.path.exists(path + ".sha256"):
            os.remove(path + ".sha256")
        return path

    def check(self, meta, files):
        with contextlib.redirect_stdout(io.StringIO()):
            return B.verify(self.archive(meta, files), {"id": "fake"}, "all")

    def test_contract_checks(self):
        run = {"run": {"start": "python3 scripts/run.py", "cwd": "."}}
        with self.assertRaises(SystemExit) as e:
            self.check(run, {"game/project.godot": "x"})
        self.assertIn("not in the archive", str(e.exception))
        self.check(run, {"scripts/run.py": "x", "game/project.godot": "x"})                       # fine
        gmc = {"scripts/run.py": "x", "game/project.godot": 'enabled=PackedStringArray("res://addons/mpf-gmc/plugin.cfg")'}
        with self.assertRaises(SystemExit) as e:
            self.check(run, gmc)
        self.assertIn("without GMC", str(e.exception))
        self.check(dict(run, platform_addons=["gde_gozen", "mpf-gmc"]), gmc)                      # the platform brings it
        self.check(run, dict(gmc, **{"game/addons/mpf-gmc/plugin.cfg": "x"}))                      # the game ships it

    def test_a_name_is_not_a_game(self):
        with self.assertRaises(SystemExit):                  # the platform keeps no list of games to look a name up in
            self.run_tool("nope-no-such-game")


if __name__ == "__main__":
    unittest.main()
