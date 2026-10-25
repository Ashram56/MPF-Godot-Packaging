"""mpf_godot/zedmd_native.py: the ZeDMD serial protocol against a fake device."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from mpf_godot import zedmd_native as z

WIDTH, HEIGHT = 128, 32


class FakeZeDmd:
    """What the firmware answers: the handshake block and 'ZeDMD' 'A' per write; keeps every write."""

    def __init__(self, write_size=64, bad_ack=False):
        self.writes, self.replies, self.write_size, self.bad_ack = [], b"", write_size, bad_ack
        self.closed = False

    def reset_input_buffer(self):
        self.replies = b""

    def write(self, data):
        self.writes.append(bytes(data))
        if bytes(data)[:5] == z.FRAME and bytes(data)[10] == z.HANDSHAKE:
            r = bytearray(64)
            r[4:8] = bytes((WIDTH, 0, HEIGHT, 0))
            r[:4] = b"ZeDM"
            r[8:11] = bytes((5, 1, 2))
            r[11:13] = bytes((self.write_size & 255, self.write_size >> 8))
            r[57] = ord("R")
            r[:4] = b"ZeDM"
            r[4:8] = bytes((WIDTH, 0, HEIGHT, 0))
            self.replies += bytes(r)
        else:
            self.replies += z.CTRL + (b"F" if self.bad_ack else b"A")

    def read(self, n):
        out, self.replies = self.replies[:n], self.replies[n:]
        return out

    def close(self):
        self.closed = True


def rgb(color=(0, 0, 0)):
    return bytes(color) * (WIDTH * HEIGHT)


class TestProtocol(unittest.TestCase):
    def device(self, fake):
        return z.ZedmdNativeDevice(WIDTH, HEIGHT, opener=lambda: fake)

    def wait(self, fake, count):
        end = time.time() + 3
        while len(fake.writes) < count and time.time() < end:
            time.sleep(0.01)

    def test_control_block_has_big_endian_size(self):
        self.assertEqual(b"ZeDMD" + bytes((4, 1, 2, 0)) + bytes(258), z.control(4, bytes(258)))

    def test_zones_of_a_black_frame_with_one_dot(self):
        frame = bytearray(rgb())
        frame[(5 * WIDTH + 9) * 3:(5 * WIDTH + 9) * 3 + 3] = bytes((9, 8, 7))     # zone column 1, zone row 1
        packets = z.zone_packets(bytes(frame), None, WIDTH, HEIGHT)
        self.assertEqual(sum(len(p) for p in packets), 127 + 1 + 96)             # 127 black zones + the lit one
        self.assertTrue(all(len(p) <= z.ZONES_BYTE_LIMIT for p in packets))
        self.assertIn(bytes((17,)), b"".join(packets))                            # the lit zone, index 17, 96 bytes

    def test_only_changed_zones_follow(self):
        a, b = bytearray(rgb()), bytearray(rgb())
        b[0:3] = bytes((1, 1, 1))
        packets = z.zone_packets(bytes(b), bytes(a), WIDTH, HEIGHT)
        self.assertEqual([bytes((0,)) + bytes((1, 1, 1)) + bytes(93)], packets)

    def test_handshake_then_frame_then_clear(self):
        fake = FakeZeDmd()
        dev = self.device(fake)
        try:
            dev.update(rgb((255, 0, 0)))
            self.wait(fake, 6)
            self.assertEqual(z.FRAME + z.control(z.HANDSHAKE), fake.writes[0][:14])
            body = b"".join(w for w in fake.writes[1:] if w[10] != z.BRIGHTNESS)
            self.assertEqual(z.FRAME + z.CTRL + bytes((z.ZONES_RGB888,)), body[:11])
            self.assertIn(z.control(z.RENDER), body)
            self.assertTrue(all(len(w) == 64 for w in fake.writes))
            dev.update(rgb())
            self.wait(fake, 40)
            time.sleep(0.2)
            self.assertIn(z.FRAME + z.control(z.CLEAR), fake.writes[-1] + b"")
        finally:
            dev.stop()

    def test_negative_ack_resends_everything(self):
        fake = FakeZeDmd(bad_ack=True)
        dev = self.device(fake)
        try:
            dev.update(rgb((1, 2, 3)))
            time.sleep(0.5)
            self.assertIsNone(dev._previous)
        finally:
            dev.stop()


if __name__ == "__main__":
    unittest.main()
