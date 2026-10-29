"""addons/dmd_out in a real (Xvfb) Godot: a published picture reaches the fake MPF as an "rgb_dmd_frame" of the device's
size, in the add-on's colour. Skipped without Godot, xvfb-run or a display driver. The classic 128x32 picture is the root
viewport (16 shades), 256x64 and HD pictures are published and resized (8 bits)."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.join(ROOT, "tests", "godot_dmd_out")


def godot():
    for c in (os.environ.get("GODOT"), os.path.join(ROOT, "toolchain", "godot", "godot")):
        if c and os.path.exists(c):
            return c
    return None


@unittest.skipUnless(godot() and shutil.which("xvfb-run"), "needs Godot (GODOT=) and xvfb-run")
class TestDmdOutInGodot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.project = os.path.join(cls.tmp, "p")
        shutil.copytree(PROJECT, cls.project)
        shutil.copy2(os.path.join(ROOT, "addons", "dmd_out", "dmd_out.gd"), cls.project)
        for _ in range(2):               # import first: class cache, so the run is clean
            subprocess.run([godot(), "--headless", "--path", cls.project, "--import"], capture_output=True, timeout=300)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_probe(self, *user_args):
        r = subprocess.run(["xvfb-run", "-a", godot(), "--path", self.project, "--rendering-driver", "opengl3",
                            "--", "--pin2dmd"] + list(user_args), capture_output=True, text=True, timeout=180)
        m = re.search(r"PROBE (\w+) (\w+) (\d+) first=(\d+),(\d+),(\d+) last=(\d+),(\d+),(\d+)", r.stdout)
        self.assertIsNotNone(m, r.stdout[-800:] + r.stderr[-800:])
        return m.group(1), m.group(2), int(m.group(3)), tuple(int(m.group(i)) for i in (4, 5, 6)), \
            tuple(int(m.group(i)) for i in (7, 8, 9))

    def test_classic_128x32_is_the_root_viewport(self):
        command, name, size, first, last = self.run_probe()
        self.assertEqual(("rgb_dmd_frame", "default", 128 * 32 * 3), (command, name, size))
        self.assertEqual((255, 115, 13), first)           # white dot = full shade of the default colour #ff730d
        self.assertEqual((255, 115, 13), last)

    def test_256x64_published_picture(self):
        _, _, size, first, last = self.run_probe("--dmd-size=256x64", "--dmd-feed=256x64")
        self.assertEqual(256 * 64 * 3, size)
        for dot in (first, last):                          # mid grey: half the colour, 8 bits
            self.assertAlmostEqual(128, dot[0], delta=2)
            self.assertAlmostEqual(57, dot[1], delta=2)

    def test_hd_picture_is_shrunk_to_the_device(self):
        _, _, size, first, last = self.run_probe("--dmd-size=256x64", "--dmd-feed=hd")
        self.assertEqual(256 * 64 * 3, size)
        self.assertEqual((255, 115, 13), first)            # left half white
        self.assertEqual((0, 0, 0), last)                  # right half black


if __name__ == "__main__":
    unittest.main()
