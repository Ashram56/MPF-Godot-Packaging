"""Remote PuP screens: the game's PuP commands sent over the network to a small display, such as the remote topper
on a Raspberry Pi (mpf_godot/pup_remote/topper/, platforms/pup-remote-topper.md).

Runs in MPF's own event loop (the game's PuP mode starts it), so a remote screen plays whether or not Godot has
a window for it. No MPF here: the unit tests drive it on a plain asyncio loop.

Protocol, one JSON object per line, on TCP port 5052 by default:
- the display finds the game by a UDP broadcast of DISCOVER on the same port; the game answers
  {"type": "here", "port": <tcp port>, "game": ...} to the sender;
- display -> game: {"type": "hello", "name": "topper", "screens": [13, 14], "version": 1};
- game -> display: {"type": "welcome", "version", "game", "screens": {"13": {"bg_playlist", "bg_file", "popup"}},
  "playlists": {folder: {"alpha_sort", "volume"}}, "current": [the commands that set what the screens show now: the
  last SetBG and the running looping play of each screen]}, then every new command;
- game -> display: {"type": "play", "cmd": {screen, playlist, file, mode, priority, length, volume}};
- game -> display: {"type": "ping"} every ping_seconds, so a display can tell the game is gone.

Videos: nothing is installed on the display. The game serves the media files it was given (`media`: pack path -> file,
the topper's playlists of the unpacked PuP Pack, read in place) over plain HTTP on `media_port` (default 5053), and the
welcome carries {"media": {"port"}}. GET /manifest.json -> {"version": 1, "files": {pack path: {"size", "mtime"}}};
GET /media/<pack path> -> the file (one Range, to resume a download). The display fetches what is missing or changed.
"""
import asyncio
import json
import logging
import os
import urllib.parse

log = logging.getLogger("mpf_godot.pup_remote")

PORT = 5052
MEDIA_PORT = 5053
VERSION = 1
DISCOVER = b"PUP_DISCOVER"
POPUP_SCREENS = (12, 14)                 # the pop-up (top) layer of the backglass and the topper (pup_player.gd)
MAX_BUFFER = 1 << 20                     # a display that stops reading is dropped past 1 MB of unsent commands


class _Discovery(asyncio.DatagramProtocol):

    def __init__(self, server):
        self.server = server
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if data.strip() == DISCOVER:
            reply = {"type": "here", "port": self.server.port, "game": self.server.game}
            self.transport.sendto(json.dumps(reply).encode(), addr)


