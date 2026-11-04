"""Bundle format 2: files and facts only, the platform starts the game (common/netconfig/mpf_contract.py, platforms/game-bundles.md)."""
import sys as _sys
import unittest as _unittest

if not _sys.platform.startswith("linux"):
    raise _unittest.SkipTest("the platform page and its netconfig code run on the Linux images only")

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
    {"id": "pup.layout", "group": "d", "label": "Layout", "type": "choice", "choices": ["split", "stacked"], "default": "split",
     "target": {"ini": "game/pup.local.cfg", "section": "pup", "key": "layout"}},
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

    def test_dmd_looks_and_reserved_names(self):
        v2 = {k: v for k, v in V2.items() if v is not None}
        ok = dict(v2, dmd={"looks": {"classic": ["--dmd=classic"], "hd": ["--dmd=hd", "--dmd-feed=hd"]}, "look": "hd"})
        self.assertEqual(K.problems(ok), [])
        for dmd, word in (({"looks": {"fancy": []}}, "fancy"), ({"looks": {"hd": "x"}}, "list of strings"),
                          ({"looks": {"hd": ["--dmd-size=1x1"]}}, "--dmd-size"), ({"looks": {"hd": ["--zedmd"]}}, "--zedmd"),
                          ({"looks": {"hd": []}, "look": "classic"}, "default"), ({"looks": []}, "object")):
            self.assertIn(word, " ".join(K.problems(dict(v2, dmd=dmd))), dmd)
        bad = dict(v2, profiles={"rpi4": {"godot_args": ["--dmd-preview=/x"]}})
        self.assertIn("--dmd-preview", " ".join(K.problems(bad)))
        self.assertTrue(K.reserved_arg("--dmd-size=1024x256") and not K.reserved_arg("--dmd-window=1024x256"))

    def test_builder_accepts_facts_and_refuses_commands(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from mpf_godot import bundle
        spec = {"id": "demo", "format": 2, "precheck": ["true"], "mpf": V2["mpf"], "settings": V2["settings"], "addons": V2["addons"]}
        self.assertEqual(bundle.validate_spec(spec), [])
        self.assertIn("`run`", " ".join(bundle.validate_spec(dict(spec, run={"start": "x"}))))
        m = bundle.manifest("/nonexistent", spec, "1.0", "all")
        self.assertEqual((m["format"], m["game_dir"], m["addons"]), (2, "game", V2["addons"]))
        self.assertNotIn("run", m)

    def test_platform_dir_found_on_an_image_without_the_variable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(os.path.join(t, "mpf_godot"))
            open(os.path.join(t, "mpf_godot", "__init__.py"), "w").close()
            saved = os.environ.pop("MPF_PLATFORM_DIR", None)
            try:
                self.assertEqual(C.find_platform_dir(user="nobody-here", here=t), t)
                os.environ["MPF_PLATFORM_DIR"] = "/x"
                self.assertEqual(C.find_platform_dir(user="nobody-here", here=t), "/x")
            finally:
                os.environ.pop("MPF_PLATFORM_DIR", None)
                if saved is not None:
                    os.environ["MPF_PLATFORM_DIR"] = saved

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

    def test_windows_amd64_is_x86(self):
        """platform.machine() is "AMD64" on Windows: it must not be taken for an ARM64 board."""
        import unittest.mock as m
        env = os.environ.pop("MPF_BOARD", None)
        try:
            for machine, name in (("AMD64", "x86"), ("x86_64", "x86"), ("arm64", "arm64"), ("aarch64", "arm64")):
                with m.patch.object(K.platform, "machine", return_value=machine), m.patch.object(K, "DT_MODEL", "/nonexistent"):
                    self.assertEqual(K.board(), name, machine)
        finally:
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

    def test_screens_card_owns_the_monitor_settings(self):
        import mpf_screens as SC
        schema = dict(SCHEMA, options=SCHEMA["options"] + [
            {"id": "pup.dmd.screen", "group": "d", "label": "DMD monitor", "type": "integer", "min": 0, "max": 7, "default": 0,
             "target": {"ini": "game/pup.local.cfg", "section": "dmd", "key": "screen"}}])
        game = self.game({"screens": [{"id": "dmd", "label": "DMD", "setting": "pup.dmd.screen"}]},
                         {"settings.json": json.dumps(schema).encode()})
        b = G.read_bundle(game)
        self.assertEqual(G.screens_state(game), [{"id": "dmd", "label": "DMD", "index": 0, "enabled": True}])
        G.screen_set(game, "dmd", "1")
        self.assertEqual(G.screens_state(game)[0]["index"], 1)
        self.assertNotIn("pup.dmd.screen", [o["id"] for o in G.settings_schema(game)["options"]])     # not in the generic form
        G.settings_save(game, {"o.dmd.mode": "classic"})                                                # saving it does not reset the screen
        self.assertEqual(G.screens_state(game)[0]["index"], 1)
        with self.assertRaises(ValueError):
            G.screen_set(game, "nope", 1)
        with self.assertRaises(ValueError):
            G.screen_set(game, "dmd", 9)
        self.assertEqual(K.problems(b, game), [])
        self.assertIn("integer setting", " ".join(K.problems(dict(b, screens=[{"id": "x", "label": "X", "setting": "dmd.mode"}]), game)))
        self.assertIn("`screens` must be", " ".join(K.problems(dict(b, screens=["x"]))))

    def test_parse_xrandr(self):
        import mpf_screens as SC
        text = ("Screen 0: minimum 8 x 8, current 3840 x 1080\nHDMI-1 connected 1920x1080+1920+0 (normal left) 527mm x 296mm\n   1920x1080 60.00*+\n"
                "DP-1 connected primary 1920x1080+0+0 (normal left) 527mm x 296mm\nVGA-1 disconnected (normal left)\n")
        got = SC.parse_xrandr(text)
        self.assertEqual([(s["name"], s["primary"], s["x"]) for s in got], [("DP-1", True, 0), ("HDMI-1", False, 1920)])

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
        self.assertIn('layout = "split"', open(os.path.join(game, "game/pup.local.cfg")).read())     # text is quoted for Godot's ConfigFile

    def test_platform_addons_and_board_settings_go_into_game_dir(self):
        """A game whose Godot project is not in game/ (game_dir "."): GMC and override.cfg must land beside its project.godot,
        else Godot cannot load GMC and MPF never connects (observed 2026-11-02 on a game built from the docs alone)."""
        gmc = os.path.join(self.t.name, "platform", "mpf-gmc")
        os.makedirs(gmc)
        open(os.path.join(gmc, "plugin.cfg"), "w").write("[plugin]\n")
        ov = os.path.join(self.t.name, "override.cfg")
        open(ov, "w").write("[audio]\n")
        saved = G.platform_addon, G.reimport_scripts
        G.platform_addon, G.reimport_scripts = (lambda name: gmc if name == "mpf-gmc" else None), (lambda dest, b: None)
        C.GAME_OVERRIDE = ov
        files = {k[len("game/"):] if k.startswith("game/") else k: v for k, v in FILES.items()}
        try:
            game = self.game(extra={"game_dir": ".", "platform_addons": ["mpf-gmc"], "keep_on_update": ["data"]}, files=files)
        finally:
            G.platform_addon, G.reimport_scripts = saved
            C.GAME_OVERRIDE = ""
        self.assertTrue(os.path.isfile(os.path.join(game, "addons", "mpf-gmc", "plugin.cfg")))
        self.assertTrue(os.path.isfile(os.path.join(game, "override.cfg")))
        self.assertFalse(os.path.exists(os.path.join(game, "game", "addons")))
        argv = G.contract_command(game, G.read_bundle(game), G.game_env())[0]
        self.assertEqual(argv[4], game)

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
