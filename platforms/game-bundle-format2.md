# Making a game's bundle in format 2: instructions for the game's session

For the session (human or Claude) that owns a game repository and must make its bundle follow the format 2 contract
([game-bundles.md](game-bundles.md), "The contract"). Owner decision 2026-10-30: **a bundle is files and facts; the platform runs
everything.** Read this page whole before changing the game; the contract table in game-bundles.md is the reference for each key.

## 1. What changes, in one table

| Format 1 (today) | Format 2 (to do) |
|---|---|
| `run.start` runs the game's `start.py`, which adds saved options to `run.py` | removed: the platform runs `python -m mpf_godot run <game_dir> -c <configs> -- <engine> -- <user args>` |
| `run.check` | removed: the platform checks the declared files and the imports of every `.py` under `game_dir` |
| `options.tool` + `options.json` (`target.arg` = a `run.py` flag) | `settings.schema`: the same file, each option with one target `godot_arg`, `ini` or `hardware`; the platform stores the values and applies them |
| `extra.profiles` with `apply` / `detect` commands | `profiles.<board>`: `limits`, `defaults`, `godot_args` as data; the platform detects the board (`rpi4`, `rpi5`, `jetson`, `x86`) |
| `pup.install` / `pup.status` / `pack_dir` / `media_dir` / `extract_only` | `pup`: `rom` and `manifest` only; the page unpacks the author's zip untouched, the game gets `MPF_PUP_PACK` |
| a media folder made from the pack and shipped in the bundle (copied mp3/png, converted files, a still) | nothing of the pack in the bundle: the game reads the pack in place |
| HD art made from the pack at each build (`--pup-zip`) | an **add-on**: made once, stored in a repository (private for art derived from a third-party pack), copied as it is into `addons/<id>/` |
| the game detects a PIN2DMD or ZeDMD, adds `--zedmd-feed`, opens the serial port | removed: the platform chooses the output, starts `dmd_bridge`, passes `--zedmd=`/`--pin2dmd=`, sets `MPF_DMD_OUTPUT` |
| `requires.env` (`<GAME>_VENV`, ...) | removed: fixed names only (`MPF_GAME_VENV`, `GODOT`, `MPF_*`) |

## 2. Steps in the game repository

1. **Spec.** In `bundle_spec.json` (or the dict the game's `build_bundle.py` writes): `"format": 2`, `game_dir`, and the facts:
   `mpf.configs` (the base configs), `mpf.hardware` (one entry per hardware choice: `{"virtual": ["hw_virtual"], "proc": ["hw_proc"]}`;
   a model or board variant is one more set, e.g. `"proc_le": ["hw_proc", "model_le"]`), `dmd.rom` (the PinMAME set name, the
   default Serum colourisation), `pup` (`rom`, `manifest`), `addons`, `settings.schema`, `profiles`. Remove `run`, `options`,
   `extra`, `requires.env` and every command key of `pup`. Keep `platform_addons` (`gde_gozen`, `mpf-gmc` or the game's own GMC,
   `dmd_out` when the game drives a PIN2DMD or ZeDMD) and `keep_on_update` (cabinet data only: scores, audits, the game's own ini
   files). `.platform/` is always kept, do not list it.
2. **Settings.** Turn the options file into the settings schema (same `groups` / `options`, same ids so the operators' choices keep
   their meaning). For each option pick its target:
   - a value Godot reads: `{"godot_arg": "--dmd-tint"}`; the game gets `--dmd-tint=blue` as a user argument
     (`OS.get_cmdline_user_args()`); bools come as `true` / `false`;
   - a key of an ini file the game reads: `{"ini": "game/pup.local.cfg", "section": "pup", "key": "ost_music"}`; the platform
     writes it before each start, the other keys of the file stay;
   - the MPF hardware: `{"hardware": true}` with the names of `mpf.hardware` as choices.
   A `run.py` flag that was neither a Godot argument nor an ini key (free play, the machine model, MPF options) becomes an MPF
   config set of `mpf.hardware` or a config file of `mpf.configs`, or a Godot argument the game forwards to MPF itself through BCP.
   Nothing is translated by a script of the game.
3. **Board profiles.** Copy each board's limits and defaults into `profiles` as data, keyed by the platform's board names. What a
   board cannot run (an HD DMD on a Raspberry Pi 4) is a `limits` entry; the platform narrows the page's choices and replaces a saved
   value the board cannot run by the profile's default at the start.
4. **Start path.** Godot and MPF must start with only what the platform gives: no start script, no generator, no device
   detection. Remove from the bundle's start path the start script, the DMD-device detection module and its import of the
   platform, any `--zedmd-feed` the game composes, `auto` DMD-window modes that probe a device. Godot reads `MPF_DMD_OUTPUT`: `lcd`
   shows the DMD on the screen, `pin2dmd` / `zedmd` render the classic 128x32 DMD in the root viewport for `dmd_out` and show no DMD
   window. The game's MPF configs never open a DMD serial port. The game's `run.py` stays for the one-line Mac/PC install; the
   platform never calls it.
5. **PuP Pack.** The PuP player takes the pack folder from `MPF_PUP_PACK` (PuP off when it is absent or has no `triggers.pup`) and
   reads its own manifest from the bundle (`pup.manifest`). It plays the pack's videos with GoZen and loads its music and pictures
   from the pack folder at run time. Delete the code that copies or converts the pack into a media folder and the check that turns
   the PuP off when that folder's manifest is missing. The tool that writes the manifest may read the pack (a zip given at the
   build, or the private submodule); the manifest lists files (path, size, length, size in pixels), never their content.