class RemoteServer:

    def __init__(self, screens, playlists, game="", host="0.0.0.0", port=PORT, ping_seconds=5.0, discovery=True,
                 media=None, media_port=MEDIA_PORT):
        """screens: pupfiles.load_screens(); playlists: pupfiles.load_playlists(); media: {pack path: file} the displays
        download (None: no media server, the displays have their own videos); media_port: its TCP port (0: any)."""
        self.screens, self.playlists, self.game = screens, playlists, game
        self.host, self.port, self.ping_seconds, self.discovery = host, port, ping_seconds, discovery
        self.media, self.media_port = dict(media) if media else None, media_port
        self._media_server = None
        self.clients = {}                   # StreamWriter -> {"name", "screens"}
        self.bg = {}                        # screen -> its last SetBG command
        self.loop_cmd = {}                  # screen -> its running looping play (a mode's loop), until stopped
        self._server = None
        self._udp = None
        self._ping = None

    # ------------------------------------------------------------------ running

    async def start(self):
        self._server = await asyncio.start_server(self._client, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        if self.discovery:
            try:
                loop = asyncio.get_running_loop()
                self._udp, _ = await loop.create_datagram_endpoint(
                    lambda: _Discovery(self), local_addr=(self.host, self.port), allow_broadcast=True)
            except OSError as e:
                log.warning("remote PuP screens: no discovery on UDP %d (%s); displays need host= set", self.port, e)
        if self.media is not None:
            self._media_server = await asyncio.start_server(self._media_client, self.host, self.media_port)
            self.media_port = self._media_server.sockets[0].getsockname()[1]
            log.info("remote PuP screens: %d media files served on port %d", len(self.media), self.media_port)
        self._ping = asyncio.ensure_future(self._pinger())
        log.info("remote PuP screens: listening on %s:%d", self.host, self.port)

    def close(self):
        if self._ping:
            self._ping.cancel()
        if self._udp:
            self._udp.close()
        if self._server:
            self._server.close()
        if self._media_server:
            self._media_server.close()
        for writer in list(self.clients):
            writer.close()
        self.clients.clear()

    async def _pinger(self):
        while True:
            await asyncio.sleep(self.ping_seconds)
            for writer in list(self.clients):
                self._write(writer, {"type": "ping"})

    # ------------------------------------------------------------------ commands

    def send(self, cmd):
        """One PuP command (engine.Engine's send): to every display showing its screen, and kept for late joiners."""
        screen = cmd.get("screen")
        mode = str(cmd.get("mode") or "").lower()
        running = self.loop_cmd.get(screen)
        if mode == "setbg":
            self.bg[screen] = cmd
        elif running is None:
            if mode == "loop":
                self.loop_cmd[screen] = cmd
        elif mode == "stopplayer" or mode == "stopfile" and _same_media(running, cmd):
            del self.loop_cmd[screen]
        elif mode != "stopfile" and int(cmd.get("priority") or 0) >= int(running.get("priority") or 0):
            # a play that replaces the loop (screen_rules.Screen.command): the new loop, or none once it ends
            if mode == "loop":
                self.loop_cmd[screen] = cmd
            else:
                del self.loop_cmd[screen]
        for writer, info in list(self.clients.items()):
            if screen in info["screens"]:
                self._write(writer, {"type": "play", "cmd": cmd})

    def current(self, screens):
        """The commands that bring a display joining now to what its screens show."""
        out = [self.bg[s] for s in screens if s in self.bg]
        return out + [self.loop_cmd[s] for s in screens if s in self.loop_cmd]

    # ------------------------------------------------------------------ clients

    async def _client(self, reader, writer):
        peer = writer.get_extra_info("peername")
        try:
            line = await asyncio.wait_for(reader.readline(), 10)
            hello = json.loads(line or b"{}")
            if hello.get("type") != "hello":
                return
            screens = [int(s) for s in hello.get("screens", [])]
            info = {"name": str(hello.get("name", "display")), "screens": screens}
            self._write(writer, self.welcome(screens))
            self.clients[writer] = info
            log.info("remote PuP display %r connected from %s, screens %s", info["name"], peer, screens)
            while await reader.readline():      # nothing more is expected; read until the display goes
                pass
        except (asyncio.TimeoutError, ValueError, OSError) as e:
            log.info("remote PuP display at %s: %s", peer, e)
        finally:
            if self.clients.pop(writer, None):
                log.info("remote PuP display at %s left", peer)
            writer.close()

    # ------------------------------------------------------------------ media (HTTP)

    def manifest(self):
        files = {}
        for key, path in sorted(self.media.items()):
            try:
                st = os.stat(path)
            except OSError:
                continue
            files[key] = {"size": st.st_size, "mtime": int(st.st_mtime)}
        return {"version": 1, "files": files}

    async def _media_client(self, reader, writer):
        """One HTTP/1.1 request per connection: GET /manifest.json or GET /media/<pack path> (optional Range: bytes=N-)."""
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            lines = head.decode("latin-1").split("\r\n")
            parts = lines[0].split(" ")
            headers = {l.split(":", 1)[0].strip().lower(): l.split(":", 1)[1].strip() for l in lines[1:] if ":" in l}
            if len(parts) < 2 or parts[0] != "GET":
                return await self._http(writer, 405, b"GET only")
            target = urllib.parse.unquote(parts[1].split("?", 1)[0])
            if target == "/manifest.json":
                return await self._http(writer, 200, json.dumps(self.manifest(), separators=(",", ":")).encode(),
                                        "application/json")
            key = target[len("/media/"):] if target.startswith("/media/") else None
            path = self.media.get(key) if key else None          # only what the game listed: no path is ever built from the URL
            if not path or not os.path.isfile(path):
                return await self._http(writer, 404, b"not found")
            size, start = os.path.getsize(path), 0
            rng = headers.get("range", "")
            if rng.startswith("bytes=") and rng.endswith("-") and rng[6:-1].isdigit():
                start = min(int(rng[6:-1]), size)
            head_lines = [b"HTTP/1.1 206 Partial Content" if start else b"HTTP/1.1 200 OK",
                          b"Content-Type: application/octet-stream", b"Accept-Ranges: bytes",
                          b"Content-Length: %d" % (size - start), b"Connection: close"]
            if start:
                head_lines.append(b"Content-Range: bytes %d-%d/%d" % (start, size - 1, size))
            writer.write(b"\r\n".join(head_lines) + b"\r\n\r\n")
            loop = asyncio.get_running_loop()
            with open(path, "rb") as f:
                f.seek(start)
                while True:
                    chunk = await loop.run_in_executor(None, f.read, 1 << 20)
                    if not chunk:
                        break
                    writer.write(chunk)
                    await writer.drain()
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError, OSError):
            pass
        finally:
            writer.close()

    async def _http(self, writer, status, body, ctype="text/plain"):
        reason = {200: "OK", 404: "Not Found", 405: "Method Not Allowed"}[status]
        writer.write(("HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n"
                      % (status, reason, ctype, len(body))).encode() + body)
        await writer.drain()

    def welcome(self, screens):
        media = {"media": {"port": self.media_port}} if self._media_server else {}
        return {"type": "welcome", "version": VERSION, "game": self.game, **media,
                "screens": {str(s): {"bg_playlist": self.screens.get(s, {}).get("playlist", ""),
                                     "bg_file": self.screens.get(s, {}).get("file", ""),
                                     "popup": s in POPUP_SCREENS} for s in screens},
                "playlists": self.playlists, "current": self.current(screens)}

    def _write(self, writer, message):
        if writer.transport.is_closing():
            self.clients.pop(writer, None)
            return
        if writer.transport.get_write_buffer_size() > MAX_BUFFER:
            log.warning("remote PuP display not reading: dropped")
            self.clients.pop(writer, None)
            writer.close()
            return
        writer.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")


def _same_media(running, stop):
    """Whether a StopFile command names the running play (by file, else by playlist), as screen_rules does."""
    if stop.get("file"):
        return str(running.get("file", "")).rsplit(".", 1)[0].lower() == str(stop["file"]).rsplit(".", 1)[0].lower()
    return str(running.get("playlist", "")).lower() == str(stop.get("playlist", "")).lower()
