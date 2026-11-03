"""Own code in a bundle (common/games/make_bundle.py) and bundles in an image before flashing (common/games/inject_image.py)."""
import sys as _sys
import unittest as _unittest

if not _sys.platform.startswith("linux"):
    raise _unittest.SkipTest("the platform page and its netconfig code run on the Linux images only")

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests import test_games as TG

HERE = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.join(HERE, "..", "common", "games")
G, C = TG.G, TG.C
sys.path.insert(0, os.path.join(HERE, "..", "common", "netconfig"))
import mpf_contract as K  # noqa: E402


def tool(name, *args, **kw):
    return subprocess.run([sys.executable, os.path.join(GAMES, name), *args], capture_output=True, text=True, **kw)


class MakeBundle(TG.Base):
    def src(self):
        s = os.path.join(self.t.name, "mygame")
        for d in ("config", "logs", "__pycache__", ".godot", "addons/mpf-gmc", "addons/mine", "pup"):
            os.makedirs(os.path.join(s, d))
        for rel, data in (("project.godot", "[application]\n"), ("config/config.yaml", "x: 1\n"), ("config/hw_virtual.yaml", "x: 1\n"),
                          ("config/hw_proc.yaml", "x: 1\n"), (".godot/uid_cache.bin", "u"), ("addons/mpf-gmc/plugin.cfg", "own copy"),
                          ("addons/mine/a.gd", "x"), ("pup/manifest.json", "{}"), ("logs/a.log", "log"), ("__pycache__/x.pyc", "c")):
            with open(os.path.join(s, rel), "w") as f:
                f.write(data)
        return s

    def unpack(self, arc):
        import tarfile
        with tarfile.open(arc) as t:
            names = t.getnames()
            b = json.load(t.extractfile([n for n in names if n.endswith("/bundle.json")][0]))
        return b, names

    def test_format_2_bundle_installs_and_the_platform_starts_it(self):
        out = os.path.join(self.t.name, "out")
        r = tool("make_bundle.py", self.src(), "--id", "my-game", "--name", "My game", "--version", "2.1", "--keep", "data",
                 "--hardware", "virtual=hw_virtual", "--hardware", "proc=hw_proc", "--dmd-rom", "mygame_100",
                 "--pup-rom", "mygame_100", "--pup-manifest", "pup/manifest.json",
                 "--platform-addon", "gde_gozen", "-o", out)            # mpf-gmc: built by `mpf_godot setup`, absent from a test machine
        self.assertEqual(r.returncode, 0, r.stderr)
        arc = os.path.join(out, "my-game@2.1.tar.xz")
        b, names = self.unpack(arc)
        self.assertEqual(b["format"], 2)
        self.assertEqual(b["mpf"], {"configs": ["config"], "hardware": {"virtual": ["hw_virtual"], "proc": ["hw_proc"]}})
        self.assertEqual(b["pup"], {"rom": "mygame_100", "manifest": "game/pup/manifest.json"})
        self.assertEqual(b["platform_addons"], ["gde_gozen"])
        self.assertEqual(b["keep_on_update"], ["game/data"])
        for k in ("run", "options", "launch", "extra", "requires"):
            self.assertNotIn(k, b)
        self.assertEqual(K.problems(b), [])
        self.assertIn("my-game@2.1/game/addons/mine/a.gd", names)                       # the game's own add-on stays
        self.assertIn("my-game@2.1/game/addons/mpf-gmc/plugin.cfg", names)              # not a platform add-on here: the game's copy
        self.assertFalse(any("scripts/package" in n or "/logs/" in n or "__pycache__" in n for n in names))
        sha = open(arc + ".sha256").read().split()[0]
        G.JOB_LOCK.acquire()
        G.run_job(G.install_game, arc, sha)
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"] + G.JOB["log"])
        game = os.path.join(C.GAMES, "my-game@2.1")
        self.assertTrue(os.path.isfile(os.path.join(game, "game", "config", "hw_proc.yaml")))
        self.assertEqual(K.plan(game, b, "x86")["configs"], ["config", "hw_virtual"])
        K.set_values(game, b, [("machine.hardware", "proc")])
        self.assertEqual(K.plan(game, b, "x86")["configs"], ["config", "hw_proc"])
        self.assertRaises(ValueError, K.set_values, game, b, [("machine.hardware", "bogus")])

    def test_one_hardware_set_needs_no_setting(self):
        out = os.path.join(self.t.name, "out")
        r = tool("make_bundle.py", self.src(), "--id", "one", "--version", "1", "--hardware", "virtual=hw_virtual", "-o", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        b, names = self.unpack(os.path.join(out, "one@1.tar.xz"))
        self.assertNotIn("settings", b)
        self.assertNotIn("one@1/settings.json", names)
        self.assertEqual(b["platform_addons"], ["gde_gozen", "mpf-gmc"])                # the default
        self.assertNotIn("one@1/game/addons/mpf-gmc/plugin.cfg", names)                 # the platform's copy is used

    def test_refuses_what_breaks_the_contract(self):
        s = self.src()
        out = self.t.name
        r = tool("make_bundle.py", s, "--id", "x", "--version", "1", "--hardware", "virtual=no_such", "-o", out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no_such.yaml", r.stderr)
        os.remove(os.path.join(s, "project.godot"))
        r = tool("make_bundle.py", s, "--id", "x", "--version", "1", "-o", out)
        self.assertIn("project.godot", r.stderr)

    def test_bad_arguments(self):
        s = self.src()
        for extra in (["--id", "Bad Id", "--version", "1"], ["--id", "ok", "--version", "bad version"], ["--id", "ok", "--version", "1", "--keep", "../x"],
                      ["--id", "ok", "--version", "1", "--hardware", "virtual"], ["--id", "ok", "--version", "1", "--pup-rom", "r"],
                      ["--id", "ok", "--version", "1", "--start", "mpf both"]):
            self.assertNotEqual(tool("make_bundle.py", s, *extra, "-o", self.t.name).returncode, 0, extra)


@unittest.skipUnless(shutil.which("sfdisk") or os.path.exists("/usr/sbin/sfdisk"), "needs sfdisk")
@unittest.skipUnless(shutil.which("debugfs") or os.path.exists("/usr/sbin/debugfs"), "needs debugfs")
class InjectImage(unittest.TestCase):
    def disk(self, t, label="gpt"):
        img = os.path.join(t, "disk.img")
        with open(img, "wb") as f:
            f.truncate(64 << 20)
        spec = "label: gpt\nstart=2048,size=16MiB,type=U\ntype=L,size=32MiB\n" if label == "gpt" else "label: dos\nstart=2048,size=16MiB,type=c\ntype=83,size=32MiB\n"
        subprocess.run(["/usr/sbin/sfdisk" if os.path.exists("/usr/sbin/sfdisk") else "sfdisk", "-q", img], input=spec, text=True, check=True)
        return img

    def ls(self, img):
        out = subprocess.run(["sfdisk", "-J", img], capture_output=True, text=True, env=dict(os.environ, PATH=os.environ["PATH"] + ":/usr/sbin:/sbin")).stdout
        part = json.loads(out)["partitiontable"]["partitions"][-1]
        dbg = shutil.which("debugfs") or "/usr/sbin/debugfs"
        r = subprocess.run([dbg, "-R", "ls -p /inbox", f"{img}?offset={part['start'] * 512}"], capture_output=True, text=True)
        return part, sorted(line.split("/")[5] for line in r.stdout.splitlines() if line.count("/") >= 5 and line.split("/")[5] not in (".", ".."))

    def test_gpt_and_dos_images(self):
        for label in ("gpt", "dos"):
            with tempfile.TemporaryDirectory() as t:
                img = self.disk(t, label)
                src = os.path.join(t, "g")
                os.makedirs(src)
                os.makedirs(os.path.join(src, "config"))
                open(os.path.join(src, "project.godot"), "w").write("[application]\n")
                open(os.path.join(src, "config", "config.yaml"), "w").write("x: 1\n")
                tool("make_bundle.py", src, "--id", "x", "--version", "1", "-o", t)
                open(os.path.join(t, "pack.zip"), "wb").write(b"PK")
                before = open(img, "rb").read(48 << 20)
                r = tool("inject_image.py", img, "--bundle", os.path.join(t, "x@1.tar.xz"), "--pup", os.path.join(t, "pack.zip") + ":x", "-o", os.path.join(t, "out.img"))
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
                self.assertEqual(open(img, "rb").read(48 << 20), before)         # the original is not touched
                out = os.path.join(t, "out.img")
                part, names = self.ls(out)
                self.assertEqual(names, ["01_x@1.tar.xz", "01_x@1.tar.xz.sha256", "x.pup.zip"], label)
                self.assertGreater(part["size"] * 512, 64 << 20)
                again = tool("inject_image.py", out, "--bundle", os.path.join(t, "x@1.tar.xz"), "-o", os.path.join(t, "again.img"))
                if label == "gpt":
                    self.assertNotEqual(again.returncode, 0)                    # a data partition is there already

    def test_nothing_to_add_and_missing_files(self):
        with tempfile.TemporaryDirectory() as t:
            img = self.disk(t)
            self.assertNotEqual(tool("inject_image.py", img).returncode, 0)
            self.assertNotEqual(tool("inject_image.py", img, "--bundle", os.path.join(t, "none.tar.xz")).returncode, 0)


if __name__ == "__main__":
    unittest.main()
