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


class Replay(unittest.TestCase):
    def test_replay_tool_against_a_fake_bcp_server(self):
        import json
        import socket
        import subprocess
        import threading
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        got = []

        def serve():
            c, _ = srv.accept()
            buf = b""
            while True:
                d = c.recv(4096)
                if not d:
                    break
                buf += d
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.decode()
                    if line.startswith("service"):
                        c.sendall(("list_switches?json=" + json.dumps({"switches": [["s_a", "A", "1", "b", 0], ["s_b", "B", "2", "b", 0]]}) + "\n").encode())
                    else:
                        got.append(line)
        threading.Thread(target=serve, daemon=True).start()
        path = os.path.join(tempfile.mkdtemp(), "s.json")
        json.dump({"format": 1, "events": [[0, "s_a", "on"], [0.1, "s_a", "off"], [0.2, "s_b", "tap"]]}, open(path, "w"))
        tool = os.path.join(os.path.dirname(__file__), "..", "common", "games", "replay_scenario.py")
        r = subprocess.run([sys.executable, tool, path, "--port", str(srv.getsockname()[1])], capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(got, ["switch?name=s_a&state=int:1", "switch?name=s_a&state=int:0", "switch?name=s_b&state=int:1", "switch?name=s_b&state=int:0"])
        json.dump({"format": 1, "events": [[0, "s_zz", "on"]]}, open(path, "w"))
        srv2 = socket.socket()
        srv2.bind(("127.0.0.1", 0))
        srv2.listen(1)

        def serve2():
            c, _ = srv2.accept()
            c.recv(4096)
            c.sendall(("list_switches?json=" + json.dumps({"switches": [["s_a", "A", "1", "b", 0]]}) + "\n").encode())
            time.sleep(1)
        threading.Thread(target=serve2, daemon=True).start()
        r = subprocess.run([sys.executable, tool, path, "--port", str(srv2.getsockname()[1])], capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 1)
        self.assertIn("s_zz", r.stderr)