6. **Add-ons.** Everything made for the game beyond its base assets, including art cut or derived from the PuP Pack (DMD clips,
   letters, award icons, a still for the service menu), is made once by the game's tools, **outside the build**, and committed as
   assets to a repository: a private one for anything derived from a third-party pack, checked out as a submodule. The build copies the
   folder into `addons/<id>/` and lists it in `addons` (`setting` / `when`: the setting that switches it on, e.g. `dmd.mode` = `hd`).
   At run time the game finds its add-ons in `MPF_ADDONS` (folders separated by `:`) and falls back to its base assets (the ROM's
   animations) for one that is absent. A build without access to the private repository gives a bundle without that add-on: the
   builder drops the entry and says so.
7. **Build.** The build stages, imports and packs; it **generates nothing** (no art, no conversion, no settings tool) and runs no
   command of the game but its own build script. `python -m mpf_godot bundle SPEC --target all` stops when the contract is broken
   (`mpf_contract.problems`: a command key, a declared file missing).
8. **Check without a machine:** unpack the archive and run, from this repository,
   `python3 -c "import sys; sys.path.insert(0,'common/netconfig'); import json, mpf_contract as K; b=json.load(open('DIR/bundle.json')); print(K.problems(b, 'DIR') or 'ok'); print(K.plan('DIR', b, 'x86'))"`:
   it prints the configs, Godot arguments, ini keys and environment the platform would use. Then install it on a machine and run
   `common/games/check_installed.sh 60` (rule 11). Do not deliver a bundle from a branch (rules 1 and 10).

## 3. What the platform gives the game at start

| Name | Value |
|---|---|
| `MPF_DMD_OUTPUT` | `lcd`, `pin2dmd` or `zedmd` |
| `MPF_PUP_PACK` | the assigned pack, unpacked untouched; absent without one |
| `MPF_ADDONS` | the folders of the add-ons switched on |
| `MPF_BOARD` | `rpi4`, `rpi5`, `jetson`, `x86`, `arm64` |
| `MPF_GAME_DATA` | a writable folder for the game (`<game>/.platform/data`, kept by updates) |
| `MPF_GAME_VENV`, `GODOT`, `DISPLAY`, the sound variables | as before |
| Godot user arguments | the board's, the profile's `godot_args`, the `godot_arg` settings, then the DMD output's |
| MPF configs | `mpf.configs` + the `mpf.hardware` set of the `hardware` setting (default `virtual`) |

## 4. Report back

When the game is ported, its session updates its game page (status, the bundle's format) and reports to this repository anything
the contract could not express (a PR on this page or on `common/netconfig/mpf_contract.py`), instead of adding a command to the bundle.
