import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common", "netconfig"))
os.environ.setdefault("MPF_STATE_DIR", tempfile.mkdtemp())
import mpf_monitor as M  # noqa: E402


class Scenarios(unittest.TestCase):
    def setUp(self):
        M.SCENARIOS = tempfile.mkdtemp()

    def test_save_list_read_delete(self):
        name = M.save_scenario("my-game", "first try!", [[0.5, "s_b", "off"], [0.1, "s_a", "on"]])
        self.assertEqual(name, "first try_")
        self.assertEqual(M.scenarios("my-game"), [{"name": "first try_", "events": 2, "seconds": 0.5}])
        self.assertEqual(M.read_scenario("my-game", "first try_")[0], [0.1, "s_a", "on"])    # time order
        self.assertEqual(M.scenarios("other"), [])
        M.delete_scenario("my-game", name)
        with self.assertRaises(ValueError):
            M.read_scenario("my-game", name)

    def test_refuses_bad_input(self):
        for bad in ([], "x", [[0, "s", "explode"]], [[-1, "s", "on"]], [["a", "s", "on"]], [[0, "", "on"]]):
            with self.assertRaises(ValueError):
                M.save_scenario("g", "n", bad)
        with self.assertRaises(ValueError):
            M.save_scenario("g", "  ", [[0, "s", "on"]])
        with self.assertRaises(ValueError):
            M.save_scenario("..", "n", [[0, "s", "on"]])
        n = M.save_scenario("g", "../../x", [[0, "s", "on"]])           # a name cannot leave the folder
        self.assertNotIn("/", n)

    def test_player_keeps_timing_skips_unknown_switch_and_stops(self):
        got = []

        def send(n, d):
            if n == "nope":
                raise ValueError("unknown switch")
            got.append((n, d, round(time.monotonic() - t0, 1)))
        p = M.Player(send)
        t0 = time.monotonic()
        p.start("x", [[0.0, "a", "on"], [0.2, "nope", "on"], [0.3, "a", "off"]])
        with self.assertRaises(ValueError):
            p.start("y", [[0, "a", "on"]])
        p.thread.join(3)
        self.assertEqual([g[:2] for g in got], [("a", "on"), ("a", "off")])
        self.assertAlmostEqual(got[1][2], 0.3, delta=0.15)
        self.assertEqual(p.status()["done"], 3)
        p.start("z", [[5, "a", "on"]])
        p.stop()
        p.thread.join(2)
        self.assertFalse(p.running())
        self.assertEqual(len(got), 2)


if __name__ == "__main__":
    unittest.main()
