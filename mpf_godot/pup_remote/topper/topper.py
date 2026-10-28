#!/usr/bin/env python3
"""The remote topper: plays the PuP Pack's topper videos (PuP screens 13 and 14) on a small computer of its own,
a Raspberry Pi with its own screen, at the moments the game sends them (mpf_godot/pup_remote/server.py).

    python3 topper.py                         # with /etc/pup-topper.cfg (the Pi's service)
    python3 topper.py --config my.cfg         # another config
    python3 topper.py --window --media DIR    # on a desktop: mpv in a window, game found on the network

It finds the game by a UDP broadcast (or host= in its config), keeps PinUP Player's rules for both screens itself
(screen_rules.py, the same file as mpf_godot/pup_remote/screen_rules.py) and plays through mpv, controlled on its JSON IPC
socket: the pop-up layer (14) while it plays, else the underlay (13), which resumes where it was. Without the game it
keeps showing what it showed, and comes back in step when the game is back. Standard library only, plus mpv.
platforms/pup-remote-topper.md has the set-up.
"""
import argparse
import asyncio
import configparser
import json
import logging
import os
import shlex
import socket
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                                        # installed: next to this file
sys.path.insert(1, os.path.dirname(HERE))                                       # in the repository: pup_remote/
import screen_rules  # noqa: E402

log = logging.getLogger("pup-topper")
VERSION = 1
DISCOVER = b"PUP_DISCOVER"
DEFAULTS = {
    "host": "auto",                 # "auto": found by broadcast; else the game computer's name or address
    "port": "5052",
    "name": "topper",
    "screens": "13,14",             # underlay, then pop-up layer
    "media": "~/pup-topper/media",
    "fit": "fill",                  # fit (black bars), fill (crop), stretch
    "align": "0.5",                 # vertical place of a fitted video: 0 top, 0.5 centre, 1 bottom
    "audio": "false",               # the cabinet plays the sound
    "mpv": "mpv",
    "mpv_args": "--vo=gpu --gpu-context=drm --hwdec=v4l2m2m-copy",
    "window": "false",              # true: a desktop window (testing) instead of the whole screen
    "window_size": "960x281",
    "timeout": "15",                # seconds without a ping from the game before it is taken as gone
}


def load_config(path, overrides):
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cfg.read_dict({"topper": DEFAULTS})
    if path:
        cfg.read(path)
    opts = dict(cfg["topper"])
    opts.update({k: v for k, v in overrides.items() if v is not None})
    return opts


def load_library(media_dir, playlists=None):
    """manifest.json from the game's topper media tool ({"files": {pack path: {"out": file}}}), else every file."""
    files = {}
    manifest = os.path.join(media_dir, "manifest.json")
    if os.path.exists(manifest):
        with open(manifest, encoding="utf-8") as f:
            for key, entry in json.load(f).get("files", {}).items():
                files[key] = os.path.join(media_dir, entry.get("out", key))
    else:
        for root, _dirs, names in os.walk(media_dir):
            for name in names:
                path = os.path.join(root, name)
                files[os.path.relpath(path, media_dir).replace(os.sep, "/")] = path
    return screen_rules.Library(files, playlists)


# ---------------------------------------------------------------------- mpv

