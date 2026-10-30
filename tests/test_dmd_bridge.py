"""native/dmd_bridge against the real libdmdutil (set DMDUTIL_DIR to the output of native/dmdutil/build_dmdutil.sh plus
native/dmd_bridge/build.sh): the shades of a frame come out scaled by the single colour in the RGB24 picture libdmdutil
makes, with no device attached. Skipped without it (the library takes minutes to build)."""
import os
import subprocess
import tempfile
import time
import unittest

D = os.environ.get("DMDUTIL_DIR", "")
W, H = 128, 32


@unittest.skipUnless(D and os.path.exists(os.path.join(D, "dmd_bridge")), "set DMDUTIL_DIR to a built libdmdutil with dmd_bridge")
class TestBridge(unittest.TestCase):
    def test_shades_scale_the_colour_without_a_colourisation(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "rgb.bin")
            p = subprocess.Popen([os.path.join(D, "dmd_bridge"), "--color", "2a6cff", "--shades", "--rgb-out", out],
                                 stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            frame = bytearray(W * H)
            frame[5 * W + 9] = 15
            p.stdin.write(bytes(frame))
            p.stdin.flush()
            for _ in range(50):
                if os.path.exists(out):
                    break
                time.sleep(0.1)
            time.sleep(0.5)
            p.stdin.close()
            p.wait(15)
            with open(out, "rb") as f:
                pic = f.read()
        self.assertEqual(W * H * 3, len(pic))
        self.assertEqual((0x2A, 0x6C, 0xFF), tuple(pic[(5 * W + 9) * 3:(5 * W + 9) * 3 + 3]))
        self.assertEqual((0, 0, 0), tuple(pic[:3]))


if __name__ == "__main__":
    unittest.main()
