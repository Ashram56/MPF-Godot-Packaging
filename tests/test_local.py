"""The local platform (mpf_godot/local.py): a game bundle installed and started on a desktop the way the cabinet's page does it.
Each test runs `python -m mpf_godot local` in a fresh MPF_LOCAL_DIR, with a stand-in Godot (the import) and a stand-in dmd_bridge."""
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCHEMA = {"groups": [{"id": "d", "label": "Display"}], "options": [
    {"id": "dmd.mode", "group": "d", "label": "Look", "type": "choice", "choices": ["hd", "classic"], "default": "hd",
     "target": {"godot_arg": "--dmd"}}]}


def bundle(version="1.0", **over):
    b = {"format": 2, "id": "demo", "name": "Demo", "version": version, "game_dir": "game", "target": {"os": "linux", "arch": "all"},
         "mpf": {"configs": ["config"], "hardware": {"virtual": ["hw_virtual"]}}, "dmd": {"rom": "demo_100"},
         "pup": {"rom": "demo_100"}, "settings": {"schema": "settings.json"}, "platform_addons": ["dmd_out"]}
    b.update(over)
    return b


def archive(path, b, files=None):
    files = dict({"game/project.godot": b"", "game/config/config.yaml": b"", "game/config/hw_virtual.yaml": b"",
                  "game/rules.py": b"import json\n", "settings.json": json.dumps(SCHEMA).encode()}, **(files or {}))
    files["bundle.json"] = json.dumps(b).encode()
    top = f"{b['id']}-{b['version']}"
    with tarfile.open(path, "w:xz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    with open(path, "rb") as f, open(path + ".sha256", "w") as s:
        s.write(hashlib.sha256(f.read()).hexdigest() + "  " + os.path.basename(path) + "\n")
    return path


@unittest.skipIf(os.name == "nt", "the stand-in Godot and dmd_bridge are shell scripts")
class Local(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = self.tmp.name
        self.local = os.path.join(self.t, "local")
        godot = os.path.join(self.t, "godot")
        with open(godot, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(godot, 0o755)
        bridge = os.path.join(self.t, "bridge")
        os.makedirs(bridge)
        with open(os.path.join(bridge, "dmd_bridge"), "w") as f:
            f.write("#!/bin/sh\nexit 0\n")              # --probe: a ZeDMD answers
        os.chmod(os.path.join(bridge, "dmd_bridge"), 0o755)
        open(os.path.join(bridge, "libserum64.so"), "w").close()
        self.env = dict(os.environ, MPF_LOCAL_DIR=self.local, GODOT=godot, MPF_DMD_BRIDGE_DIR=bridge, PYTHONPATH=ROOT)
        for k in ("MPF_GAMES_DIR", "MPF_STATE_DIR", "MPF_PUP_DIR", "MPF_SERUM_DIR", "MPF_JOB_FILE", "MPF_PLATFORM_DIR"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def local_cmd(self, *args, ok=True):
        r = subprocess.run([sys.executable, "-m", "mpf_godot", "local"] + list(args), cwd=ROOT, env=self.env,
                           capture_output=True, text=True, timeout=120)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_install_checks_the_sha_and_adds_the_platform_addons(self):
        a = archive(os.path.join(self.t, "demo.tar.xz"), bundle())
        out = self.local_cmd("install", a).stdout
        game = os.path.join(self.local, "games", "demo@1.0")
        self.assertIn("is the active game", out)
        self.assertTrue(os.path.isfile(os.path.join(game, "game", "addons", "dmd_out", "dmd_out.gd")))
        self.assertIn("* demo@1.0", self.local_cmd("list").stdout)
        with open(a + ".sha256", "w") as s:
            s.write("0" * 64 + "\n")
        r = self.local_cmd("install", a, ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("sha256 does not match", r.stdout + r.stderr)

    def test_a_bundle_with_commands_is_refused(self):
        a = archive(os.path.join(self.t, "bad.tar.xz"), bundle(run={"start": "python3 start.py"}))
        r = self.local_cmd("install", a, ok=False)
        self.assertIn("cannot start", r.stdout + r.stderr)
        self.assertFalse(os.path.isdir(os.path.join(self.local, "games", "demo@1.0")))

    def test_pup_settings_and_zedmd_with_serum(self):
        self.local_cmd("install", archive(os.path.join(self.t, "demo.tar.xz"), bundle()))
        pack = os.path.join(self.t, "Demo PuP.zip")
        with zipfile.ZipFile(pack, "w") as z:
            z.writestr("Demo/demo_100/triggers.pup", "x")
            z.writestr("Demo/demo_100/Backglass/a.mp4", "v")
        self.local_cmd("pup", pack)
        link = os.path.join(self.local, "games", "demo@1.0", ".platform", "pup")
        self.assertTrue(os.path.isfile(os.path.join(link, "triggers.pup")))
        serum = os.path.join(self.t, "demo_100.cROMc")
        open(serum, "w").close()
        self.local_cmd("serum", serum)
        self.local_cmd("set", "dmd.mode=classic")
        self.local_cmd("dmd", "--port", "COM7", "--color", "#ff0000")
        out = self.local_cmd("start", "--dmd", "zedmd", "--dry-run").stdout
        for want in ("--dmd=classic", "--zedmd=#ff0000", "--zedmd-shades", "--zedmd-feed=" + os.path.join(self.env["MPF_DMD_BRIDGE_DIR"], "dmd_bridge"),
                     "--zedmd-feed-arg=--rom --zedmd-feed-arg=demo_100", "--zedmd-feed-arg=--device --zedmd-feed-arg=COM7",
                     "MPF_DMD_OUTPUT=zedmd", "MPF_PUP_PACK="):
            self.assertIn(want, out)
        lcd = self.local_cmd("start", "--dmd", "lcd", "--dry-run").stdout
        self.assertIn("MPF_DMD_OUTPUT=lcd", lcd)
        self.assertNotIn("--zedmd", lcd)

    def test_a_new_version_keeps_settings_and_pack(self):
        self.local_cmd("install", archive(os.path.join(self.t, "v1.tar.xz"), bundle("1.0")))
        pack = os.path.join(self.t, "p.zip")
        with zipfile.ZipFile(pack, "w") as z:
            z.writestr("triggers.pup", "x")
        self.local_cmd("pup", pack)
        self.local_cmd("set", "dmd.mode=classic")
        self.local_cmd("install", archive(os.path.join(self.t, "v2.tar.xz"), bundle("2.0")))
        g2 = os.path.join(self.local, "games", "demo@2.0")
        self.assertEqual(json.load(open(os.path.join(g2, ".platform", "settings.json"))), {"dmd.mode": "classic"})
        self.assertTrue(os.path.isfile(os.path.join(g2, ".platform", "pup", "triggers.pup")))
        self.assertIn("* demo@2.0", self.local_cmd("list").stdout)


if __name__ == "__main__":
    unittest.main()
