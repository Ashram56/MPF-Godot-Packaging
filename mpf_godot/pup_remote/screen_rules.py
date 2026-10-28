"""PinUP Player's rules for one PuP screen, in Python: the remote topper (mpf_godot/pup_remote/topper/) plays by them.

The same rules as the game's pup_screen.gd (Godot's PuP screens), kept player-agnostic so a Raspberry Pi with mpv,
or a test with a fake output, can follow them:
- a play replaces what runs when its priority is >= the running one's, else it is dropped;
- Loop column: "Loop" loops the file, "SetBG" makes it the screen's background (it plays when nothing else does),
  "StopFile" stops that file, "StopPlayer" stops the screen, "SkipSamePrty" drops the play when the running video
  has the same priority;
- when a video ends the background comes back; a pop-up layer (ForcePopBack) with no background hides.
Playlists are picked as the game's pup_player.gd picks them (pick()). Standard library only: the Pi's agent copies this
file next to itself.
"""
import os
import random
import re

_DIGITS = re.compile(r"(\d+)")


def natural_key(text):
    """'Drain10' after 'Drain9', case ignored (Godot's naturalnocasecmp_to)."""
    return [int(part) if part.isdigit() else part for part in _DIGITS.split(text.lower())]


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0].lower()


class Library:
    """The media a player has: pack paths ("Folder/File.mp4") -> the file to play, and the pack's playlists.

    files: {pack path: local path}; playlists: {folder (lower case): {"alpha_sort": bool, "volume": percent}}.
    """

    def __init__(self, files, playlists=None, rng=None):
        self.files = dict(files)
        self.playlists = {k.lower(): v for k, v in (playlists or {}).items()}
        self.rng = rng or random.Random()
        self.folders = {}
        for key in self.files:
            self.folders.setdefault(os.path.dirname(key).lower(), []).append(key)
        for keys in self.folders.values():
            keys.sort(key=natural_key)
        self._next = {}
        self._last = {}

    def pick(self, playlist, file=""):
        """Pack path of the file a play names, or the next file of its playlist; "" when there is none."""
        keys = self.folders.get(str(playlist).lower(), [])
        if file:
            want = _stem(file)
            return next((k for k in keys if _stem(k) == want), "")
        if not keys:
            return ""
        if self.playlists.get(str(playlist).lower(), {}).get("alpha_sort"):
            # in order from a random first file, as the Godot player does (numbered variants: Drain1-5)
            i = self._next.get(playlist, self.rng.randrange(len(keys))) % len(keys)
            self._next[playlist] = i + 1
            return keys[i]
        i = self.rng.randrange(len(keys))
        if len(keys) > 1 and keys[i] == self._last.get(playlist):
            i = (i + 1 + self.rng.randrange(len(keys) - 1)) % len(keys)
        self._last[playlist] = keys[i]
        return keys[i]

    def path(self, key):
        return self.files.get(key, "")

    def volume_of(self, cmd):
        """0..1: the command's own volume, else its playlist's."""
        volume = cmd.get("volume")
        if volume not in (None, ""):
            return float(volume) / 100.0
        return float(self.playlists.get(str(cmd.get("playlist", "")).lower(), {}).get("volume", 100.0)) / 100.0


class Screen:
    """One PuP screen. output: start(key, loop, volume), stop(), set_visible(bool); the player calls finished()
    when the media it plays ends. schedule(seconds, callback) runs the `length` timers."""

    def __init__(self, number, library, output, schedule, popup=False, bg_playlist="", bg_file=""):
        self.number = number
        self.library = library
        self.output = output
        self.schedule = schedule
        self.popup = popup
        self.fg = None          # {playlist, file, key, priority, loop, volume}
        self.bg = {"playlist": bg_playlist, "file": bg_file} if bg_playlist else None
        self.bg_playing = False
        self.key = ""           # what the output plays ("" = nothing)
        self.loop = False
        self._serial = 0
        output.set_visible(not popup)

    def start_background(self):
        if self.bg and self.fg is None:
            self._play_bg()

    def command(self, cmd):
        mode = str(cmd.get("mode") or "").lower()
        priority = int(cmd.get("priority") or 0)
        if mode == "stopfile":
            if self.fg is not None and self._matches(self.fg, cmd):
                self._stop_fg()
            return
        if mode == "stopplayer":
            if self.fg is not None:
                self._stop_fg()
            elif self.popup:
                self._stop_media()
                self.output.set_visible(False)
            return
        if mode == "setbg":
            self.bg = {"playlist": cmd.get("playlist", ""), "file": cmd.get("file", "")}
            if self.fg is None:
                self._play_bg()
            return
        if mode == "skipsameprty" and self.fg is not None and int(self.fg["priority"]) == priority:
            return
        if self.fg is not None and priority < int(self.fg["priority"]):
            return
        key = self.library.pick(cmd.get("playlist", ""), cmd.get("file", ""))
        if not key:
            return
        self.fg = {"playlist": cmd.get("playlist", ""), "file": os.path.basename(key), "key": key,
                   "priority": priority, "loop": mode == "loop", "volume": self.library.volume_of(cmd)}
        self._start(key, self.fg["loop"], self.fg["volume"])
        length = float(cmd.get("length") or 0)
        if length > 0:
            serial = self._serial

            def timeout():
                if serial == self._serial and self.fg is not None:
                    self._stop_fg()
            self.schedule(length, timeout)

    def finished(self):
        """The output's media ended (a looping one never does: the output loops it)."""
        if self.fg is not None:
            self._stop_fg()
        elif self.bg and self.bg_playing and not self.bg["file"]:
            self._play_bg()                     # a playlist background moves to its next file

    @staticmethod
    def _matches(entry, cmd):
        file = str(cmd.get("file") or "")
        if file:
            return _stem(entry["file"]) == _stem(file)
        return entry["playlist"].lower() == str(cmd.get("playlist", "")).lower()

    def _stop_fg(self):
        self.fg = None
        if self.bg:
            self._play_bg()
        else:
            self._stop_media()
            if self.popup:
                self.output.set_visible(False)

    def _play_bg(self):
        key = self.library.pick(self.bg["playlist"], self.bg["file"])
        if not key:
            self._stop_media()
            return
        # a background named by its file loops that file; a playlist background moves to its next file
        self._start(key, bool(self.bg["file"]), self.library.volume_of({"playlist": self.bg["playlist"]}))

    def _start(self, key, loop, volume):
        self._serial += 1
        self.bg_playing = self.fg is None
        self.key, self.loop = key, loop
        if self.popup:
            self.output.set_visible(True)
        self.output.start(key, loop, volume)

    def _stop_media(self):
        self._serial += 1
        self.bg_playing = False
        self.key, self.loop = "", False
        self.output.stop()
