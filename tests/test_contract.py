"""Bundle format 2: files and facts only, the platform starts the game (common/netconfig/mpf_contract.py, platforms/game-bundles.md)."""
import json
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_games import Base  # noqa: E402
import mpf_common as C  # noqa: E402
import mpf_contract as K  # noqa: E402
import mpf_dmd as D  # noqa: E402
import mpf_games as G  # noqa: E402

SCHEMA = {"groups": [{"id": "d", "label": "Display"}], "options": [
    {"id": "dmd.mode", "group": "d", "label": "Look", "type": "choice", "choices": ["hd", "classic"], "default": "hd",
     "target": {"godot_arg": "--dmd"}},
    {"id": "pup.music", "group": "d", "label": "Music", "type": "bool", "default": True,
     "target": {"ini": "game/pup.local.cfg", "section": "pup", "key": "music"}},
    {"id": "machine.hw", "group": "d", "label": "Hardware", "type": "choice", "choices": ["virtual", "proc"], "default": "virtual",
     "target": {"hardware": True}}]}

V2 = {"format": 2, "run": None, "game_dir": "game", "keep_on_update": ["game/data"],
      "mpf": {"configs": ["config"], "hardware": {"virtual": ["hw_virtual"], "proc": ["hw_proc"]}},
      "dmd": {"rom": "demo_100"}, "pup": {"rom": "demo_100", "manifest": "pup/manifest.json"},
      "addons": [{"id": "hd_art", "dir": "addons/hd_art", "setting": "dmd.mode", "when": "hd"}],
      "settings": {"schema": "settings.json"},
      "profiles": {"rpi4": {"limits": {"dmd.mode": ["classic"]}, "defaults": {"dmd.mode": "classic"}, "godot_args": ["--max-fps=30"]}},
      "platform_addons": []}
FILES = {"game/project.godot": b"", "game/config/config.yaml": b"", "game/config/hw_virtual.yaml": b"",
         "game/config/hw_proc.yaml": b"", "game/rules/feature.py": b"import json\n", "settings.json": json.dumps(SCHEMA).encode(),
         "pup/manifest.json": b"{}", "addons/hd_art/a.png": b"x"}


