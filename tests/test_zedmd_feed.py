"""game/native/zedmd_feed (the C feeder) against a fake ZeDMD on a pty: handshake, then the zone packets it writes are
the ones the Python platform (mpf_godot/zedmd_native.py) builds for the same frames."""
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import tty
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from mpf_godot import zedmd_native as z

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "native", "zedmd_feed", "zedmd_feed.c")
W, H = 128, 32


def frame(dots=()):
    b = bytearray(W * H * 3)
    for x, y, c in dots:
        b[(y * W + x) * 3:(y * W + x) * 3 + 3] = bytes(c)
    return bytes(b)


def wire(packet):
    """A zone packet as written: header, zones, render, zero padded to the 64-byte write size."""
    data = z.FRAME + z.control(z.ZONES_RGB888, packet) + z.control(z.RENDER)
    return data.ljust(-(-len(data) // 64) * 64, b"\0")


@unittest.skipUnless(shutil.which("cc") or shutil.which("gcc"), "no C compiler")
class TestFeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.exe = os.path.join(cls.dir, "zedmd_feed")
        subprocess.check_call([shutil.which("cc") or "gcc", "-O2", "-Wall", "-Werror", "-o", cls.exe, SRC])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir)

    def setUp(self):
        self.master, slave = pty.openpty()
        tty.setraw(self.master)
        self.port = os.ttyname(slave)
        self.slave = slave
        self.writes = []

    def tearDown(self):
        os.close(self.master)
        os.close(self.slave)

    def serve(self, until, seconds=5):
        """The firmware: answers the handshake and acks every write-sized block; returns when `until()` holds."""
        buf, end = b"", time.time() + seconds
        while time.time() < end and not until():
            if select.select([self.master], [], [], 0.05)[0]:
                buf += os.read(self.master, 4096)
            while len(buf) >= 64:
                block, buf = buf[:64], buf[64:]
                self.writes.append(block)
                if block[10] == z.HANDSHAKE and block[:5] == z.FRAME:
                    r = bytearray(64)
                    r[:4] = b"ZeDM"
                    r[4:8] = bytes((W, 0, H, 0))
                    r[8:11] = bytes((5, 1, 2))
                    r[11:13] = bytes((64, 0))
                    r[57] = ord("R")
                    os.write(self.master, bytes(r))
                else:
                    os.write(self.master, z.CTRL + b"A")

    def test_frames_match_the_python_platform(self):
        p = subprocess.Popen([self.exe, "--port", self.port], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            a = frame([(9, 5, (9, 8, 7)), (100, 30, (255, 255, 255))])
            self.serve(lambda: len(self.writes) >= 1, 3)                        # the handshake
            p.stdin.write(a)
            p.stdin.flush()
            want = b"".join(wire(pk) for pk in z.zone_packets(a, None, W, H))
            self.serve(lambda: len(b"".join(self.writes[1:])) >= len(want), 5)
            self.assertEqual(want, b"".join(self.writes[1:]))
            b = frame([(9, 5, (9, 8, 7)), (100, 30, (255, 0, 0))])             # one zone changes
            n = len(self.writes)
            p.stdin.write(b)
            p.stdin.flush()
            changed = z.zone_packets(b, a, W, H)
            self.assertEqual(1, len(changed))
            self.serve(lambda: len(b"".join(self.writes[n:])) >= len(wire(changed[0])), 3)
            self.assertEqual(wire(changed[0]), b"".join(self.writes[n:]))
        finally:
            p.stdin.close()
            p.wait(5)

    def test_shades_are_drawn_in_the_colour(self):
        """--shades: a frame is 4096 shades 0-15, shown as --color scaled by the shade (the zones equal those of the RGB frame)."""
        p = subprocess.Popen([self.exe, "--port", self.port, "--shades", "--color", "2a6cff"], stdin=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        try:
            shades = bytearray(W * H)
            shades[5 * W + 9] = 15
            shades[30 * W + 100] = 7
            rgb = frame([(9, 5, (0x2a, 0x6c, 0xff)), (100, 30, (0x2a * 7 // 15, 0x6c * 7 // 15, 0xff * 7 // 15))])
            self.serve(lambda: len(self.writes) >= 1, 3)
            p.stdin.write(bytes(shades))
            p.stdin.flush()
            want = b"".join(wire(pk) for pk in z.zone_packets(rgb, None, W, H))
            self.serve(lambda: len(b"".join(self.writes[1:])) >= len(want), 5)
            self.assertEqual(want, b"".join(self.writes[1:]))
        finally:
            p.stdin.close()
            p.wait(5)

    def test_serum_needs_shades_and_a_build_with_serum(self):
        r = subprocess.run([self.exe, "--port", "/dev/null", "--serum", "x", "--rom", "y"], stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=10)
        self.assertEqual(1, r.returncode)                       # needs --shades
        r = subprocess.run([self.exe, "--port", "/dev/null", "--shades", "--serum", "x", "--rom", "y"],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
        self.assertEqual(1, r.returncode)                       # built without Serum
        self.assertIn(b"without Serum", r.stderr)

    def test_no_zedmd_exits_2(self):
        r = subprocess.run([self.exe, "--port", "/dev/null"], stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
        self.assertEqual(2, r.returncode)


if __name__ == "__main__":
    unittest.main()
