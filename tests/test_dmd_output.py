"""The DMD output setting and the Serum library: what the launcher passes to a game, per output and per game."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_games import Base  # noqa: E402
import mpf_dmd as D  # noqa: E402


class DmdOutput(Base):
    def setUp(self):
        super().setUp()
        self.serum = D.SERUM
        D.SERUM = os.path.join(self.t.name, "serum")
        self.bridge = D.bridge_dir
        self.bd = os.path.join(self.t.name, "bridge")
        os.makedirs(self.bd)
        for n in ("dmd_bridge", "libserum64.so"):
            open(os.path.join(self.bd, n), "w").close()
        D.bridge_dir = lambda: self.bd

    def tearDown(self):
        D.SERUM, D.bridge_dir = self.serum, self.bridge
        super().tearDown()

    def upload(self, name):
        src = os.path.join(self.t.name, name)
        open(src, "wb").write(b"x")
        return D.store_serum(src, name)

    def test_lcd_has_no_args(self):
        D.set_output("lcd")
        self.assertEqual(D.merge_args(["--a"], "tron", {}), ["--a"])

    def test_auto_follows_detection(self):
        self.assertEqual(D.resolve(detected=""), "lcd")
        self.assertEqual(D.resolve(detected="zedmd"), "zedmd")
        self.assertEqual(D.plan("tron", {}, detected="pin2dmd"), (["--pin2dmd=#2a6cff"], []))

    def test_zedmd_mono_without_colourisation(self):
        D.set_output("zedmd", "#ff0000")
        pre, user = D.plan("tron", {"dmd": {"rom": "trn_174h"}})
        self.assertEqual(pre, ["--zedmd=#ff0000"])
        self.assertEqual(user, ["--zedmd-shades", "--zedmd-feed=" + os.path.join(self.bd, "dmd_bridge")])

    def test_zedmd_serum_default_and_per_game(self):
        D.set_output("zedmd")
        self.assertEqual(self.upload("trn_174h.cROMc"), "trn_174h")
        self.upload("other.cRZ")
        b = {"dmd": {"rom": "trn_174h"}}
        args = D.merge_args(["--board"], "tron", b)
        self.assertEqual(args[:3], ["--board", "--zedmd=#2a6cff", "--"])
        self.assertIn("--zedmd-feed-arg=trn_174h", args)
        self.assertIn("--zedmd-feed-arg=" + D.SERUM, args)
        D.assign_serum("tron", "other")
        self.assertIn("--zedmd-feed-arg=other", D.merge_args([], "tron", b))
        D.assign_serum("tron", "none")
        self.assertFalse(any("--rom" in a for a in D.merge_args([], "tron", b)))
        D.assign_serum("tron", "")
        self.assertEqual(D.chosen_serum("tron", b), "trn_174h")
        self.assertEqual(D.chosen_serum("other_game", {}), "")

    def test_board_args_with_godot_section(self):
        D.set_output("zedmd")
        args = D.merge_args(["--x", "--", "--", "--y"], "g", {})
        self.assertEqual(args[:2], ["--x", "--zedmd=#2a6cff"])
        self.assertEqual(args.count("--"), 2)
        self.assertIn("--y", args)

    def test_no_bridge_falls_back_to_screen(self):
        D.bridge_dir = lambda: None
        D.set_output("zedmd")
        self.assertEqual(D.merge_args([], "g", {}), [])

    def test_upload_rules(self):
        with self.assertRaises(ValueError):
            self.upload("bad.zip")
        with self.assertRaises(ValueError):
            D.assign_serum("g", "missing")
        self.upload("a.cROMc")
        D.assign_serum("g", "a")
        D.delete_serum("a")
        self.assertEqual(D.library(), [])
        self.assertEqual(D.load()["serum"], {})


if __name__ == "__main__":
    unittest.main()
