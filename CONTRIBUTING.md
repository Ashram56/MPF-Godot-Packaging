# Contributing: what belongs in this repository

Two repositories share the learnings of the Stern SAM recreations. Route each one to the right place, in the same
session you find it (open a pull request; without write access, open an issue directly).

| The finding is about | It goes to |
|---|---|
| Godot, GDE GoZen, native video, GMC, MPF, MPF Monitor, their versions and patches | **this repository** (`fixes/<component>/`, one file each, with an upstream draft) |
| A platform or board: Windows, macOS, Linux, Jetson, Raspberry Pi, video decoders, drivers, kernel modules, sound and screens, VideoCore / V4L2, frame rates, installers and images | **this repository** (`platforms/`) |
| Taking a SAM ROM apart, recoding the game's rules, reference traces, the VPX table, PuP Pack mapping, a game's own look | [Ashram56/Stern-SAM-Decryption](https://github.com/Ashram56/Stern-SAM-Decryption) (`agents/`, `knowledge/`) |
| One game's status, owner decisions and values | that game's repository |

A finding that spans both (for example a PuP Pack that needs a decoder fix) is written once, here, and the
Stern-SAM-Decryption file gets a one-line pointer to it. New fix: copy `fixes/TEMPLATE.md`, then run
`python fixes/make_index.py`; platform findings go in the platform's page under "Findings" or in a page listed in
`platforms/README.md`. Run `python -m pytest -q tests` before pushing. Never commit a ROM or private material.

**No game content here.** This repository holds no game: no recipe, no bundle spec, no file list, no URL, no name of a game or of its
PuP Pack. The game's repository (or the session that creates the game) produces a complete game package and describes it in its own
`bundle_spec.json` (`common/games/README.md`, "What the game provides"); this repository only turns that package into a bundle. The
provenance of a finding ("found on game X") is fine in `fixes/` and `platforms/`. `tests/test_no_game_content.py` enforces it.
