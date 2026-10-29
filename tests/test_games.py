"""Several games on one image: install, versions, the active game, the inbox, how a bundle is started (common/netconfig/mpf_games.py)."""
import io
import json
import os
import pwd
import sys
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common", "netconfig"))
import mpf_common as C  # noqa: E402
import mpf_games as G  # noqa: E402


def make_bundle(path, gid="demo", version="1.0", name="Demo", extra=None, files=None, arch="all"):
    """A tar.xz in the bundle layout: one folder with bundle.json."""
    b = {"format": 1, "id": gid, "name": name, "version": version, "target": {"os": "linux", "arch": arch},
         "run": {"start": "echo hi"}, "keep_on_update": ["game/data", "pup_pack"], "pup": {"pack_dir": "pup_pack/p", "media_dir": "pup_media/p"}}
    b.update(extra or {})
    with tarfile.open(path, "w:xz") as tf:
        def add(rel, data):
            ti = tarfile.TarInfo(f"{gid}/{rel}")
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
        add("bundle.json", json.dumps(b).encode())
        for rel, data in (files or {}).items():
            add(rel, data)


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        t = self.t.name
        self.saved = {k: getattr(C, k) for k in ("GAMES", "STATE_DIR", "UPLOADS", "INBOX", "PUPS", "USER", "JOB_FILE", "GAME_ENV", "READONLY")}
        C.GAMES, C.STATE_DIR, C.UPLOADS, C.INBOX = (os.path.join(t, n) for n in ("games", "state", "up", "inbox"))
        C.PUPS = os.path.join(t, "pups")
        C.JOB_FILE = os.path.join(t, "job.json")
        C.GAME_ENV = os.path.join(t, "mpf-game")
        C.USER, C.READONLY = pwd.getpwuid(os.getuid()).pw_name, False
        for d in (C.GAMES, C.INBOX, C.UPLOADS):
            os.makedirs(d)
        self.saved_fn = {k: getattr(G, k) for k in ("set_autostart", "board_profile", "game_running", "game_restart")}
        G.set_autostart = lambda on: None
        G.board_profile = lambda game, b: None
        G.game_running = lambda: False
        G.JOB.update(state="idle", msg="", log="")

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(C, k, v)
        for k, v in self.saved_fn.items():
            setattr(G, k, v)
        self.t.cleanup()

    def install(self, **kw):
        arc = os.path.join(self.t.name, "b.tar.xz")
        make_bundle(arc, **kw)
        G.JOB_LOCK.acquire()
        G.run_job(G.install_game, arc, "")
        return G.JOB["state"], G.JOB["msg"]


