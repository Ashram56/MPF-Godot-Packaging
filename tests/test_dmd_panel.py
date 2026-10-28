import os
import tempfile
import unittest

from mpf_godot import dmd_panel


def usb(root, name, vid, pid):
    d = os.path.join(root, "bus", "usb", "devices", name)
    os.makedirs(d)
    open(os.path.join(d, "idVendor"), "w").write(vid + "\n")
    open(os.path.join(d, "idProduct"), "w").write(pid + "\n")


class Detect(unittest.TestCase):
    def test_nothing(self):
        with tempfile.TemporaryDirectory() as r:
            self.assertEqual(dmd_panel.find(r), "")

    def test_pin2dmd_by_usb_id(self):
        with tempfile.TemporaryDirectory() as r:
            usb(r, "1-1", "0314", "e457")
            self.assertEqual(dmd_panel.find(r), "pin2dmd")

    def test_other_usb_devices_are_not_a_dmd(self):
        with tempfile.TemporaryDirectory() as r:
            usb(r, "1-2", "1a86", "7523")        # a serial bridge nothing answers on
            self.assertEqual(dmd_panel.find(r), "")


if __name__ == "__main__":
    unittest.main()
