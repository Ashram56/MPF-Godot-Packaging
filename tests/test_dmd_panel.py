import os
import shutil
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




class FakeSysfs(unittest.TestCase):
    """A fake sysfs with symlinked devices (as /sys has them), and a ZeDMD on a pty."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    def usb(self, name, vid, pid, tty=None):
        dev = os.path.join(self.root, "devices", name)
        os.makedirs(os.path.join(dev, "1-1:1.0"))
        for f, v in (("idVendor", vid), ("idProduct", pid)):
            with open(os.path.join(dev, f), "w") as fh:
                fh.write(v + "\n")
        os.makedirs(os.path.join(self.root, "bus", "usb", "devices"), exist_ok=True)
        os.symlink(dev, os.path.join(self.root, "bus", "usb", "devices", name))
        if tty:
            os.makedirs(os.path.join(self.root, "class", "tty", tty), exist_ok=True)
            os.symlink(os.path.join(dev, "1-1:1.0"), os.path.join(self.root, "class", "tty", tty, "device"))

    def test_pin2dmd_by_usb_id(self):
        self.usb("1-1", "0314", "e457")
        self.assertEqual(dmd_panel.find(self.root), "pin2dmd")

    def test_zedmd_ports_by_usb_id_and_nothing_else(self):
        self.usb("1-1", "1a86", "7523", "ttyUSB0")
        self.usb("1-2", "303a", "1001", "ttyACM0")
        self.usb("1-3", "0403", "6010", "ttyUSB1")          # an FTDI (a P-ROC): not a ZeDMD
        self.assertEqual(dmd_panel.serial_ports(self.root), [("/dev/ttyACM0", 115200), ("/dev/ttyUSB0", 921600)])
        self.assertEqual(dmd_panel.find(os.path.join(self.root, "none")), "")

    @unittest.skipUnless(hasattr(os, "openpty"), "needs a pty")
    def test_handshake_on_a_pty(self):
        import threading
        import tty
        master, slave = os.openpty()
        tty.setraw(master)
        name = os.ttyname(slave)

        def zedmd(answer):
            got = b""
            while len(got) < 64:
                got += os.read(master, 64 - len(got))
            if got[:14] == dmd_panel.HANDSHAKE:
                os.write(master, answer)

        good = b"ZeDM" + bytes((128, 0, 32, 0)) + bytes(49) + b"R" + bytes(6)
        for answer, expect in ((good, True), (bytes(64), False)):
            t = threading.Thread(target=zedmd, args=(answer,), daemon=True)
            t.start()
            self.assertEqual(dmd_panel.zedmd_answers(name, 921600, timeout=1.5), expect)
            t.join(2)
        os.close(master)
        os.close(slave)



if __name__ == "__main__":
    unittest.main()