class Install(Base):
    def test_first_game_is_active_and_lives_in_id_at_version(self):
        self.assertEqual(self.install()[0], "done")
        games = G.installed_games()
        self.assertEqual([g["folder"] for g in games], ["demo@1.0"])
        self.assertTrue(games[0]["active"])

    def test_board_override_is_copied_at_every_install(self):
        ov = os.path.join(self.t.name, "override.cfg")
        open(ov, "w").write("[audio]\n")
        C.GAME_OVERRIDE = ov
        try:
            self.assertEqual(self.install()[0], "done")
        finally:
            C.GAME_OVERRIDE = ""
        self.assertEqual(open(os.path.join(C.GAMES, "demo@1.0", "game", "override.cfg")).read(), "[audio]\n")

    def test_update_of_the_running_active_game_restarts_it(self):
        self.install()
        calls = []
        G.game_running = lambda: True
        G.game_restart = lambda: calls.append("restart")
        try:
            self.assertEqual(self.install(version="1.1")[0], "done")
            self.assertEqual(calls, ["restart"])
            calls.clear()
            self.install(gid="other", name="Other", version="3")     # a different game waits: no restart
            self.assertEqual(calls, [])
        finally:
            G.game_running = lambda: False
    def test_board_arguments_and_venv_names(self):
        env = {"MPF_GAME_ARGS": "-- --rendering-driver opengl3", "MPF_GAME_VENV": "/v", "TF_VENV": "/v2", "GODOT": "/g"}
        own = {"run": {"start": "python3 run.py"}}
        self.assertEqual(G.game_command("/x", own, env)[0][1:], ["run.py"])                          # a game with its own start: no board arguments
        packaged = {"run": {"start": "python3 scripts/package/start.py"}}
        self.assertEqual(G.game_command("/x", packaged, env)[0][-3:], ["--", "--rendering-driver", "opengl3"])
        self.assertEqual(G.game_command("/x", {}, env)[0][-1], "opengl3")                           # default start: the packaged launcher
        opted = {"run": {"start": "python3 run.py", "game_args": True}}
        self.assertEqual(G.game_command("/x", opted, env)[0][-1], "opengl3")
        refused = {"run": {"start": "python3 scripts/package/start.py", "game_args": False}}
        self.assertEqual(G.game_command("/x", refused, env)[0][1:], ["scripts/package/start.py"])
        child = G.game_environment({"requires": {"env": {"OTHER_VENV": ""}}}, env)
        self.assertEqual((child["MPF_GAME_VENV"], child["OTHER_VENV"], child["TF_VENV"], child["GODOT"]), ("/v", "/v", "/v2", "/g"))

    def test_platform_gmc_replaces_the_bundles_own(self):
        plat = os.path.join(self.t.name, "plat")
        gmc = os.path.join(plat, "toolchain", "addons", "mpf-gmc")
        os.makedirs(os.path.join(gmc, "scripts"))
        open(os.path.join(gmc, "plugin.cfg"), "w").write("[plugin]\n")
        open(os.path.join(gmc, "scripts", "bcp_server.gd"), "w").write("# mpf-godot fix bcp-partial-lines\n")
        fake = os.path.join(self.t.name, "godot")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\necho \"$@\" > %s/godot.called\n" % self.t.name)
        os.chmod(fake, 0o755)
        open(C.GAME_ENV, "w").write(f"GODOT={fake}\n")
        saved = C.PLATFORM_DIR
        C.PLATFORM_DIR = plat
        try:
            state, msg = self.install(extra={"platform_addons": ["mpf-gmc"]},
                                      files={"game/project.godot": b"", "game/addons/mpf-gmc/scripts/bcp_server.gd": b"# the bundle's own, unpatched\n"})
        finally:
            C.PLATFORM_DIR = saved
        self.assertEqual(state, "done", msg)
        p = os.path.join(C.GAMES, "demo@1.0", "game", "addons", "mpf-gmc", "scripts", "bcp_server.gd")
        self.assertIn("mpf-godot fix", open(p).read())
        self.assertTrue(os.path.isfile(os.path.join(self.t.name, "godot.called")))      # the project was re-imported once
        state, msg = self.install(version="2", extra={"platform_addons": ["mpf-gmc"]})       # no platform GMC: refused, not silently skipped
        self.assertEqual(state, "error")

    def test_a_second_game_waits_to_be_chosen(self):
        self.install()
        state, msg = self.install(gid="other", name="Other", version="3")
        self.assertEqual(state, "done")
        self.assertIn("choose it", msg)
        self.assertEqual(G.active_folder(), "demo@1.0")
        G.set_active("other@3")
        self.assertEqual(G.active_folder(), "other@3")
        self.assertEqual(G.installed_game(), os.path.join(C.GAMES, "other@3"))

    def test_new_version_inherits_settings_scores_and_pack_and_old_stays(self):
        self.install(files={"game/data/scores.json": b"123", "pup_pack/p/a.mp4": b"video"})
        old = os.path.join(C.GAMES, "demo@1.0")
        # the old version played on: its scores changed
        open(os.path.join(old, "game/data/scores.json"), "wb").write(b"456")
        self.assertEqual(self.install(version="1.1", files={"game/data/scores.json": b"0"})[0], "done")
        new = os.path.join(C.GAMES, "demo@1.1")
        self.assertEqual(open(os.path.join(new, "game/data/scores.json")).read(), "456")      # carried over (a copy)
        open(os.path.join(new, "game/data/scores.json"), "w").write("789")
        self.assertEqual(open(os.path.join(old, "game/data/scores.json")).read(), "456")      # the old one is untouched
        a, b = os.stat(os.path.join(old, "pup_pack/p/a.mp4")), os.stat(os.path.join(new, "pup_pack/p/a.mp4"))
        self.assertEqual(a.st_ino, b.st_ino)                                                  # the pack is not copied twice
        self.assertEqual(G.active_folder(), "demo@1.1")                                       # an update of the active game takes over
        self.assertEqual(len(G.installed_games()), 2)

    def test_same_version_again_replaces_and_keeps(self):
        self.install(files={"game/data/s": b"1"})
        open(os.path.join(C.GAMES, "demo@1.0", "game/data/s"), "w").write("2")
        self.install(files={"game/data/s": b"0"})
        self.assertEqual(open(os.path.join(C.GAMES, "demo@1.0", "game/data/s")).read(), "2")
        self.assertEqual(len(G.installed_games()), 1)

    def test_refused_bundles(self):
        self.assertIn("this machine", self.install(arch="mips")[1])
        self.assertEqual(G.installed_games(), [])
        self.assertIn("id must be", self.install(gid="Bad Id")[1])
        self.assertEqual(os.listdir(C.GAMES), [])

    def test_delete(self):
        self.install()
        self.install(gid="other", name="Other", version="1")
        G.delete_game("other@1")
        self.assertEqual([g["folder"] for g in G.installed_games()], ["demo@1.0"])
        with self.assertRaises(ValueError):
            G.delete_game("nothing@0")
        G.delete_game("demo@1.0")
        self.assertIsNone(G.active_folder())
        self.assertIsNone(G.installed_game())


