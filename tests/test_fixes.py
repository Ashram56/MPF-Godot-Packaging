"""Every fix document follows fixes/TEMPLATE.md, the index is current, and relative links in the docs resolve."""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "fixes"))
import make_index  # noqa: E402


def docs():
    for folder, _name, _tracker in make_index.COMPONENTS:
        d = os.path.join(ROOT, "fixes", folder)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".md") and f != "README.md":
                    yield os.path.join(d, f)


class TestFixes(unittest.TestCase):

    def test_every_doc_follows_the_template(self):
        for path in docs():
            with self.subTest(doc=os.path.relpath(path, ROOT)):
                self.assertEqual([], make_index.problems(path))

    def test_index_is_current(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "fixes", "make_index.py"), "--check"])
        self.assertEqual(0, r.returncode, "run python fixes/make_index.py")

    def test_relative_links_resolve(self):
        broken = []
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", ".venv", "toolchain", "node_modules")]
            for f in files:
                if not f.endswith(".md"):
                    continue
                path = os.path.join(base, f)
                with open(path, encoding="utf-8") as fh:
                    text = re.sub(r"```.*?```", "", fh.read(), flags=re.S)
                for link in re.findall(r"\]\(([^)\s]+)\)", text):
                    if re.match(r"[a-z]+:|#", link):
                        continue
                    target = os.path.normpath(os.path.join(base, link.split("#")[0]))
                    if not os.path.exists(target):
                        broken.append("{} -> {}".format(os.path.relpath(path, ROOT), link))
        self.assertEqual([], broken)


if __name__ == "__main__":
    unittest.main()
