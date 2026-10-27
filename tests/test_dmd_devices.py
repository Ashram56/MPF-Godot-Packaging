"""The RGB LED DMD pieces (platforms/dmd_devices.md): the MPF overlays parse, name what exists, and match the
Godot add-on's frame format."""
import importlib
import os
import re
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples", "dmd_devices")
ADDON = os.path.join(ROOT, "addons", "dmd_out", "dmd_out.gd")


def overlay(name):
    with open(os.path.join(EXAMPLES, name), encoding="utf-8") as f:
        text = f.read()
    assert text.startswith("#config_version=6"), name
    return yaml.safe_load(text)


class TestOverlays(unittest.TestCase):
    def test_pin2dmd(self):
        c = overlay("pin2dmd.yaml")
        self.assertEqual("pin2dmd", c["hardware"]["rgb_dmd"])
        self.assertEqual("128x32", c["pin2dmd"]["resolution"])
        self.assertEqual(["default"], list(c["rgb_dmds"]))          # the only name MPF's platform accepts
        self.assertEqual("virtual", c["dmds"]["dmd"]["platform"])

    def test_zedmd_platform_exists(self):
        c = overlay("zedmd.yaml")
        path = c["mpf"]["platforms"]["zedmd_native"]
        module, cls = path.rsplit(".", 1)
        self.assertTrue(hasattr(importlib.import_module(module), cls), path)
        self.assertEqual("zedmd_native", c["hardware"]["rgb_dmd"])
        self.assertEqual((128, 32), (c["zedmd"]["width"], c["zedmd"]["height"]))

    def test_feed(self):
        self.assertEqual({"dmds": {"dmd": {"platform": "virtual"}}}, overlay("zedmd_feed.yaml"))


class TestAddon(unittest.TestCase):
    def test_frame_format(self):
        with open(ADDON, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("const WIDTH := 128", src)
        self.assertIn("const HEIGHT := 32", src)
        self.assertIn('send_bytes("rgb_dmd_frame", frame, {"name": "default"})', src)
        for arg in ("--pin2dmd", "--zedmd", "--zedmd-feed="):
            self.assertIn(arg, src)
        self.assertTrue(re.search(r'DEFAULT_COLOR := "#[0-9a-f]{6}"', src))


if __name__ == "__main__":
    unittest.main()
