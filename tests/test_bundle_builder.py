"""mpf_godot/bundle.py: the generic game bundle builder (the Godot import itself is not run here)."""
import json
import os
import subprocess
import tempfile
import unittest

from mpf_godot import bundle

IMPORT = 'path.s3tc="res://.godot/imported/a.s3tc.ctex"\npath.etc2="res://.godot/imported/a.etc2.ctex"\n' \
         'dest_files=["res://.godot/imported/a.s3tc.ctex", "res://.godot/imported/a.etc2.ctex"]\n' \
         '"imported_formats": ["s3tc_bptc", "etc2_astc"],\n'


def write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class Builder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(os.path.join(self.root, "game", "project.godot"), "[rendering]\n\nrenderer=\"x\"\n")
        write(os.path.join(self.root, "game", "main.gd"), "x")
        write(os.path.join(self.root, "game", "addons", "gde_gozen", "bin", "libgozen.so"), "binary")
        write(os.path.join(self.root, "gen", "frame.png"), "png")
        write(os.path.join(self.root, "tpl.import"), "[remap]\n")
        subprocess.run(["git", "-C", self.root, "init", "-q"], check=True)
        subprocess.run(["git", "-C", self.root, "add", "game"], check=True)
        self.spec = {"id": "g", "copy": ["gen"], "never": ["game/data"], "never_names": ["*.local.cfg"],
                     "import_seed": [{"dir": "gen", "template": "tpl.import"}], "platform_addons": ["gde_gozen"],
                     "keep_on_update": ["game/data"]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_stage_has_no_addon_binary(self):
        stage = os.path.join(self.root, "stage")
        os.makedirs(stage)
        bundle.stage_tree(self.root, self.spec, stage)
        self.assertTrue(os.path.isfile(os.path.join(stage, "game", "main.gd")))
        self.assertTrue(os.path.isfile(os.path.join(stage, "gen", "frame.png")))
        self.assertFalse(os.path.exists(os.path.join(stage, "game", "addons")))

    def test_cabinet_data_refused(self):
        stage = os.path.join(self.root, "stage")
        write(os.path.join(stage, "game", "data", "x"))
        write(os.path.join(stage, "game", "a.local.cfg"))
        self.assertEqual(sorted(bundle.forbidden(self.spec, stage)), ["game/a.local.cfg", "game/data"])

    def test_seed_and_formats(self):
        stage = os.path.join(self.root, "stage")
        write(os.path.join(stage, "gen", "frame.png"))
        self.assertEqual(bundle.seed_imports(self.root, self.spec, stage), 1)
        self.assertTrue(os.path.isfile(os.path.join(stage, "gen", "frame.png.import")))
        bundle.set_texture_formats(os.path.join(self.root, "game", "project.godot"), "both")
        text = open(os.path.join(self.root, "game", "project.godot")).read()
        self.assertIn("import_etc2_astc=true", text)
        self.assertIn("import_s3tc_bptc=true", text)

    def test_prune_etc2(self):
        game = os.path.join(self.root, "pg")
        write(os.path.join(game, "t.png.import"), IMPORT)
        write(os.path.join(game, ".godot", "imported", "a.s3tc.ctex"))
        write(os.path.join(game, ".godot", "imported", "a.etc2.ctex"))
        self.assertEqual(bundle.prune_formats(game, "etc2"), 1)
        text = open(os.path.join(game, "t.png.import")).read()
        self.assertNotIn("s3tc", text)
        self.assertIn("etc2", text)
        self.assertEqual(bundle.prune_formats(game, "both"), 0)

    def test_manifest(self):
        m = bundle.manifest(self.root, self.spec, "v1", "all")
        self.assertEqual(m["target"], {"os": "linux", "arch": "arm64+x86_64", "texture_formats": "both"})
        self.assertEqual(m["platform_addons"], ["gde_gozen"])
        json.dumps(m)


if __name__ == "__main__":
    unittest.main()