class Contract(unittest.TestCase):
    def test_commands_are_refused(self):
        b = dict(V2, run={"start": "python3 start.py"}, options={"tool": "x.py"}, pup={"install": "x", "pack_dir": "p"},
                 requires={"env": {"X_VENV": ""}}, profiles={"rpi4": {"apply": "python3 board.py"}})
        bad = " ".join(K.problems(b))
        v2 = {k: v for k, v in V2.items() if v is not None}
        for word in ("`run`", "`options`", "pup.install", "pup.pack_dir", "requires.env", "profiles.rpi4"):
            self.assertIn(word, bad)
        self.assertEqual(K.problems(v2), [])

    def test_builder_accepts_facts_and_refuses_commands(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from mpf_godot import bundle
        spec = {"id": "demo", "format": 2, "precheck": ["true"], "mpf": V2["mpf"], "settings": V2["settings"], "addons": V2["addons"]}
        self.assertEqual(bundle.validate_spec(spec), [])
        self.assertIn("`run`", " ".join(bundle.validate_spec(dict(spec, run={"start": "x"}))))
        m = bundle.manifest("/nonexistent", spec, "1.0", "all")
        self.assertEqual((m["format"], m["game_dir"], m["addons"]), (2, "game", V2["addons"]))
        self.assertNotIn("run", m)

    def test_board_from_the_device_tree(self):
        saved, env = K.DT_MODEL, os.environ.pop("MPF_BOARD", None)
        try:
            for model, name in (("Raspberry Pi 4 Model B Rev 1.4", "rpi4"), ("Raspberry Pi 5 Model B", "rpi5"),
                                ("NVIDIA Jetson Xavier NX Developer Kit", "jetson")):
                K.DT_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_model")
                open(K.DT_MODEL, "w").write(model)
                self.assertEqual(K.board(), name)
            os.remove(K.DT_MODEL)
        finally:
            K.DT_MODEL = saved
            if env is not None:
                os.environ["MPF_BOARD"] = env


class Platform(Base):
    def setUp(self):
        super().setUp()
        self.bridge = D.bridge_dir
        D.bridge_dir = lambda: None
        D.SERUM_SAVED, D.SERUM = D.SERUM, os.path.join(self.t.name, "serum")
        open(C.GAME_ENV, "w").write("MPF_GAME_ARGS=-- --rendering-driver opengl3\n")

    def tearDown(self):
        D.bridge_dir, D.SERUM = self.bridge, D.SERUM_SAVED
        super().tearDown()

    def game(self, extra=None, files=None):
        state, msg = self.install(extra=dict(V2, **(extra or {})), files=dict(FILES, **(files or {})))
        self.assertEqual(state, "done", msg)
        return os.path.join(C.GAMES, "demo@1.0")

    def test_missing_declared_file_is_refused(self):
        state, msg = self.install(extra=V2, files={k: v for k, v in FILES.items() if k != "game/config/hw_proc.yaml"})
        self.assertEqual(state, "error")
        self.assertIn("hw_proc.yaml", msg)
        state, msg = self.install(extra=dict(V2, run={"start": "echo"}), files=FILES)
        self.assertIn("`run`", msg)

    def test_platform_starts_it_from_the_facts(self):
        game = self.game()
        os.environ["MPF_BOARD"] = "x86"
        try:
            argv, cwd, env = G.contract_command(game, G.read_bundle(game), G.game_env())
        finally:
            del os.environ["MPF_BOARD"]
        self.assertEqual(argv[1:6], ["-m", "mpf_godot", "run", os.path.join(game, "game"), "-c"])
        self.assertEqual(argv[6], "config,hw_virtual")
        self.assertEqual(argv[7:], ["--", "--rendering-driver", "opengl3", "--", "--dmd=hd"])
        self.assertEqual(env["MPF_ADDONS"], os.path.join(game, "addons/hd_art"))
        self.assertNotIn("MPF_PUP_PACK", env)
        self.assertIn("music = true", open(os.path.join(game, "game/pup.local.cfg")).read())

    def test_settings_are_the_platforms_and_follow_the_board(self):
        game = self.game()
        G.settings_save(game, {"o.machine.hw": "proc", "o.pup.music": "false", "o.dmd.mode": "hd"})
        self.assertEqual(G.settings_values(game), {"machine.hw": "proc", "pup.music": False, "dmd.mode": "hd"})
        P = K.plan(game, G.read_bundle(game), "rpi4")
        self.assertEqual(P["configs"], ["config", "hw_proc"])
        self.assertEqual(P["godot_args"], ["--max-fps=30", "--dmd=classic"])    # the Pi 4 cannot run HD: its default wins
        self.assertNotIn("MPF_ADDONS", P["env"])
        self.assertEqual(K.schema(game, G.read_bundle(game), "rpi4")["options"][0]["choices"], ["classic"])
        with self.assertRaises(ValueError):
            G.settings_save(game, {"o.dmd.mode": "neon"})

    def test_pup_pack_is_unpacked_untouched_and_given_by_path(self):
        game = self.game()
        p = os.path.join(C.UPLOADS, "pack.zip")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("PUPVideos/demo/triggers.pup", "t")
            z.writestr("PUPVideos/demo/Drain/a.mp4", "video")
        G.assign_pup("demo@1.0", G.pup_store(p, "author.zip"))
        self.assertTrue(G.pup_installed(game))
        self.assertEqual(G.pup_assigned(game), "author.zip")
        env = K.plan(game, G.read_bundle(game), "x86")["env"]
        self.assertEqual(open(os.path.join(env["MPF_PUP_PACK"], "Drain/a.mp4")).read(), "video")
        self.assertFalse(os.path.realpath(env["MPF_PUP_PACK"]).startswith(os.path.realpath(game)))

    def test_update_keeps_platform_settings_and_pack(self):
        game = self.game()
        G.settings_save(game, {"o.machine.hw": "proc"})
        state, msg = self.install(extra=V2, files=FILES, version="1.1")
        self.assertEqual(state, "done", msg)
        self.assertEqual(G.settings_values(os.path.join(C.GAMES, "demo@1.1")), {"machine.hw": "proc"})


if __name__ == "__main__":
    unittest.main()
