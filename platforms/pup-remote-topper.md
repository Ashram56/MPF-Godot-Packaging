# Remote PuP screens: a topper (or any small screen) on a Raspberry Pi

A PuP Pack's topper videos (screens 13 and 14 in the packs we know) can play on a small screen of their own, driven by a
Raspberry Pi, instead of in a window on the cabinet's computer. The game sends the Pi short commands over the network
(Wi-Fi or Ethernet); the videos are on the Pi's SD card. The cabinet keeps all the sound. This is platform code, shared by
every game: the game only feeds it (section "What a game provides"). Code: `mpf_godot/pup_remote/`; tests:
`tests/test_pup_remote.py`.

**The videos are not in any image or bundle.** The game serves them, read in place from the PuP Pack the player unpacked
(game format 2: nothing of the pack is in the bundle), and the Pi downloads what is new at each connection ("Videos").

Tested: the server, the link and the player on Linux with a desktop mpv (fake mpv in the tests). Not tested on a real
Raspberry Pi yet.

## What you need

- A Raspberry Pi 3 Model A+ (four cores, the Pi's H.264 decoder) or a Pi Zero W (same decoder, one slow core, untested),
  with its screen on HDMI, running Raspberry Pi OS Lite (Bookworm) with a hostname, a user, Wi-Fi and SSH set in the Imager.
- The Pi and the game computer on the same network.

## On a Pi Zero W: the image

`platforms/raspberrypi/zero/` builds a flashable image (Raspberry Pi OS Lite 32-bit, the userland that runs on the Zero's
ARMv6 core, plus mpv and the agent; [README](raspberrypi/zero/README.md)). Flash it, edit `network-config` (Wi-Fi) and
`user-data` (hostname, password, SSH key) on its boot partition, power on: the topper finds the game by itself and downloads
its videos. Nothing is installed or generated on the Pi. For any other Pi, the installer below.

## On the Pi (installer, any Pi)

```bash
curl -fsSL https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/mpf_godot/pup_remote/topper/install.sh | bash
```

(or `bash mpf_godot/pup_remote/topper/install.sh` from a clone; `--uninstall` removes it). It installs mpv, the agent
(`/opt/pup-topper`), its settings (`/etc/pup-topper.cfg`) and a systemd service `pup-topper` that starts at boot. The videos
live in `~/pup-topper/media`, downloaded from the game (below), with a `manifest.json` of
`{"files": {pack path: {"out": file, "size", "mtime"}}}`; with `download=false`, put the files there by hand (without a
manifest every file in the folder is used).

## Videos

The game's remote server (`RemoteServer(..., media={pack path: file})`) also serves HTTP on `media_port` (default 5053):
`GET /manifest.json` (`{"files": {pack path: {"size", "mtime"}}}`) and `GET /media/<pack path>` (one `Range: bytes=N-`, to
resume). Only the files the game listed are served; no path is ever built from the URL. The welcome tells the Pi the port.
At each connection the agent compares the manifest with its own `manifest.json`, downloads what is missing or changed
(`NAME.part`, renamed when whole, a partial one resumes), removes what the game no longer lists, and restarts the screens once
with the new files. A video that is not there yet is skipped (nothing plays, the underlay stays). `download=false` turns it off.
The Pi's hardware decoder plays H.264, 8-bit 4:2:0, at most 1920x1080 and 30 fps; a pack video outside that (the manifest does not
say yet) is a bundle add-on of re-encoded copies made once in the game repository, never a step on the cabinet.

Settings (`/etc/pup-topper.cfg`, then `sudo systemctl restart pup-topper`): `host` (`auto` = found by broadcast, else the
game computer's name or address), `fit` (`fit`, `fill`, `stretch`), `align`, `audio`, `mpv_args` (default
`--vo=gpu --gpu-context=drm --hwdec=v4l2m2m-copy`), `screens` (default `13,14`: underlay, then pop-up layer). Log:
`journalctl -u pup-topper -f`.

## How it works

```
 Game computer                                       Raspberry Pi
 MPF: PuP triggers (the game)                        topper.py (systemd service)
   `-- server.py: TCP 5052, JSON lines  -- network ->  PinUP rules of its screens (screen_rules.py)
          UDP 5052: answers the Pi's broadcast          --> mpv on its IPC socket --> the screen
```

- The server runs in MPF's event loop. On connect it sends each screen's default background, the playlists' rules
  (order, volume) and what the screens show now (last SetBG and running loop), then every new command, and a ping every 5 s
  (the Pi reconnects after 15 s without news).
- The Pi keeps PinUP Player's rules itself (`screen_rules.py`: priority, Loop, SetBG, StopFile, StopPlayer, SkipSamePrty, the
  background back when a video ends), because only the Pi knows when its video ends. One mpv plays both layers: the pop-up
  while it plays, else the underlay, which resumes where it was.
- Discovery: UDP broadcast `PUP_DISCOVER` to the port; the server answers `{"type": "here", "port", "game"}`. Protocol and
  messages: the docstring of `server.py`.

## What a game provides

```python
from mpf_godot.pup_remote import server
remote = server.RemoteServer(screens, playlists, game="name", host="0.0.0.0", port=5052, discovery=True)
asyncio.ensure_future(remote.start(), loop=machine.clock.loop)      # then, for each PuP command dict:
remote.send(cmd)      # {screen, playlist, file, mode, priority, length, volume}
remote.close()
```

`screens` is `{screen number: {"playlist", "file", "active"}}` (screens.pup) and `playlists` is
`{folder (lower case): {"alpha_sort": bool, "volume": percent}}` (playlists.pup). The import needs the platform on
`PYTHONPATH` (`MPF_GODOT_PACKAGING` / `MPF_PLATFORM_DIR`). The videos: pass
`media=mpf_godot.pup_remote.media.topper_media(pack, screens, triggers)` (the media files of the playlists the topper's screens
play, from the pack read in place) to `RemoteServer`. The game also owns its on/off setting: an option `[remote] enabled` in its
settings schema, written to the game's `pup.local.cfg` (Tron: `scripts/package/options.json`).

## Testing without a Pi

On a Linux or macOS computer with mpv: `python mpf_godot/pup_remote/topper/topper.py --window --media <topper media folder>`
beside a game with the remote screens on.

## To check on the Pi

0. The image on a real Pi Zero W: boot, Wi-Fi from `network-config`, the topper found by broadcast, the videos downloaded.
1. Smooth playback with `--hwdec=v4l2m2m-copy` on the 3 A+ and a Zero W (try `--hwdec=no` to compare).
2. Discovery on the cabinet's network (else set `host=`).
3. The underlay resuming where it was after a pop-up.