class Mpv:
    """mpv started idle with a JSON IPC socket; one file at a time."""

    def __init__(self, opts):
        self.opts = opts
        self.socket = os.path.join(tempfile.gettempdir(), "pup-topper-mpv-%d.sock" % os.getpid())
        self.on_eof = None
        self.position = 0.0
        self.path = ""
        self._proc = None
        self._writer = None
        self._queue = []

    def args(self):
        o = self.opts
        args = [o["mpv"], "--idle=yes", "--input-ipc-server=" + self.socket, "--force-window=yes",
                "--no-osc", "--osd-level=0", "--no-input-default-bindings", "--no-terminal", "--keep-open=no",
                "--image-display-duration=inf", "--really-quiet",
                "--video-align-y=%.3f" % (float(o["align"]) * 2.0 - 1.0)]
        if o["fit"] == "fill":
            args.append("--panscan=1.0")
        elif o["fit"] == "stretch":
            args.append("--keepaspect=no")
        if o["audio"].lower() not in ("1", "true", "yes", "on"):
            args.append("--aid=no")
        if o["window"].lower() in ("1", "true", "yes", "on"):
            args += ["--geometry=" + o["window_size"], "--title=PuP topper"]
        else:
            args += ["--fullscreen"] + shlex.split(o["mpv_args"])
        return args

    async def start(self):
        if os.path.exists(self.socket):
            os.remove(self.socket)
        self._proc = await asyncio.create_subprocess_exec(*self.args())
        for _ in range(100):
            if os.path.exists(self.socket):
                break
            await asyncio.sleep(0.1)
        reader, self._writer = await asyncio.open_unix_connection(self.socket)
        self._send(["observe_property", 1, "time-pos"])
        for cmd in self._queue:
            self._send(cmd)
        self._queue.clear()
        asyncio.ensure_future(self._read(reader))

    async def _read(self, reader):
        while True:
            line = await reader.readline()
            if not line:
                log.error("mpv quit")
                os._exit(1)                     # the service restarts us, and mpv with us
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("event") == "property-change" and msg.get("name") == "time-pos":
                self.position = msg.get("data") or 0.0
            elif msg.get("event") == "end-file" and msg.get("reason") == "eof" and self.on_eof:
                self.on_eof()

    def _send(self, command):
        if self._writer is None:
            self._queue.append(command)
            return
        self._writer.write(json.dumps({"command": command}).encode() + b"\n")

    def play(self, path, loop, volume, start=0.0):
        self.path = path
        self.position = start
        self._send(["set_property", "loop-file", "inf" if loop else "no"])
        self._send(["set_property", "start", "%.3f" % start if start > 0 else "none"])
        self._send(["set_property", "volume", round(max(0.0, min(volume, 1.0)) * 100)])
        self._send(["loadfile", path, "replace"])

    def clear(self):
        self.path = ""
        self._send(["stop"])

    def stop_process(self):
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()


# ---------------------------------------------------------------------- the two layers

class Layer:
    """A screen_rules output: what one PuP screen wants shown."""

    def __init__(self, display):
        self.display = display
        self.key, self.loop, self.volume, self.visible = "", False, 1.0, True

    def start(self, key, loop, volume):
        self.key, self.loop, self.volume = key, loop, volume
        self.display.refresh(restart=self)

    def stop(self):
        self.key = ""
        self.display.refresh()

    def set_visible(self, visible):
        self.visible = visible
        self.display.refresh()


class Display:
    """The PuP screens of one window, the last on top (a pop-up layer shows only while it plays)."""

    def __init__(self, player, library):
        self.player, self.library = player, library
        self.layers = []                # [(screen number, Layer, Screen)], bottom first
        self.shown = None               # the Layer on screen
        self.resume = {}                # Layer -> (key, position): an underlay covered by a pop-up
        self._setting_up = False        # setup() running: the screens settle first, the player is told once
        player.on_eof = self._eof

    def setup(self, screens_info, playlists, numbers, current=()):
        """The game's welcome: each screen's background and pop-up flag, the playlists' rules, and the commands that
        set what the screens show now. A loop already on screen (the game came back) goes on without a restart."""
        self.library.playlists = {k.lower(): v for k, v in (playlists or {}).items()}
        self.layers, self.shown, self.resume = [], None, {}
        loop = asyncio.get_event_loop()
        for n in numbers:
            info = screens_info.get(str(n), {})
            layer = Layer(self)
            screen = screen_rules.Screen(n, self.library, layer, lambda s, cb: loop.call_later(s, cb),
                                         popup=bool(info.get("popup")), bg_playlist=info.get("bg_playlist", ""),
                                         bg_file=info.get("bg_file", ""))
            self.layers.append((n, layer, screen))
        self._setting_up = True
        try:
            for _n, _layer, screen in self.layers:
                screen.start_background()
            for cmd in current:
                self.command(cmd)
        finally:
            self._setting_up = False
        self.refresh()

    def command(self, cmd):
        for n, _layer, screen in self.layers:
            if n == cmd.get("screen"):
                screen.command(cmd)

    def top(self):
        for _n, layer, _screen in reversed(self.layers):
            if layer.visible and layer.key:
                return layer
        return None

    def refresh(self, restart=None):
        if self._setting_up:
            return
        top = self.top()
        if top is self.shown and (restart is None or top is not restart):
            return
        old = self.shown
        if old is not None and old is not top and old.key and old.loop and self.player.path:
            self.resume[old] = (old.key, self.player.position)          # covered: comes back where it was
        self.shown = top
        if top is None:
            self.player.clear()
            return
        start = 0.0
        kept = self.resume.pop(top, None)
        if top is not restart and kept and kept[0] == top.key:
            start = kept[1]
        path = self.library.path(top.key)
        if restart is None and top.loop and path == self.player.path:
            return                      # already on screen (the game came back): no restart
        log.info("play %s%s", top.key, " from %.1f s" % start if start else "")
        self.player.play(path, top.loop, top.volume, start)

    def _eof(self):
        for _n, layer, screen in self.layers:
            if layer is self.shown:
                screen.finished()
                return


