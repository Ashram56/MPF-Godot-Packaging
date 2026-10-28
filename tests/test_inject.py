"""Own code in a bundle (common/games/make_bundle.py) and bundles in an image before flashing (common/games/inject_image.py)."""
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


def tool(name, *args, **kw):
    return subprocess.run([sys.executable, os.path.join(GAMES, name), *args], capture_output=True, text=True, **kw)


class MakeBundle(TG.Base):
    def src(self):
        s = os.path.join(self.t.name, "mygame")
        os.makedirs(os.path.join(s, "config"))
        os.makedirs(os.path.join(s, "logs"))
        os.makedirs(os.path.join(s, "__pycache__"))
        for rel, data in (("run.py", "print('hi')\n"), ("config/machine.yaml", "x: 1\n"), ("logs/a.log", "log"), ("__pycache__/x.pyc", "c")):
            with open(os.path.join(s, rel), "w") as f:
                f.write(data)
        return s

    def test_bundle_installs_and_starts_with_the_given_command(self):
        out = os.path.join(self.t.name, "out")
        r = tool("make_bundle.py", self.src(), "--id", "my-game", "--name", "My game", "--version", "2.1", "--keep", "data", "-o", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        arc = os.path.join(out, "my-game@2.1.tar.xz")
        self.assertTrue(os.path.isfile(arc + ".sha256"))
        sha = open(arc + ".sha256").read().split()[0]
        G.JOB_LOCK.acquire()
        G.run_job(G.install_game, arc, sha)
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"] + G.JOB["log"])
        game = os.path.join(C.GAMES, "my-game@2.1")
        self.assertTrue(os.path.isfile(os.path.join(game, "game", "run.py")))
        self.assertTrue(os.path.isfile(os.path.join(game, "game", "config", "machine.yaml")))
        self.assertFalse(os.path.exists(os.path.join(game, "game", "__pycache__")))
        self.assertFalse(os.path.exists(os.path.join(game, "game", "logs", "a.log")))
        argv, cwd = G.game_command(game, G.read_bundle(game), {})
        self.assertEqual(argv[1:], ["run.py"])
        self.assertEqual(cwd, os.path.join(game, "game"))

    def test_bad_arguments(self):
        s = self.src()
        for extra in (["--id", "Bad Id", "--version", "1"], ["--id", "ok", "--version", "bad version"], ["--id", "ok", "--version", "1", "--keep", "../x"]):
            self.assertNotEqual(tool("make_bundle.py", s, *extra, "-o", self.t.name).returncode, 0, extra)

    def test_pack_folders_are_linked_not_copied_but_settings_are(self):
        s = self.src()
        os.makedirs(os.path.join(s, "pup"))
        os.makedirs(os.path.join(s, "data"))
        open(os.path.join(s, "pup", "v.mp4"), "w").write("video")
        open(os.path.join(s, "data", "scores"), "w").write("1")
        out = os.path.join(self.t.name, "out")
        for v in ("1", "2"):
            tool("make_bundle.py", s, "--id", "g", "--version", v, "--keep", "data", "--pup-dir", "pup", "-o", out)
            G.JOB_LOCK.acquire()
            G.run_job(G.install_game, os.path.join(out, f"g@{v}.tar.xz"), "")
            self.assertEqual(G.JOB["state"], "done", G.JOB["msg"])
        a = os.stat(os.path.join(C.GAMES, "g@1", "game", "pup", "v.mp4"))
        b = os.stat(os.path.join(C.GAMES, "g@2", "game", "pup", "v.mp4"))
        self.assertEqual(a.st_ino, b.st_ino)
        a = os.stat(os.path.join(C.GAMES, "g@1", "game", "data", "scores"))
        b = os.stat(os.path.join(C.GAMES, "g@2", "game", "data", "scores"))
        self.assertNotEqual(a.st_ino, b.st_ino)


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
                open(os.path.join(src, "run.py"), "w").write("pass\n")
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
