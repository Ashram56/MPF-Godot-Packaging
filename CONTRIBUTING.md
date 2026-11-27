# Contributing: what belongs in this repository

Two repositories share the learnings of the Stern SAM recreations. Route each one to the right place, in the same
session you find it (open a pull request; without write access, open an issue directly).

| The finding is about | It goes to |
|---|---|
| Taking a SAM / WPC / Whitestar ROM apart: formats, OS, tables, emulator, Ghidra decompile, reference traces, the functional diagram, the VPX table extraction | [Ashram56/Stern-SAM-Decryption](https://github.com/Ashram56/Stern-SAM-Decryption) (`agents/rom_extraction.md`, `agents/vpx_extraction.md`, `knowledge/`) |
| Rebuilding the decoded game in MPF: rules, display, sound, lamps, VPX bridge, improvements, packaging, PuP Packs | **this repository** (`agents/`, `knowledge/`, `tools/pup/`) |
| MPF itself: its behaviour and quirks, `virtual_pinball`, BCP, config | **this repository** (`knowledge/mpf.md`) |
| Godot, GDE GoZen, native video, GMC, MPF Monitor, their versions and patches | **this repository** (`fixes/<component>/`, one file each, with an upstream draft) |
| A platform or board: Windows, macOS, Linux, Jetson, Raspberry Pi, video decoders, drivers, kernel modules, sound and screens, VideoCore / V4L2, frame rates, installers and images | **this repository** (`platforms/`) |
| One game's status, owner decisions and values | that game's repository |

A finding that spans both (for example a PuP Pack that needs a decoder fix) is written once, in the repository that owns the topic, and the
other gets a one-line pointer to it. Agents C to G (`agents/`) report every game-agnostic learning here in the same session, without being asked: a pull request with write access, otherwise an issue opened directly. New fix: copy `fixes/TEMPLATE.md`, then run
`python fixes/make_index.py`; platform findings go in the platform's page under "Findings" or in a page listed in
`platforms/README.md`. Run `python -m pytest -q tests` before pushing. Never commit a ROM or private material.

**No game content here.** This repository holds no game: no recipe, no bundle spec, no file list, no URL, no name of a game or of its
PuP Pack. The method documents in `agents/` and `knowledge/` (and `tools/pup/`) may cite a worked example (a game's name and repository link); everything else may not. The game's repository (or the session that creates the game) produces a complete game package and describes it in its own
`bundle_spec.json` (`common/games/README.md`, "What the game provides"); this repository only turns that package into a bundle. The
provenance of a finding ("found on game X") is fine in `fixes/` and `platforms/`. `tests/test_no_game_content.py` enforces it.
