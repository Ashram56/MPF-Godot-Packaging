"""The import walk of a format 2 bundle (common/netconfig/mpf_bundlecheck.py): a folder of modules without __init__.py is a package."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common", "netconfig"))
import mpf_bundlecheck as BC  # noqa: E402


class NamespacePackage(unittest.TestCase):
    def test_import_of_a_folder_without_init_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "game", "tf", "features"))
            open(os.path.join(d, "game", "tf", "os_layer.py"), "w").write("X = 1\n")
            open(os.path.join(d, "game", "tf", "features", "wiz.py"), "w").write("import tf\nfrom tf import os_layer\n")
            starts = BC.python_files(os.path.join(d, "game"))
            self.assertEqual(BC.problems(d, python=None, starts=starts), [])

    def test_missing_module_still_reported_with_source(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as src:
            os.makedirs(os.path.join(src, "game", "tf"))
            open(os.path.join(src, "game", "tf", "x.py"), "w").write("")
            os.makedirs(os.path.join(d, "game"))
            open(os.path.join(d, "game", "m.py"), "w").write("import tf\n")
            bad = BC.problems(d, python=None, starts=[os.path.join(d, "game", "m.py")], source=src)
            self.assertTrue(any("'tf'" in b for b in bad))


if __name__ == "__main__":
    unittest.main()