class Launch(Base):
    def test_default_and_custom_start(self):
        env = {"MPF_GAME_ARGS": "-- --fullscreen"}
        argv, cwd = G.game_command("/g", {}, env)
        self.assertEqual(argv[1:], ["scripts/package/start.py", "--", "--fullscreen"])
        self.assertEqual(cwd, "/g")
        argv, cwd = G.game_command("/g", {"run": {"start": "mpf both -x", "cwd": "machine"}}, {})
        self.assertEqual(argv[1:], ["both", "-x"])
        self.assertEqual(cwd, "/g/machine")

    def test_programs_come_from_the_venv(self):
        venv = os.path.join(self.t.name, "venv")
        os.makedirs(os.path.join(venv, "bin"))
        for n in ("python", "mpf"):
            open(os.path.join(venv, "bin", n), "w").close()
        open(C.GAME_ENV, "w").write(f"MPF_GAME_VENV={venv}\n")
        self.assertEqual(G.resolve_program("python3"), os.path.join(venv, "bin", "python"))
        self.assertEqual(G.resolve_program("mpf"), os.path.join(venv, "bin", "mpf"))

    def test_bundle_gets_the_variables_it_names(self):
        env = {"GODOT": "/g/godot", "MPF_GAME_VENV": "/v"}
        got = G.game_environment({"requires": {"env": {"GODOT": "x", "SOME_VENV": "y"}}}, env)
        self.assertEqual(got, {"GODOT": "/g/godot", "MPF_GAME_VENV": "/v", "SOME_VENV": "/v"})


