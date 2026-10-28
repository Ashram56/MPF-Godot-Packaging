# Remote PuP screens: a topper (or any small screen) on a Raspberry Pi

A PuP Pack's topper videos (screens 13 and 14 in the packs we know) can play on a small screen of their own, driven by a
Raspberry Pi, instead of in a window on the cabinet's computer. The game sends the Pi short commands over the network
(Wi-Fi or Ethernet); the videos are on the Pi's SD card. The cabinet keeps all the sound. This is platform code, shared by
every game: the game only feeds it (section "What a game provides"). Code: `mpf_godot/pup_remote/`; tests:
`tests/test_pup_remote.py`.

Tested: the server, the link and the player on Linux with a desktop mpv (fake mpv in the tests). Not tested on a real
Raspberry Pi yet.

## What you need

- A Raspberry Pi 3 Model A+ (four cores, the Pi's H.264 decoder) or a Pi Zero W (same decoder, one slow core, untested),
  with its screen on HDMI, running Raspberry Pi OS Lite (Bookworm) with a hostname, a user, Wi-Fi and SSH set in the Imager.
- The Pi and the game computer on the same network.

## On the Pi

```bash
curl -fsSL https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/mpf_godot/pup_remote/topper/install.sh | bash
```

(or `bash mpf_godot/pup_remote/topper/install.sh` from a clone; `--uninstall` removes it). It installs mpv, the agent
(`/opt/pup-topper`), its settings (`/etc/pup-topper.cfg`) and a systemd service `pup-topper` that starts at boot. The videos
live in `~/pup-topper/media` (the game's media tool copies them there, with a `manifest.json` of
`{"files": {pack path: {"out": file}}}`; without a manifest every file in the folder is used).

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
`PYTHONPATH` (`MPF_GODOT_PACKAGING` / `MPF_PLATFORM_DIR`). The game also owns the media tool that picks the topper's
playlists from its pack and copies them to the Pi (re-encoding what the Pi's decoder can't play: not H.264, above
1920x1080 or 30 fps, 10-bit or 4:4:4) and its own on/off setting.

## Testing without a Pi

On a Linux or macOS computer with mpv: `python mpf_godot/pup_remote/topper/topper.py --window --media <topper media folder>`
beside a game with the remote screens on.

## To check on the Pi

1. Smooth playback with `--hwdec=v4l2m2m-copy` on the 3 A+ and a Zero W (try `--hwdec=no` to compare).
2. Discovery on the cabinet's network (else set `host=`).
3. The underlay resuming where it was after a pop-up.
