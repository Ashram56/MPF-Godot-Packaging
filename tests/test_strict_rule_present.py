"""The owner's STRICT RULE (2026-11-24) must stay in the files agents read first."""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER = "STRICT RULE: DECOMPILE EVERYTHING"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class StrictRulePresent(unittest.TestCase):
    def test_claude_md_carries_the_rule(self):
        for m in (MARKER, "Never end a turn by announcing", "progress report at least every 15 minutes"):
            self.assertIn(m, read("CLAUDE.md"))

    def test_agent_files_carry_the_gate(self):
        for rel in ("agents/README.md", "agents/recreation.md"):
            self.assertIn(MARKER, read(rel), rel)


if __name__ == "__main__":
    unittest.main()
