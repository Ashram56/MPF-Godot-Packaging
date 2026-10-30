import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common", "games"))
import webdav_tidy as W  # noqa: E402


class Plan(unittest.TestCase):
    def test_loose_files_go_to_a_folder_by_id_or_packs(self):
        manifest = [{"id": "alpha", "file": "pkg-1.tar.xz"}]
        moves, left = W.plan(["pkg-1.tar.xz", "pkg-1.tar.xz.sha256", "beta-2.1-linux-arm64.tar.xz", "beta@abc1234.tar.xz",
                              "Cool Pack.zip", "weird.tar.xz", "notes.txt", "mpf-games.json"], manifest)
        self.assertEqual(dict(moves), {"pkg-1.tar.xz": "alpha", "pkg-1.tar.xz.sha256": "alpha", "beta-2.1-linux-arm64.tar.xz": "beta",
                                       "beta@abc1234.tar.xz": "beta", "Cool Pack.zip": "PuP Packs"})
        self.assertEqual(left, ["weird.tar.xz"])


if __name__ == "__main__":
    unittest.main()