class Inbox(Base):
    def test_bundles_then_packs_and_failures_are_set_aside(self):
        make_bundle(os.path.join(C.INBOX, "demo.tar.xz"))
        open(os.path.join(C.INBOX, "bad.tar.xz"), "wb").write(b"not an archive")
        open(os.path.join(C.INBOX, "demo.pup.zip"), "wb").write(b"zip")
        calls = []
        G.install_pup = lambda path, folder=None: (calls.append((os.path.basename(path), folder)), os.remove(path), G.job_set(state="done"))
        try:
            self.assertEqual(G.process_inbox(), 2)
        finally:
            import importlib
            importlib.reload(G)
        self.assertEqual(calls, [("demo.pup.zip", "demo@1.0")])
        self.assertEqual([g["folder"] for g in G.installed_games()], ["demo@1.0"])
        self.assertEqual(sorted(n for n in os.listdir(C.INBOX)), ["failed"])
        self.assertIn("bad.tar.xz.log", os.listdir(os.path.join(C.INBOX, "failed")))

    def test_pack_target_names(self):
        games = [{"folder": "a@1", "id": "a", "active": False, "mtime": 1}, {"folder": "a@2", "id": "a", "active": True, "mtime": 2},
                 {"folder": "b@1", "id": "b", "active": False, "mtime": 3}]
        self.assertEqual(G.inbox_pup_target("a.pup.zip", games), "a@2")        # the active version of that game
        self.assertEqual(G.inbox_pup_target("a@1.pup.zip", games), "a@1")
        self.assertEqual(G.inbox_pup_target("b.pup.zip", games), "b@1")
        self.assertIsNone(G.inbox_pup_target("c.pup.zip", games))


class StartCheck(Base):
    """A bundle that cannot start is refused before it is installed, and the game that was running stays the active one."""
    START = {"run": {"start": "python3 scripts/start.py"}}

    def venv(self):
        d = os.path.join(self.t.name, "venv", "bin")
        os.makedirs(d)
        os.symlink(sys.executable, os.path.join(d, "python"))
        with open(C.GAME_ENV, "w") as f:
            f.write(f"MPF_GAME_VENV={os.path.join(self.t.name, 'venv')}\n")

    def refused(self, **kw):
        arc = os.path.join(self.t.name, "bad.tar.xz")
        make_bundle(arc, **kw)
        G.JOB_LOCK.acquire()
        G.run_job(G.install_game, arc, "")
        return G.JOB["msg"]

    def test_missing_module_is_refused_and_the_old_game_stays(self):
        self.venv()
        self.install(version="1.0", extra=self.START, files={"scripts/start.py": b"import helper\n", "scripts/helper.py": b"X = 1\n"})
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"])
        msg = self.refused(version="2.0", extra=self.START, files={"scripts/start.py": b"import helper\nimport helper_missing_xyz\n", "scripts/helper.py": b""})
        self.assertEqual(G.JOB["state"], "error")
        self.assertIn("helper_missing_xyz", msg)
        self.assertEqual([g["folder"] for g in G.installed_games()], ["demo@1.0"])             # nothing of 2.0 was installed
        self.assertTrue(G.installed_games()[0]["active"])

    def test_optional_imports_and_stdlib_pass(self):
        self.venv()
        src = b"import os, json\ntry:\n    import nothing_here_optional\nexcept ImportError:\n    pass\ndef f():\n    import also_missing\n"
        self.install(extra=self.START, files={"scripts/start.py": src})
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"])

    def test_script_launched_by_the_start_script_is_followed(self):
        self.venv()
        self.refused(extra=self.START, files={"scripts/start.py": b"import subprocess\nsubprocess.run(['python3', 'run.py'])\n",
                                              "scripts/run.py": b"import lost_module_xyz\n"})
        self.assertEqual(G.JOB["state"], "error")
        self.assertIn("lost_module_xyz", G.JOB["msg"])

    def test_run_check_decides(self):
        self.venv()
        ok = {"run": {"start": "echo hi", "check": "python3 scripts/check.py"}}
        self.install(version="1.0", extra=ok, files={"scripts/check.py": b"import sys; sys.exit(0)\n"})
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"])
        msg = self.refused(version="2.0", extra=ok, files={"scripts/check.py": b"import sys; print('no display'); sys.exit(3)\n"})
        self.assertIn("run.check", msg)
        self.assertIn("no display", msg)
        self.assertEqual([g["folder"] for g in G.installed_games()], ["demo@1.0"])


