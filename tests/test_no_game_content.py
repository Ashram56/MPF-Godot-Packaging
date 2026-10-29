"""This repository is game agnostic: it takes a game package that the game provides and builds a bundle from it. No game's name,
recipe, bundle spec or PuP Pack path may be in it. Where a name is allowed: `fixes/` and `platforms/` (the provenance of a finding,
"found on game X"), this test, and the two places that carry a legacy patch tag."""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN = re.compile(r"transformers|tron[ -_]?legacy|\btf_?180\b|\btf_pup\b", re.I)
FORBIDDEN_WORD = re.compile(r"\btron\b", re.I)
ALLOWED_PREFIXES = ("fixes/", "platforms/", "tests/test_no_game_content.py")
LEGACY_TAG = {"mpf_godot/gmc_patch.py", "tests/test_toolchain.py"}      # older GMC copies carry "# tron patch"; the tag must stay readable
BINARY = (".so", ".dll", ".dylib", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".xz", ".ctex", ".mp4", ".patch")


def tracked():
    out = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True)
    if out.returncode == 0 and out.stdout.strip():
        return out.stdout.split("\n")
    return [os.path.relpath(os.path.join(b, n), ROOT).replace(os.sep, "/") for b, d, ns in os.walk(ROOT) if ".git" not in b for n in ns]


class NoGameContent(unittest.TestCase):
    def test_no_recipes_or_specs_of_a_game(self):
        files = [f for f in tracked() if f and os.path.exists(os.path.join(ROOT, f))]
        bad = [f for f in files if f.startswith("common/games/recipes") or re.search(r"(^|/)recipes/", f)]
        self.assertEqual([], bad, "a game's recipe or spec belongs in the game's repository (CONTRIBUTING.md)")

    def test_no_game_names(self):
        bad = []
        for f in tracked():
            if not f or f.startswith(ALLOWED_PREFIXES) or f.endswith(BINARY) or not os.path.isfile(os.path.join(ROOT, f)):
                continue
            with open(os.path.join(ROOT, f), encoding="utf-8", errors="ignore") as fh:
                for n, line in enumerate(fh, 1):
                    if FORBIDDEN.search(line) or (FORBIDDEN_WORD.search(line) and f not in LEGACY_TAG):
                        bad.append(f"{f}:{n}: {line.strip()[:80]}")
        self.assertEqual([], bad[:20], "game names do not belong here: use a neutral example, or put the game's files in its repository")


if __name__ == "__main__":
    unittest.main()