# ---------------------------------------------------------------------- the game link

async def discover(port, timeout=2.0, target="255.255.255.255"):
    """The game's address and port, from its answer to a broadcast; None when nobody answers."""
    loop = asyncio.get_running_loop()
    answer = loop.create_future()

    class Proto(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            try:
                msg = json.loads(data)
            except ValueError:
                return
            if msg.get("type") == "here" and not answer.done():
                answer.set_result((addr[0], int(msg.get("port", port))))

    transport, _ = await loop.create_datagram_endpoint(Proto, family=socket.AF_INET, allow_broadcast=True)
    try:
        transport.sendto(DISCOVER, (target, port))
        return await asyncio.wait_for(answer, timeout)
    except (asyncio.TimeoutError, OSError):
        return None
    finally:
        transport.close()


async def session(opts, display, numbers):
    """One connection to the game, until it closes or goes quiet."""
    port = int(opts["port"])
    if opts["host"] == "auto":
        found = await discover(port)
        if not found:
            return False
        host, port = found
    else:
        host = opts["host"]
    reader, writer = await asyncio.open_connection(host, port)
    log.info("connected to the game at %s:%d", host, port)
    hello = {"type": "hello", "name": opts["name"], "screens": numbers, "version": VERSION}
    writer.write(json.dumps(hello).encode() + b"\n")
    try:
        while True:
            line = await asyncio.wait_for(reader.readline(), float(opts["timeout"]))
            if not line:
                return True
            msg = json.loads(line)
            kind = msg.get("type")
            if kind == "welcome":
                display.setup(msg.get("screens", {}), msg.get("playlists", {}), numbers, msg.get("current", []))
            elif kind == "play":
                display.command(msg.get("cmd", {}))
    except asyncio.TimeoutError:
        log.warning("the game went quiet")
        return True
    finally:
        writer.close()


async def run(opts):
    numbers = [int(n) for n in opts["screens"].split(",") if n.strip()]
    media = os.path.expanduser(opts["media"])
    library = load_library(media)
    log.info("%d media files in %s", len(library.files), media)
    player = Mpv(opts)
    await player.start()
    display = Display(player, library)
    display.setup({}, {}, numbers)
    try:
        while True:
            try:
                if not await session(opts, display, numbers):
                    await asyncio.sleep(1)
                    continue
            except (OSError, ValueError) as e:
                log.info("no game: %s", e)
            await asyncio.sleep(3)
    finally:
        player.stop_process()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", default="/etc/pup-topper.cfg")
    ap.add_argument("--host", help="the game computer (default: found on the network)")
    ap.add_argument("--port")
    ap.add_argument("--media", help="the topper videos (the game's topper media tool)")
    ap.add_argument("--window", action="store_const", const="true", help="a desktop window, for testing")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(message)s")
    opts = load_config(a.config if os.path.exists(a.config) else None,
                       {"host": a.host, "port": a.port, "media": a.media, "window": a.window})
    try:
        asyncio.run(run(opts))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
