"""End to end, once the toolchain is installed (python -m mpf_godot setup): examples/minimal gets the patched GMC, Godot
imports and starts it, GMC listens, MPF connects over BCP and initialises. Skipped when the toolchain is missing."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from mpf_godot import toolchain as tc  # noqa: E402

READY = os.path.exists(tc.venv_exe("mpf")) and os.path.exists(tc.godot_path()) \
    and os.path.exists(os.path.join(tc.gmc_dir(), "plugin.cfg"))


@unittest.skipUnless(READY, "the toolchain is not installed (python -m mpf_godot setup)")
class TestSmoke(unittest.TestCase):

    def test_minimal_game_connects(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        game = os.path.join(tmp, "minimal")
        shutil.copytree(os.path.join(ROOT, "examples", "minimal"), game)
        py = tc.venv_python()
        subprocess.run([py, "-m", "mpf_godot", "addons", game], check=True, cwd=ROOT, capture_output=True)
        with open(os.path.join(game, "addons", "mpf-gmc", "scripts", "bcp_server.gd"), encoding="utf-8") as f:
            self.assertIn("bcp-partial-lines", f.read())
        r = subprocess.run([py, "-m", "mpf_godot", "run", game, "--seconds", "12"], cwd=ROOT, capture_output=True,
                           text=True, timeout=600)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("GMC is listening", r.stdout)
        with open(os.path.join(game, "logs", "godot.log"), encoding="utf-8", errors="replace") as f:
            godot = f.read()
        self.assertIn("Client connected from", godot)
        self.assertNotIn("SCRIPT ERROR", godot)
        with open(os.path.join(game, "logs", "mpf.log"), encoding="utf-8", errors="replace") as f:
            mpf = f.read()
        self.assertIn("Connected BCP to 'local_display'", mpf)
        self.assertIn("init_done", mpf)

    def test_mpf_starts_with_monitor_installed(self):
        """fixes/mpf/ruamel-yaml-clib-0.2.15.md: with mpf-monitor in the venv, `mpf` must still start."""
        r = subprocess.run([tc.venv_exe("mpf"), "--version"], capture_output=True, text=True, timeout=120)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn(tc.MPF_VERSION, r.stdout)


if __name__ == "__main__":
    unittest.main()
