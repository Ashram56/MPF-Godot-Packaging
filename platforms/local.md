# The local platform: a cabinet's game on a desktop (Windows, macOS, Linux)

To check a game bundle on a PC or a Mac before it goes to a cabinet: the same bundle (`<id>-<version>-linux-all.tar.xz`, the one the
setup page installs from the WebDAV share), installed and started by the same code as on the image, in a window, with the DMD on the
screen or on a ZeDMD plugged into the computer (PPUC's libzedmd, Serum colour by PPUC's libserum, both unmodified). Any game: nothing
here knows one. Back to [all platforms](README.md).

The game repository's own one-line install (its `run.py`) stays what it is; this page is the **platform's** way of starting a bundle,
separate from any game.

## Set up once

1. The platform, with the one line of [README.md](README.md) (Windows: `install/install_windows.ps1`; macOS: `install/install_macos.sh`):
   it clones this repository into `~/MPF-Godot` (Windows `%USERPROFILE%\MPF-Godot`) and installs Python 3.11, MPF, Godot and the patched
   GMC. Until the local platform is on `main`, set `MPF_GODOT_BRANCH` to its branch first (PowerShell:
   `$env:MPF_GODOT_BRANCH = "claude/project-thread-49zld7"`).
2. The ZeDMD bridge:
   - **Windows x64**: nothing to do, `native/prebuilt/windows-x86_64/dmd_bridge/` is in the repository (`dmd_bridge.exe`, `zedmd64.dll`,
     `serum64.dll` and their DLLs; `SOURCES.txt` says what each is, `SHA256SUMS` their sums). It is built on Linux with mingw-w64 by
     `native/build_windows_bridge.sh`.
   - **macOS**: `python -m mpf_godot local build-bridge` builds libzedmd, libserum and `dmd_bridge` on the Mac into
     `native/bin/macos-<arch>/dmd_bridge/` (needs Xcode's command line tools and `brew install cmake autoconf automake libtool`).
   - **Linux**: the same command, or the build of [dmd_devices.md](dmd_devices.md).

The commands below run from the clone with the venv's Python: `.venv\Scripts\python` on Windows, `.venv/bin/python` elsewhere
(written `python` here).

## Use

```sh
python -m mpf_godot local doctor                                   # Godot, MPF, GMC, dmd_bridge, does a ZeDMD answer
python -m mpf_godot local install https://<share>/MPF%20Games/<game>/<bundle>.tar.xz --user claude
python -m mpf_godot local install D:\Downloads\<bundle>.tar.xz     # or a file (its .sha256 beside it is checked)
python -m mpf_godot local pup "D:\Downloads\<the author's pack>.zip"   # the PuP Pack, unpacked untouched, linked to the game
python -m mpf_godot local serum D:\Colorisations\<rom>.cROMc        # a Serum colourisation, by the ROM's name
python -m mpf_godot local dmd --output zedmd --serum <game id>=<rom>   # where the DMD goes; which colourisation a game uses
python -m mpf_godot local start                                     # the active game, in a window
python -m mpf_godot local start --dmd lcd                           # this run only: the DMD on the screen
python -m mpf_godot local start --dmd preview                       # the ZeDMD's pictures (Serum colour) in a window, no ZeDMD needed
python -m mpf_godot local start --dry-run                           # print the configs, Godot arguments and MPF_* variables
python -m mpf_godot local settings ; python -m mpf_godot local set dmd.mode=classic
python -m mpf_godot local list ; python -m mpf_godot local use <id or id@version> ; python -m mpf_godot local remove <id@version>
```

| Command | What the cabinet does the same way |
|---|---|
| `install` | the page's install from the share (`mpf_games.install_game`): sha256 of the archive, `SHA256SUMS` of every file, the format 2 contract and the import walk (`mpf_contract.problems`, `mpf_bundlecheck`; a format 1 game's `run.check`), the platform's add-ons (`platform_addons`, this computer's native files only), one Godot import, the settings, scores and PuP link of the installed version carried over (`keep_on_update`, `.platform/`), the new version made active |
| `pup` | the author's zip is unpacked as it is into the library and linked into the game (`.platform/pup` for format 2, `pup.pack_dir` for a format 1 `extract_only` game); nothing of the game runs. Windows uses a junction (no administrator rights needed) |
| `dmd`, `serum` | `mpf_dmd.py`: output `auto`, `lcd`, `zedmd` or `pin2dmd`, the single colour, the Serum library (one file per ROM name) and its assignment per game (default: the bundle's `dmd.rom`) |
| `start` | format 2: `mpf_contract.plan` (configs, Godot arguments of the settings and of the board's profile, `MPF_PUP_PACK`, `MPF_ADDONS`, `MPF_GAME_DATA`) plus `mpf_dmd.plan`, then `mpf_godot run`; format 1: the bundle's `run.start` with `mpf_dmd.merge_args` |

With the output `zedmd` (saved or `--dmd zedmd`), `start` first asks `dmd_bridge --probe`: when no ZeDMD answers (not plugged in,
port taken), that run shows the DMD on the screen instead of none.

`local start --dmd preview` shows the DMD a ZeDMD would get, **Serum colour included**, in a window (`mpf_godot/dmd_preview.py`, tkinter:
part of the python.org installers; Linux `apt install python3-tk`). `dmd_bridge --rgb-out FILE` writes each picture, the window shows the file;
the game hides its own screen DMD, as it does for a ZeDMD. No ZeDMD needed (and none is driven in that run).

What a desktop changes: no systemd or game user, the game in a window instead of the cabinet's screens (`MPF_GAME_ARGS` adds the
cabinet's own arguments when you want them), `auto` looks for a ZeDMD with `dmd_bridge --probe` (libzedmd tries every serial port;
`local dmd --port COM5` names one), and the board is `x86` (a Mac with Apple silicon: `arm64`; `MPF_BOARD=rpi4` shows a game as a
Raspberry Pi 4 would run it, its profile's limits included). Everything lives in `~/MPF-Local` (`MPF_LOCAL_DIR`): `games/`, `pups/`,
`serum/`, `state/`. A WebDAV password comes from `MPF_WEBDAV_PASSWORD`, else it is asked once.

## Checked (2026-11-02, cloud sandbox, Linux x86_64)

- `tests/test_local.py`: install, sha256 refused, a bundle with commands refused, PuP assignment, settings, ZeDMD + Serum arguments,
  a new version keeping settings and pack.
- A real game bundle from the share (format 1, 438 MB): installed in 57 s, started 60 s under Xvfb with output `zedmd` and its
  Serum file: `dmd_bridge` loaded the colourisation (Serum v2) and received the game's frames, coloured (the attract mode's
  "REPLAY AT" page in the colourisation's colours).
- `dmd_bridge.exe` under Wine: the single colour, and the real colourisation loaded by `serum64.dll` (`tests/test_dmd_bridge.py`,
  `MPF_TEST_WINE=1`).

**Not checked yet**: the commands on a real Windows or Mac, a real ZeDMD on Windows (libzedmd's port search on COM ports), the macOS
build of the bridge.

## Duplicating the whole machine (the setup page too)

The page's code (`common/netconfig/`) drives systemd, NetworkManager, ALSA and a read-only root: it runs on Linux only. To check the page
itself on a PC, run the image's Linux side instead of porting it: a WSL 2 distribution (Ubuntu 24.04, Windows 11's WSLg shows Godot's
window) with this repository's `common/netconfig` services, the ZeDMD passed in with `usbipd-win`. Not built; ask for it if the page
needs checking off the cabinet.
