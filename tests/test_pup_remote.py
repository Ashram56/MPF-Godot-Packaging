"""Remote PuP screens: PinUP Player's rules in Python (screen_rules.py), the game's server (pup_remote/server.py) and the
remote topper's agent (pup_remote/topper/topper.py), linked over the loopback with a fake mpv."""
import asyncio
import importlib.util
import json
import os
import random
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
from mpf_godot.pup_remote import server as remote, screen_rules   # noqa: E402

_spec = importlib.util.spec_from_file_location("topper", os.path.join(ROOT, "mpf_godot", "pup_remote", "topper", "topper.py"))
topper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(topper)

FILES = ["Background - Topper/Title.mp4", "TopperModes/Hero.mp4", "TopperModes/Spark.mp4",
         "TopperEvents/Jackpot2.mp4", "TopperEvents/Jackpot10.mp4", "TopperEvents/Jackpot1.mp4"]


class Output:
    def __init__(self):
        self.log, self.visible = [], None

    def start(self, key, loop, volume):
        self.log.append(("start", key, loop))

    def stop(self):
        self.log.append(("stop",))

    def set_visible(self, visible):
        self.visible = visible


class Timers:
    def __init__(self):
        self.pending = []

    def __call__(self, seconds, callback):
        self.pending.append((seconds, callback))

    def fire(self):
        pending, self.pending = self.pending, []
        for _s, cb in pending:
            cb()


def library(playlists=None):
    return screen_rules.Library({k: "/media/" + k for k in FILES}, playlists, rng=random.Random(1))


class TestScreenRules(unittest.TestCase):

    def screen(self, popup=False, bg=("Background - Topper", "Title.mp4")):
        self.out, self.timers = Output(), Timers()
        return screen_rules.Screen(13, library(), self.out, self.timers, popup=popup, bg_playlist=bg[0],
                                   bg_file=bg[1])

    def test_background_then_priority(self):
        s = self.screen()
        s.start_background()
        self.assertEqual(("start", "Background - Topper/Title.mp4", True), self.out.log[-1])
        s.command({"playlist": "TopperModes", "file": "Hero", "priority": 5, "mode": "Loop"})
        self.assertEqual(("start", "TopperModes/Hero.mp4", True), self.out.log[-1])
        s.command({"playlist": "TopperModes", "file": "Spark.mp4", "priority": 4})           # lower: dropped
        self.assertEqual("TopperModes/Hero.mp4", s.key)
        s.command({"playlist": "TopperModes", "file": "Spark", "priority": 5, "mode": "SkipSamePrty"})
        self.assertEqual("TopperModes/Hero.mp4", s.key)
        s.command({"playlist": "TopperModes", "file": "hero", "mode": "StopFile"})          # the background back
        self.assertEqual(("start", "Background - Topper/Title.mp4", True), self.out.log[-1])

    def test_video_end_and_length(self):
        s = self.screen()
        s.start_background()
        s.command({"playlist": "TopperModes", "file": "Spark", "priority": 1})
        self.assertFalse(s.loop)
        s.finished()
        self.assertEqual("Background - Topper/Title.mp4", s.key)
        s.command({"playlist": "TopperModes", "file": "Spark", "priority": 1, "length": 3})
        self.timers.fire()
        self.assertEqual("Background - Topper/Title.mp4", s.key)

    def test_stale_length_timer(self):
        s = self.screen()
        s.command({"playlist": "TopperModes", "file": "Spark", "priority": 1, "length": 3})
        s.command({"playlist": "TopperModes", "file": "Hero", "priority": 1, "mode": "Loop"})
        self.timers.fire()                                   # Spark's timer: Hero plays on
        self.assertEqual("TopperModes/Hero.mp4", s.key)

    def test_popup_hides(self):
        s = self.screen(popup=True, bg=("", ""))
        self.assertFalse(self.out.visible)
        s.command({"playlist": "TopperEvents", "priority": 1})
        self.assertTrue(self.out.visible)
        s.finished()
        self.assertFalse(self.out.visible)
        self.assertEqual(("stop",), self.out.log[-1])
        s.command({"playlist": "TopperEvents", "priority": 1, "mode": "StopPlayer"})
        self.assertFalse(self.out.visible)

    def test_set_bg(self):
        s = self.screen()
        s.command({"playlist": "TopperModes", "file": "Spark", "mode": "SetBG"})
        self.assertEqual(("start", "TopperModes/Spark.mp4", True), self.out.log[-1])

    def test_pick(self):
        lib = library({"topperevents": {"alpha_sort": True, "volume": 50}})
        firsts = [lib.pick("TopperEvents") for _ in range(4)]
        names = ["TopperEvents/Jackpot1.mp4", "TopperEvents/Jackpot2.mp4", "TopperEvents/Jackpot10.mp4"]
        start = names.index(firsts[0])
        self.assertEqual([names[(start + i) % 3] for i in range(4)], firsts)      # natural order, wraps
        self.assertEqual(0.5, lib.volume_of({"playlist": "TopperEvents"}))
        self.assertEqual(0.8, lib.volume_of({"playlist": "TopperEvents", "volume": 80}))
        lib = library()
        picks = [lib.pick("TopperModes") for _ in range(10)]
        self.assertTrue(all(a != b for a, b in zip(picks, picks[1:])))         # random, never twice in a row
        self.assertEqual("", lib.pick("Nothing"))
        self.assertEqual("", lib.pick("TopperModes", "missing.mp4"))


