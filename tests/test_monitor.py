"""Switch monitor and saved logs (common/netconfig/mpf_monitor.py), against a fake BCP server."""
import json
import os
import socket
import tempfile
import threading
import time
import unittest

from tests import test_games as TG

C, G = TG.C, TG.G
import mpf_monitor as M  # noqa: E402


class FakeBcp:
    """Speaks the lines MPF's BCP server speaks for the three commands the monitor uses."""

    def __init__(self):
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.got = []
        self.conn = None
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        try:
            self.conn, _ = self.srv.accept()
        except OSError:
            return
        buf = b""
        while True:
            try:
                d = self.conn.recv(4096)
            except OSError:
                return
            if not d:
                return
            buf += d
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self.got.append(line.decode())
                if line.startswith(b"service?subcommand=list_switches"):
                    rows = [["s_start", "Start", "7", "virtual", 0], ["s_trough1", "", "1", "virtual", 1]]
                    self.conn.sendall(("list_switches?json=" + json.dumps({"switches": rows}) + "\n").encode())

    def send(self, line):
        self.conn.sendall((line + "\n").encode())

    def close(self):
        self.srv.close()
        if self.conn:
            self.conn.close()


def wait(cond, secs=3):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


class MonitorTest(unittest.TestCase):
    def setUp(self):
        self.bcp = FakeBcp()
        self.mon = M.Monitor()
        self.saved = (M.HOST, M.PORT, M.SAVED, M.MON)
        M.HOST, M.PORT = "127.0.0.1", self.bcp.port
        self.tmp = tempfile.mkdtemp()
        M.SAVED = os.path.join(self.tmp, "logs")
        M.MON = self.mon

    def tearDown(self):
        M.HOST, M.PORT, M.SAVED, M.MON = self.saved
        self.mon.last_use = 0
        self.bcp.close()

    def test_codec(self):
        self.assertEqual(M.encode("switch", name="s a", state=-1), "switch?name=s%20a&state=int:-1")
        self.assertEqual(M.decode("switch?name=s%20a&state=int:1"), ("switch", {"name": "s a", "state": 1}))
        self.assertEqual(M.decode('list_switches?json={"switches": [["a", "", "1", "b", 0]]}')[1]["switches"][0][0], "a")

    def test_list_follow_and_set(self):
        self.mon.snapshot()
        self.assertTrue(wait(lambda: len(self.mon.snapshot()["switches"]) == 2))
        snap = self.mon.snapshot()
        self.assertTrue(snap["connected"])
        self.assertEqual([(s["name"], s["state"]) for s in snap["switches"]], [("s_start", 0), ("s_trough1", 1)])
        self.assertIn("monitor_start?category=switches", self.bcp.got)
        self.bcp.send("switch?name=s_start&state=int:1")
        self.assertTrue(wait(lambda: self.mon.snapshot()["switches"][0]["state"] == 1))
        self.assertEqual(self.mon.snapshot()["log"][-1][1:], ["s_start", 1])
        self.mon.set_switch("s_start", "toggle")
        self.assertTrue(wait(lambda: "switch?name=s_start&state=int:-1" in self.bcp.got))
        self.mon.set_switch("s_start", "tap")
        self.assertTrue(wait(lambda: "switch?name=s_start&state=int:0" in self.bcp.got))
        with self.assertRaises(ValueError):
            self.mon.set_switch("nope", "on")
        with self.assertRaises(ValueError):
            self.mon.set_switch("s_start", "explode")

    def test_game_not_running(self):
        M.PORT = 1
        snap = self.mon.snapshot()
        self.assertTrue(wait(lambda: self.mon.snapshot()["error"]))
        self.assertFalse(snap["connected"])
        with self.assertRaises(ValueError):
            self.mon.set_switch("x", "on")

    def test_save_log(self):
        name = M.save_log(None)
        self.assertIn(name, M.saved_logs())
        text = M.read_saved(name)
        self.assertIn("MPF log snapshot", text)
        self.assertIsNone(M.read_saved("../../etc/passwd"))
        for i in range(M.KEEP_LOGS + 3):
            open(os.path.join(M.SAVED, f"2000010{i % 10}-{i:06d}-x.log.txt"), "w").close()
        M.save_log(None)
        self.assertEqual(len(M.saved_logs()), M.KEEP_LOGS)


if __name__ == "__main__":
    unittest.main()