class PupLibrary(Base):
    PACK = {"pup": {"pack_dir": "pup_pack/p", "media_dir": "pup_media/p",
                    "install": "sh -c 'mkdir -p pup_pack/p pup_media/p && echo v > pup_pack/p/a.mp4 && echo m > pup_media/p/a.webm'"}}

    def upload(self, name="pack.zip"):
        import zipfile
        p = os.path.join(C.UPLOADS, "pup.zip")
        zipfile.ZipFile(p, "w").writestr("a.txt", "x")
        return G.pup_store(p, name)

    def test_store_and_refuse_a_non_zip(self):
        self.assertEqual(self.upload("my pack.zip"), "my_pack.zip")
        self.assertEqual([p["name"] for p in G.pup_library()], ["my_pack.zip"])
        bad = os.path.join(C.UPLOADS, "pup.zip")
        open(bad, "wb").write(b"nope")
        with self.assertRaises(G.JobError):
            G.pup_store(bad, "x.zip")

    def test_assign_links_and_is_shared_by_versions(self):
        self.install(extra=self.PACK)
        name = self.upload()
        G.assign_pup("demo@1.0", name)
        game = os.path.join(C.GAMES, "demo@1.0")
        self.assertTrue(os.path.islink(os.path.join(game, "pup_pack/p")))
        self.assertEqual(open(os.path.join(game, "pup_pack/p/a.mp4")).read().strip(), "v")
        self.assertEqual(G.pup_assigned(game), name)
        self.assertTrue(G.pup_installed(game))
        self.install(version="2.0", extra=self.PACK)                          # a new version inherits the link
        self.assertEqual(G.pup_assigned(os.path.join(C.GAMES, "demo@2.0")), name)
        with self.assertRaises(G.JobError):                                   # in use: cannot be deleted
            G.delete_pup(name)
        G.unassign_pup("demo@1.0")
        G.unassign_pup("demo@2.0")
        self.assertIsNone(G.pup_assigned(game))
        self.assertFalse(G.pup_installed(game))
        G.assign_pup("demo@1.0", name)                                        # again: no second install (the installer would add a marker)
        G.unassign_pup("demo@1.0")
        G.delete_pup(name)
        self.assertEqual(G.pup_library(), [])

    def test_extract_only_unpacks_the_authors_zip_and_runs_nothing(self):
        """pup.extract_only: the zip's pack folder (the one holding triggers.pup, at any depth) is only unpacked; the game's install command
        (which would write a marker) never runs, and the media folder of the bundle is left alone."""
        import zipfile
        pup = {"pack_dir": "pup_pack/p", "extract_only": True, "install": "sh -c 'touch RAN'"}
        self.install(extra={"pup": pup}, files={"pup_media/p/m.json": b"{}"})
        p = os.path.join(C.UPLOADS, "pup.zip")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("PUPVideos/p/triggers.pup", "t")
            z.writestr("PUPVideos/p/Sub/a.mp4", "video")
            z.writestr("PUPVideos/other/x.txt", "no")
            z.writestr("PUPVideos/p/../evil.txt", "no")
        name = G.pup_store(p, "author.zip")
        G.assign_pup("demo@1.0", name)
        game = os.path.join(C.GAMES, "demo@1.0")
        self.assertEqual(open(os.path.join(game, "pup_pack/p/Sub/a.mp4")).read(), "video")
        self.assertFalse(os.path.exists(os.path.join(game, "pup_pack/p/x.txt")))
        self.assertFalse(os.path.exists(os.path.join(game, "RAN")))
        self.assertTrue(os.path.exists(os.path.join(game, "pup_media/p/m.json")))
        self.assertTrue(G.pup_installed(game))

    def test_assign_needs_a_pack_and_pack_support(self):
        self.install(extra=self.PACK)
        with self.assertRaises(G.JobError):
            G.assign_pup("demo@1.0", "missing.zip")
        self.install(gid="plain", extra={"pup": None})
        with self.assertRaises(G.JobError):
            G.assign_pup("plain@1.0", self.upload())


if __name__ == "__main__":
    unittest.main()
