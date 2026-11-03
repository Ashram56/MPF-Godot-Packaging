"""The Docker files: scripts parse, the stand-in systemctl keeps the game's state, the Dockerfile copies files that exist."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "docker")
SCRIPTS = ["entrypoint.sh", "mpf-game-run", "systemctl", "journalctl"]


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class DockerFiles(unittest.TestCase):

    def test_scripts_parse(self):
        for s in SCRIPTS:
            self.assertEqual(subprocess.run(["bash", "-n", os.path.join(D, s)]).returncode, 0, s)

    def test_dockerfile_installs_existing_files(self):
        text = open(os.path.join(D, "Dockerfile")).read()
        for m in re.finditer(r"install -m 755 ([^\\\n]+?)(?: /usr/local/bin/| \\|$)", text):
            for f in m.group(1).split():
                if f.startswith("docker/"):
                    self.assertTrue(os.path.isfile(os.path.join(ROOT, f)), f)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "native", "libzedmd", "build_libzedmd.sh")))

    def test_systemctl_standin_enable_and_status(self):
        with tempfile.TemporaryDirectory() as t:
            env = dict(os.environ, MPF_STATE_DIR=t)
            sc = os.path.join(D, "systemctl")

            def call(*a):
                return subprocess.run(["bash", sc, *a], env=env, capture_output=True, text=True).returncode
            self.assertEqual(call("is-enabled", "--quiet", "mpf-game.service"), 1)
            self.assertEqual(call("enable", "mpf-game.service"), 0)
            self.assertEqual(call("is-enabled", "--quiet", "mpf-game.service"), 0)
            self.assertEqual(call("disable", "mpf-game.service"), 0)
            self.assertEqual(call("is-enabled", "--quiet", "mpf-game.service"), 1)
            self.assertEqual(call("reload", "ssh.service"), 0)       # another unit: accepted, ignored


if __name__ == "__main__":
    unittest.main()