class FakeMpv:
    def __init__(self):
        self.plays, self.path, self.position, self.on_eof = [], "", 0.0, None

    def play(self, path, loop, volume, start=0.0):
        self.path = path
        self.plays.append((os.path.basename(path), loop, round(start, 1)))

    def clear(self):
        self.path = ""
        self.plays.append(None)


SCREENS = {13: {"playlist": "Background - Topper", "file": "Title.mp4", "active": "Show"},
           14: {"playlist": "", "file": "", "active": "ForcePopBack"}}


class TestDisplay(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.mpv = FakeMpv()
        self.display = topper.Display(self.mpv, library())
        server = remote.RemoteServer(SCREENS, {})
        self.welcome = server.welcome([13, 14])

    def tearDown(self):
        self.loop.close()

    def test_popup_over_underlay_then_resume(self):
        self.display.setup(self.welcome["screens"], {}, [13, 14])
        self.assertEqual([("Title.mp4", True, 0.0)], self.mpv.plays)
        self.mpv.position = 12.5
        self.display.command({"screen": 14, "playlist": "TopperEvents", "file": "Jackpot1", "priority": 1})
        self.assertEqual(("Jackpot1.mp4", False, 0.0), self.mpv.plays[-1])
        self.mpv.on_eof()                                    # the pop-up ends: the logo where it was
        self.assertEqual(("Title.mp4", True, 12.5), self.mpv.plays[-1])

    def test_rejoin_keeps_the_loop(self):
        self.display.setup(self.welcome["screens"], {}, [13, 14])
        self.display.setup(self.welcome["screens"], {}, [13, 14])
        self.assertEqual(1, len(self.mpv.plays))
        cmd = {"screen": 13, "playlist": "TopperModes", "file": "Hero", "priority": 2, "mode": "Loop"}
        self.display.setup(self.welcome["screens"], {}, [13, 14], [cmd])       # the game says Hero runs
        self.display.setup(self.welcome["screens"], {}, [13, 14], [cmd])
        self.assertEqual([("Title.mp4", True, 0.0), ("Hero.mp4", True, 0.0)], self.mpv.plays)

    def test_underlay_changes_under_popup(self):
        self.display.setup(self.welcome["screens"], {}, [13, 14])
        self.display.command({"screen": 14, "playlist": "TopperEvents", "file": "Jackpot1", "priority": 1})
        self.display.command({"screen": 13, "playlist": "TopperModes", "file": "Spark", "priority": 1,
                              "mode": "Loop"})
        self.assertEqual(("Jackpot1.mp4", False, 0.0), self.mpv.plays[-1])    # covered: nothing shown changes
        self.mpv.on_eof()
        self.assertEqual(("Spark.mp4", True, 0.0), self.mpv.plays[-1])


class TestServer(unittest.TestCase):

    def test_current_state(self):
        server = remote.RemoteServer(SCREENS, {})
        server.send({"screen": 13, "playlist": "TopperModes", "file": "Spark", "mode": "SetBG"})
        server.send({"screen": 13, "playlist": "TopperModes", "file": "Hero", "priority": 3, "mode": "Loop"})
        server.send({"screen": 13, "playlist": "TopperEvents", "priority": 1})           # lower: the loop goes on
        server.send({"screen": 14, "playlist": "TopperEvents", "priority": 9})
        self.assertEqual(["Spark", "Hero"], [c["file"] for c in server.current([13, 14])])
        server.send({"screen": 13, "playlist": "TopperModes", "file": "Spark.mp4", "mode": "StopFile"})
        self.assertEqual(2, len(server.current([13])))                                    # not the running loop
        server.send({"screen": 13, "playlist": "TopperModes", "file": "hero", "mode": "StopFile"})
        self.assertEqual(["Spark"], [c["file"] for c in server.current([13])])
        server.send({"screen": 13, "playlist": "TopperModes", "file": "Hero", "priority": 3, "mode": "Loop"})
        server.send({"screen": 13, "playlist": "TopperEvents", "priority": 3})            # replaces it
        self.assertEqual(["Spark"], [c["file"] for c in server.current([13])])
        welcome = server.welcome([13, 14])
        self.assertEqual({"bg_playlist": "Background - Topper", "bg_file": "Title.mp4", "popup": False},
                         welcome["screens"]["13"])
        self.assertTrue(welcome["screens"]["14"]["popup"])
        json.dumps(welcome)

    def test_link(self):
        """Discovery, welcome with the current state, live commands to the screens asked for, then the game gone."""
        async def scenario():
            server = remote.RemoteServer(SCREENS, {"topperevents": {"alpha_sort": True, "volume": 100}},
                                         game="trn_174h", host="127.0.0.1", port=0, ping_seconds=0.2)
            await server.start()
            found = await topper.discover(server.port, target="127.0.0.1")
            self.assertEqual(("127.0.0.1", server.port), found)
            server.send({"screen": 13, "playlist": "TopperModes", "file": "Hero", "priority": 3, "mode": "Loop"})
            mpv = FakeMpv()
            display = topper.Display(mpv, library())
            opts = topper.load_config(None, {"host": "127.0.0.1", "port": str(server.port), "timeout": "1"})
            link = asyncio.ensure_future(topper.session(opts, display, [13, 14]))
            for _ in range(50):
                await asyncio.sleep(0.02)
                if server.clients:
                    break
            self.assertEqual([("Hero.mp4", True, 0.0)], mpv.plays)
            self.assertTrue(display.library.playlists["topperevents"]["alpha_sort"])
            server.send({"screen": 14, "playlist": "TopperEvents", "file": "Jackpot2", "priority": 1})
            server.send({"screen": 2, "playlist": "Drain", "priority": 1})                # not a topper screen
            await asyncio.sleep(0.5)                                                      # pings keep it up
            self.assertEqual(("Jackpot2.mp4", False, 0.0), mpv.plays[-1])
            self.assertEqual(2, len(mpv.plays))
            server.close()
            self.assertTrue(await asyncio.wait_for(link, 3))
        asyncio.run(scenario())

    def test_nobody_answers(self):
        async def scenario():
            with socket_port() as port:
                self.assertIsNone(await topper.discover(port, timeout=0.2, target="127.0.0.1"))
        asyncio.run(scenario())


class socket_port:
    """A free UDP port nobody answers on."""
    def __enter__(self):
        import socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        return self.sock.getsockname()[1]

    def __exit__(self, *exc):
        self.sock.close()


class TestAgent(unittest.TestCase):

    def test_mpv_args(self):
        opts = topper.load_config(None, {})
        args = topper.Mpv(opts).args()
        for arg in ("--fullscreen", "--panscan=1.0", "--aid=no", "--hwdec=v4l2m2m-copy", "--video-align-y=0.000"):
            self.assertIn(arg, args)
        args = topper.Mpv(topper.load_config(None, {"window": "true", "audio": "true"})).args()
        self.assertIn("--geometry=960x281", args)
        self.assertNotIn("--fullscreen", args)
        self.assertNotIn("--aid=no", args)

    def test_example_config(self):
        opts = topper.load_config(os.path.join(ROOT, "mpf_godot", "pup_remote", "topper", "pup-topper.cfg"), {})
        self.assertEqual(set(topper.DEFAULTS), set(opts))

    def test_same_rules_file(self):
        # the installer copies mpf_godot/pup_remote/screen_rules.py next to the agent: one file, no copy in git
        self.assertFalse(os.path.exists(os.path.join(ROOT, "mpf_godot", "pup_remote", "topper", "screen_rules.py")))
        self.assertEqual(os.path.join(ROOT, "mpf_godot", "pup_remote", "screen_rules.py"), topper.screen_rules.__file__)

    def test_library_from_manifest(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "manifest.json"), "w") as f:
                json.dump({"files": {"TopperModes/Hero.mp4": {"out": "TopperModes/Hero.mp4"}}}, f)
            lib = topper.load_library(d)
            self.assertEqual(os.path.join(d, "TopperModes/Hero.mp4"), lib.path(lib.pick("TopperModes", "Hero")))




if __name__ == "__main__":
    unittest.main()
