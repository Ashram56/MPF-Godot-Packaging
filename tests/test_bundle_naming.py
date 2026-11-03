import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mpf_godot import bundle as B


class Naming(unittest.TestCase):
    def test_number_and_label(self):
        self.assertEqual(B.release({}, "1.4.0", "serum-zedmd"), ("1.4.0", "serum-zedmd", "1.4.0-serum-zedmd"))

    def test_spec_defaults(self):
        self.assertEqual(B.release({"version": "2.0", "label": "base"}, None, None)[2], "2.0-base")

    def test_hash_refused(self):
        with self.assertRaises(SystemExit):
            B.release({}, "2026.11.02-ad25031", "x")
        with self.assertRaises(SystemExit):
            B.release({}, "1.0.0", "Bad Label")

    def test_manifest_keeps_commit(self):
        m = B.manifest(os.getcwd(), {"id": "g"}, "1.0.0-base", "all", "1.0.0", "base")
        self.assertEqual((m["semver"], m["label"], m["version"]), ("1.0.0", "base", "1.0.0-base"))
        self.assertIn("game_commit_short", m["source"])


if __name__ == "__main__":
    unittest.main()
