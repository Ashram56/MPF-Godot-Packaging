"""native/dmd_bridge (PPUC's libzedmd for the ZeDMD, libserum for colour) with --rgb-out, so no ZeDMD is needed. Set
LIBZEDMD_DIR to the output of native/libzedmd/build_libzedmd.sh plus native/dmd_bridge/build.sh (it takes a while to build, so
the tests are skipped without it); LIBSERUM adds the real libserum, SERUM_ALTCOLOR/SERUM_ROM a real colourisation."""
import os
import subprocess
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_zedmd_feed import FAKE_SERUM

D = os.environ.get("LIBZEDMD_DIR", "")
W, H = 128, 32


def shades(dots):
    b = bytearray(W * H)
    for x, y, n in dots:
        b[y * W + x] = n
    return bytes(b)


@unittest.skipUnless(D and os.path.exists(os.path.join(D, "dmd_bridge")), "set LIBZEDMD_DIR to a built libzedmd with dmd_bridge")
class TestBridge(unittest.TestCase):
    def picture(self, args, frame):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "rgb.bin")
            p = subprocess.Popen([os.path.join(D, "dmd_bridge"), "--shades", "--rgb-out", out] + args,
                                 stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            p.stdin.write(frame)
            p.stdin.flush()
            for _ in range(60):
                if os.path.exists(out) and os.path.getsize(out) == W * H * 3:
                    break
                time.sleep(0.1)
            time.sleep(0.3)
            p.stdin.close()
            err = p.communicate(timeout=15)[1].decode()
            with open(out, "rb") as f:
                return f.read(), err

    def px(self, pic, x, y):
        return tuple(pic[(y * W + x) * 3:(y * W + x) * 3 + 3])

    def test_shades_scale_the_colour_without_a_colourisation(self):
        pic, _ = self.picture(["--color", "2a6cff"], shades([(9, 5, 15), (100, 30, 5)]))
        self.assertEqual((0x2A, 0x6C, 0xFF), self.px(pic, 9, 5))
        self.assertEqual((0x2A * 5 // 15, 0x6C * 5 // 15, 0xFF * 5 // 15), self.px(pic, 100, 30))
        self.assertEqual((0, 0, 0), self.px(pic, 0, 0))

    def test_serum_library_colours_the_frame(self):
        """libserum is dlopen'ed: a stand-in with its C names returns a version 2 picture (RGB565) made from the shades."""
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "fake.c")
            with open(src, "w") as f:
                f.write(FAKE_SERUM)
            lib = os.path.join(d, "libfake.so")
            subprocess.check_call([shutil.which("cc") or "gcc", "-shared", "-fPIC", "-o", lib, src])
            pic, err = self.picture(["--serum-lib", lib, "--altcolor", d, "--rom", "rom"], shades([(9, 5, 15), (100, 30, 8)]))
        self.assertEqual((15 * 255 // 31, 0, 0), self.px(pic, 9, 5))
        self.assertEqual((8 * 255 // 31, 0, 0), self.px(pic, 100, 30))

    @unittest.skipUnless(os.environ.get("LIBSERUM"), "set LIBSERUM to a built libserum")
    def test_real_libserum_without_a_colourisation_keeps_the_colour(self):
        pic, err = self.picture(["--color", "ff0000", "--serum-lib", os.environ["LIBSERUM"], "--altcolor", "/nonexistent",
                                 "--rom", "nothing"], shades([(9, 5, 15)]))
        self.assertEqual((255, 0, 0), self.px(pic, 9, 5))
        self.assertIn("no colourisation nothing", err)

    @unittest.skipUnless(os.environ.get("LIBSERUM") and os.environ.get("SERUM_ALTCOLOR") and os.environ.get("SERUM_ROM"),
                         "set LIBSERUM, SERUM_ALTCOLOR and SERUM_ROM for a real colourisation")
    def test_real_colourisation_loads(self):
        pic, err = self.picture(["--color", "ff0000", "--serum-lib", os.environ["LIBSERUM"], "--altcolor",
                                 os.environ["SERUM_ALTCOLOR"], "--rom", os.environ["SERUM_ROM"]], shades([(9, 5, 15)]))
        self.assertIn("serum: " + os.environ["SERUM_ROM"] + " loaded", err)
        self.assertEqual((255, 0, 0), self.px(pic, 9, 5))        # a frame that is not the game's: the single colour


if __name__ == "__main__":
    unittest.main()
