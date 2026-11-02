"""mpf_bundlecheck: what it must not refuse (a namespace package) and must still refuse (a module left out)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common", "netconfig"))
import mpf_bundlecheck as BC  # noqa: E402


def make(root, files):
    for rel, text in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)


class NamespacePackage(unittest.TestCase):
    def test_folder_without_init_is_found(self):
        """game/pkg/ has no __init__.py but game code imports it (the game folder is on sys.path at run time)."""
        with tempfile.TemporaryDirectory() as d:
            make(d, {"game/pkg/a.py": "from pkg.sub import b\n", "game/pkg/sub/__init__.py": "", "game/pkg/sub/b.py": "import os\n"})
            self.assertEqual([], BC.problems(d, None, {}, starts=BC.python_files(os.path.join(d, "game"))))
            self.assertIn("pkg", BC.index(d))

    def test_missing_module_still_reported_from_source(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as src:
            make(d, {"game/a.py": "import gone\n"})
            make(src, {"gone.py": ""})
            bad = BC.problems(d, None, {}, source=src, starts=BC.python_files(os.path.join(d, "game")))
            self.assertEqual(1, len(bad))
            self.assertIn("gone", bad[0])


if __name__ == "__main__":
    unittest.main()
