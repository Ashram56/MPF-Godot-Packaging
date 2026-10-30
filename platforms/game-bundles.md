# Game bundles: what a game builds, what this platform runs

One platform image, one or more game bundles. **A bundle is files and facts; the platform runs everything.** No command, no
script name the platform would execute, is in a bundle (format 2, owner decision 2026-10-30). The split is the same for every game:

| Part | Made by | Contains |
|---|---|---|
| **Platform** (this repository) | `install/`, `platforms/*/image`, `python -m mpf_godot setup` | Python with MPF, Godot, ffmpeg, the display stack, the setup page (`common/netconfig`), **every binary add-on** (`addons/gde_gozen`, `dmd_out`, the patched GMC), libzedmd, libserum, `dmd_bridge`, and **the only launcher** (`mpf_godot run`, started by `mpf-game.service`) |
| **Game bundle** (the game's repository) | the game's build, then `mpf_godot bundle` | the MPF machine (config, modes, rules code), the Godot project with its import made, the game's base assets (DMD animations, fonts, call outs, sounds, the ROM's music when it has one), its **add-ons** (DMD assets made once and stored in a repository), the PuP **manifest** (never a file of the pack), and `bundle.json`: facts only |

The binaries stay identical for every game; a game never ships its own copy. A game's `run.py` (one-line install on a Mac or a PC) is
never called by the platform.

## The contract (bundle.json format 2)

How a game's session ports its bundle, step by step: [game-bundle-format2.md](game-bundle-format2.md). `common/netconfig/mpf_contract.py` reads it; `schema/game_package.schema.json` describes it; the builder and the page refuse a
format 2 bundle that breaks it (`mpf_contract.problems`).

```json
{
  "format": 2, "id": "mygame", "name": "My Game (Stern 20xx), MPF recreation", "version": "2026.11.02-ab12cd3",
  "target": {"os": "linux", "arch": "arm64+x86_64", "texture_formats": "both"},
  "game_dir": "game",
  "mpf": {"configs": ["config"], "hardware": {"virtual": ["hw_virtual"], "proc": ["hw_proc"]}},
  "dmd": {"rom": "mygame_100", "size": "128x32"},
  "pup": {"rom": "mygame_100", "manifest": "pup/manifest.json"},
  "addons": [{"id": "pup_art", "dir": "addons/pup_art", "setting": "dmd.mode", "when": "hd"}],
  "settings": {"schema": "settings.json"},
  "profiles": {"rpi4": {"limits": {"dmd.mode": ["classic"]}, "defaults": {"dmd.mode": "classic"}, "godot_args": ["--max-fps=30"]}},
  "platform_addons": ["gde_gozen", "mpf-gmc", "dmd_out"],
  "keep_on_update": ["game/data", "game/audits"]
}
```

| Key | What the platform does with it |
|---|---|
| `game_dir` | the folder with `project.godot` and MPF's `config/`: `python -m mpf_godot run <game_dir> -c <configs> -- <engine> -- <user>` |
| `mpf.configs`, `mpf.hardware` | the MPF config files; the set of `mpf.hardware` named by the `hardware` setting is added (default `virtual`) |
| `dmd.rom` | the default Serum colourisation of the game (the page's library) |
| `pup.manifest` | the game's list of the pack files it uses (path, size, length); the page only checks it is there |
| `addons` | folders of the bundle switched on by a setting (`setting` == `when`; no `setting`: always), given to the game in `MPF_ADDONS` |
| `settings.schema` | a JSON file: `groups` and `options` (`id`, `group`, `label`, `type` bool/choice/integer/number/string, `choices`, `min`, `max`, `default`, `target`); the page's form, values saved in `<game>/.platform/settings.json` |
| option `target` | exactly one of `{"godot_arg": "--name"}` (`--name=value` as a Godot user argument), `{"ini": "game/x.local.cfg", "section": "s", "key": "k"}` (written before the start), `{"hardware": true}` |
| `profiles.<board>` | `rpi4`, `rpi5`, `jetson`, `x86` (detected from the device tree; `MPF_BOARD` wins): `limits` narrow choices, `defaults` replace the schema's, `godot_args` come first |
| `keep_on_update` | paths carried to a new version; `.platform/` (settings, data, PuP link) always is |

**Not allowed** (a format 2 bundle with one is refused): `run`, `launch`, `options` (`tool`), `extra` (`profiles.apply`, `detect`),
`pup.install`, `pup.status`, `pup.pack_dir`, `pup.media_dir`, `pup.extract_only`, `requires.env`, anything in `profiles` but data.

**What the game reads at start** (fixed names, the same for every game):

| Variable / argument | Value | The game |
|---|---|---|
| `MPF_DMD_OUTPUT` | `lcd`, `pin2dmd`, `zedmd` | shows its DMD on the screen only for `lcd`; otherwise renders the exact 128x32 classic DMD in the root viewport (`dmd_out`) |
| `MPF_PUP_PACK` | the pack assigned on the page, unpacked as the author made it; absent without one | PuP on when it holds `triggers.pup`; plays the files in place (GoZen), never copies them |
| `MPF_ADDONS` | the folders of the add-ons switched on, `:`-separated | loads its add-ons from there, else its base assets |
| `MPF_BOARD`, `MPF_GAME_DATA` | the board; a writable folder of the game's own | optional |
| Godot user arguments | from `godot_arg` settings, the board, the DMD output (`--zedmd=`, `--pin2dmd=`, `--zedmd-feed=`) | `OS.get_cmdline_user_args()` |

The game detects no DMD device, opens no serial port (its MPF configs never do), composes no `--zedmd*` or `--pin2dmd*` argument,
starts no process and installs nothing.

**Add-ons.** Content made for the game that is not its base assets (HD art, clips, letters, a still for the service menu), including
art derived from a third-party PuP Pack, is **made once, offline, and stored as assets in a repository** (a private one for art taken
from a third-party pack). The build copies it into `addons/<id>/` of the bundle as it is: nothing is generated by the build or the
target. A build without access to that repository makes the bundle without the add-on (base assets only).

**Format 1** bundles (`run.start`, `options.tool`, `pup.install`) still install and start until they are rebuilt; nothing new is
built in format 1.

## Building a bundle (the game's side)

One command from a clone of the game's repository, with the checks: [common/games/README.md](../common/games/README.md#building-the-package-of-a-game-from-its-repository) (`build_game_package.py`). What follows is what it runs.

Run from this platform's checkout with `GODOT=/path/to/godot` (or after `mpf_godot setup`). Done on any PC where the game's own setup has finished (the generated config, media, sounds and fonts must be
current) and where this platform's toolchain is set up (`python -m mpf_godot setup`: the import needs its Godot).
The game describes itself in a small JSON spec at its repository root ([examples/bundle/bundle_spec.json](../examples/bundle/bundle_spec.json),
every key explained at the top of `mpf_godot/bundle.py`); the builder is the same for every game:

```sh
python -m mpf_godot bundle bundle_spec.json --target all          # universal: arm64 + x86_64, no binary
python -m mpf_godot bundle bundle_spec.json --target x86_64       # one architecture's textures only
python -m mpf_godot bundle bundle_spec.json --version 2026.10.28 --out DIR --no-archive
```

What it does, in order:

1. **Stage** the git-tracked files of `git_tracked` (minus `git_exclude`, by default `game/addons/`: add-ons come from the
   platform) plus the `copy` list (generated config, media, sounds, baked fonts, the few scripts and data the
   game reads at run time). Stops if a staged `never` path or a `never_names` pattern (cabinet data: `data`, `audits`, `logs`,
   `*.local.cfg`, `options.json`) is in the tree.
2. **Seed** the `.import` files the game generates but does not track (`import_seed`: the text of a Godot `.import` file, e.g. `[remap]`, `importer="texture"`, `type="CompressedTexture2D"`, `[params]`, `compress/mode=2`; `skip_prefixes` are file-name prefixes), so Godot imports them
   VRAM-compressed, then **import** (`godot --headless --import`, twice) so the machine does not. The VRAM
   **A texture is only VRAM compressed if its `.import` says `compress/mode=2`**: a game whose textures use Godot's
   default (lossless) import gets no S3TC/ETC2 variant, whatever the project setting says, and the bundle carries none (the
   builder warns). Tracked `.import` files: list their folders in `force_vram`; untracked ones: `import_seed`.
   The VRAM texture format depends on the GPU: ARM GPUs (Pi 4, Jetson) take ETC2/ASTC, PCs S3TC/BPTC. `--target all` keeps
   **both** (about 300 MB packed for a game with HD frames), so one archive installs anywhere; a single target drops the other
   format from every `.import` and deletes its `.ctex` (Godot imports the host's preferred format whatever the setting says).
3. **No binary:** `platform_addons` goes into `bundle.json`; nothing from `addons/` is packed except what the game tracks itself.
4. **Write `bundle.json`** (with `"format": 2` in the spec: `id`, `name`, `version`, `target` with `arch` `arm64`, `x86_64` or
   `arm64+x86_64` and `texture_formats`, `source` commit, `requires`, `keep_on_update`, `platform_addons`, and the facts of the
   contract above, copied as they are; it stops when `mpf_contract.problems` finds a command or a declared file missing) and
   **`SHA256SUMS`**, pack as `<id>-<version>-linux-<target>.tar.xz` with a `.sha256` next to it.
`game/.godot` (the import) is packed on purpose; the version defaults to `YYYY.MM.DD-<short commit>`; `requires.godot` is this platform's pinned Godot.
5. **Check** with `xz -t`, `tar -xJOf ARCHIVE <id>/bundle.json`, and that no `libgozen` is in a universal archive.

A game can have its own builder (by convention `scripts/package/build_bundle.py` in its repository) that writes the spec and
calls this one: it may read the PuP Pack to write `pup.manifest` and copy the game's add-ons from their repository, never generate
art or copy a file of the pack, and it adds no runner script, settings tool or install command (format 2). A small update is a zip of the changed files plus `REMOVED.txt`, made from two bundles' `SHA256SUMS`.

## Rules every prebuilt bundle follows

They are the same for every game, each one comes from a bundle that installed fine and then crashed in a loop on a machine
(observed 2026-10-29: `mpf-game.service` restarted 22 times). `build_game_package.py` checks the ones a tool can check.

| # | Rule | Why, and what breaks without it |
|---|---|---|
| 1 | **Build only from the game's merged default branch** (`main`), never from a work branch. The tool refuses otherwise (`--allow-branch` for a test package) and prints the branch and commit. | The fixes of a game live on branches until they are merged. A bundle built from an older branch lacks them: the bundle that looped was built from a branch that was 5 fixes behind. |
| 2 | **A bundle never regenerates anything at start.** Nothing in the game's start (its Godot scripts, MPF code) checks that media are current or rebuilds them. | The bundle has the generated files but not the generators' inputs (the ROM extraction). A launcher that regenerated found the inputs missing, failed, and had already emptied the media: crash loop. |
| 3 | **Ship the files the media fingerprint reads** (names tables, font lists, image lists) so that the stamp inside the bundle matches. | A fingerprint over files that are not in the bundle can never match, which triggers rule 2's failure even if regeneration is skipped for the wrong reason. |
| 4 | **`platform_addons` lists `gde_gozen` and `mpf-gmc`** unless the game ships its own patched GMC (then it lists only `gde_gozen`). The tool refuses a project that uses `mpf-gmc` when neither is true. | No GMC means no BCP server: Godot starts, MPF never connects. |
| 5 | **The game's GMC patch step accepts the platform's patched GMC** (the tag of the platform's patch counts as patched) and never re-patches or replaces it. | The platform installs its GMC after the unpack; a game that patches again breaks it. |
| 6 | **Read only the platform's fixed names** (`MPF_GAME_VENV`, `GODOT`, `MPF_DMD_OUTPUT`, `MPF_PUP_PACK`, `MPF_ADDONS`, `MPF_BOARD`, `MPF_GAME_DATA`) and accept any Godot user argument the platform adds. Format 2 refuses `requires.env`. | A game that looked for its own variable names or rejected unknown arguments crashed when the platform added one. |
| 7 | **Never convert the PuP videos** and never replace `game/addons/gde_gozen` in the pack's install command. | The platform's GoZen decodes H.264 on the GPU; Theora forces software decoding. |
| 8 | **Ship every Python file the game's code imports.** Format 2: the builder and the page follow the top-level imports of every `.py` under `game_dir` (`mpf_bundlecheck.py`) and refuse a bundle where one cannot be found. | A script was missing from the game's list (observed 2026-10-29): `ModuleNotFoundError`, the service restarted every 10 s. |
| 9 | **Declare every file the start needs**: the configs of `mpf.configs` and `mpf.hardware`, the settings schema, the PuP manifest, the add-on folders. The builder and the page check they are there (`mpf_contract.missing_files`); no game command runs (format 1's `run.check` is gone). | A missing config only showed when MPF started on the machine. |
| 10 | **Deliver a bundle only from a commit that is on the remote default branch.** The tool refuses a commit that is not (`--allow-branch` makes a test package that is not delivered). | A bundle built from an unpushed commit cannot be rebuilt or fixed by anyone else (observed 2026-10-29). |
| 11 | **Install the archive on a machine and watch it run** before calling it done: `common/games/check_installed.sh 60` (the service stays active, no restart). A build that "checks" has not been run. | Every item above was invisible to the build's own checks. |
| 12 | **Nothing runs on the target to generate anything**, and **the build generates nothing either**: the build copies files. No pip, no media generation, no processing of a PuP Pack's media, at the start, at the install of a bundle or of a pack, or in the build. The build may read the PuP Pack only to write the game's manifest (`pup.manifest`: the list of the pack's files the game uses); no file of the pack, copied or converted, goes in the bundle. | A clean PC venv has no numpy, and art made on the machine into folders that a library pack reuse replaced showed the dot animations (2026-10-29). |
| 13 | **Everything extra made for a game is an add-on, made once and stored in a repository.** Any content made for a game beyond its base assets (HD art, clips, letters, stills, including art derived from a third-party PuP Pack) is made offline once, versioned as assets (a private repository for art derived from a third-party pack), and copied into `addons/<id>/` of the bundle by the build. The only things kept apart are what the owner downloads untouched from its author (a PuP Pack zip, a ROM) and what belongs to a cabinet (`keep_on_update`). (Owner decision 2026-10-30, replaces the 2026-10-29 rule that made the art at the build.) | Art made at each build depended on the build machine's tools and on the pack being there; art made on the target needed numpy and was lost when a pack was reused. |

## Known failures (symptom, cause, rule)

A new game's session reads this table before it builds. Each row comes from a real failure; add one when a new kind shows up.

| Symptom | Cause | Rule / what catches it now |
|---|---|---|
| `ModuleNotFoundError: No module named 'mpf_platform'`, service restarting every 10 s (2026-10-29) | A script (`dmd_out.py`) imported by the start script imports a module the game's `copy` list leaves out | Rule 8: `mpf_bundlecheck.py` in the builder (the build fails) and in the page (the bundle is refused, the running game stays) |
| Service restarts 22 times, `game/media` emptied | The launcher regenerated media at start, without the ROM extraction | Rules 2 and 3 |
| Godot starts, MPF never connects | `mpf-gmc` is neither in the bundle nor in `platform_addons` | Rule 4 (checked by the builder) |
| Fixes present in the repository are missing from the bundle | Built from a work branch, or from a commit that was never pushed | Rules 1 and 10 (the builder refuses) |
| `could not read Username ... Failed to clone 'pup_pack'` during setup | The PuP Pack submodule is private | Expected: the pack is never in the bundle (rule 7), installed from the author's zip |
| A bundle "checks" but does not run | Only the build's own checks were looked at | Rule 11: install it and run `check_installed.sh 60` |
| HD DMD shows the dot animations and ROM letters on a machine, the PuP clips on the builder (2026-10-29) | The art made from the PuP Pack was made on the machine (needs numpy, lived in folders a pack reuse replaced) | Rule 12: made offline at the build, shipped in the bundle, nothing made on the target |

What a bundle that cannot start does on a machine: the page's installer unpacks it, runs `mpf_bundlecheck.py` and the game's
`run.check`, and **refuses it before touching anything**: the installed game stays the active one, the message says what is missing.

## Installing (the platform's side)

The setup web page (`common/netconfig/mpf_netconfig.py`, upload field "Game bundle") does, in order: verify the
`.sha256`; unpack; reject a bundle whose `target.os` or `arch` (split on `+`) does not match the machine; `sha256sum -c`;
**check that it can start** (format 2: `mpf_contract.problems` and the imports of every `.py` of `game_dir`; format 1: `mpf_bundlecheck.py`
and `run.check`; a failure refuses the bundle and leaves everything as it was);
move the previous install's `keep_on_update` paths into the new tree; swap folders; **install each add-on listed
in `platform_addons` from this platform's `addons/<name>`, only the binaries of this machine**
(`MPF_PLATFORM_DIR`, default found from the netconfig file or from `MPF_GOZEN_SO`); replace the Pi's GoZen with a
board-specific build when `MPF_GOZEN_SO` is set. Format 2 has nothing more to run: the board profile is applied at each start.

**On the images** (x86, Raspberry Pi 4 and 5, Jetson) the page's modules are `common/netconfig/mpf_*.py` copied to `/usr/local/bin`
(so `mpf_contract.py` comes with them) and the platform's checkout is `~/MPF-Godot` of the game user: the page finds it without
`MPF_PLATFORM_DIR` (`mpf_common.find_platform_dir`) and starts format 2 games with its `mpf_godot` package. An image built before
format 2 needs the page updated (`common/netconfig/update_page.sh`) or a new image to install a format 2 bundle; it still runs format 1.

Same thing by hand: `python -m mpf_godot addons GAME --video` copies the patched GMC and GoZen into a game folder.

## The game's PuP Pack

The pack is the author's zip, never in a bundle. The page keeps a library of packs (upload, or the inbox `<id>.pup.zip`), and
assigning one to a format 2 game **only unpacks it** (the folder holding `triggers.pup`, at any depth) into the library and links it at
`<game>/.platform/pup`: no command of the game runs. At the start the platform sets `MPF_PUP_PACK` to it; without a pack the variable
is absent and the game plays without PuP. A format 1 game's `pup.install` command still runs for that game until it is rebuilt.

## Who launches the game, and the DMD output

`mpf-game.service` runs `mpf_games.game_exec`: for a format 2 bundle `contract_command` composes
`python -m mpf_godot run <game_dir> -c <configs> [launcher options of the board] -- <Godot engine options of the board> -- <Godot user arguments>`,
the user arguments being, in order, the board's (`MPF_GAME_ARGS` after its second `--`), the profile's `godot_args`, the settings'
`godot_arg` values, then the DMD output's. The platform chooses the DMD display (setup page > "Sortie DMD": auto, LCD, PIN2DMD,
ZeDMD) and the Serum colourisation of each game (default: the one named `dmd.rom`); libzedmd, libserum (unmodified PPUC) and
`dmd_bridge` are the platform's. For ZeDMD it adds `--zedmd=#RRGGBB --zedmd-shades --zedmd-feed=<dmd_bridge> --zedmd-feed-arg=...`; for
PIN2DMD `--pin2dmd=#RRGGBB`; and it sets `MPF_DMD_OUTPUT`.

The game: loads the platform's `addons/dmd_out` (installed from `platform_addons`); with `--zedmd` or `--pin2dmd` renders its exact
classic 128x32 DMD in the root viewport, 16 shades identical to the ROM (Serum matches the ROM's frames; HD or redrawn text does not);
shows its DMD on the screen only for `MPF_DMD_OUTPUT=lcd`. It ships no Serum code, feeder, `zedmd_feed` binary or ZeDMD setting, and
its MPF configs never open a DMD serial port.

Test on a machine: output ZeDMD, colourisation assigned, restart the game: `ps` shows dmd_bridge `--color ... --serum-lib ... --rom <rom>
--altcolor /data/serum --shades` and "serum: <rom> loaded (version 2, 16 shades)"; "no colour" gives `--color ... --shades` only.

## Platform or game

| Platform (this repository, the same for every game) | Game (its repository, built with `bundle_spec.json`) |
|---|---|
| Python, MPF, Godot, ffmpeg, display stack, kernel and board work | MPF machine config, rules, DMD frames, sounds, fonts, the ROM's music |
| The launcher, the board detection, settings storage and the page's form, the DMD output (bridge, libzedmd, Serum), the sound output | the settings schema and board profiles as data, the MPF hardware config sets |
| GoZen binaries, patched GMC, `dmd_out`, `mpf_godot bundle` | its add-ons (made once, stored in a repository), the PuP manifest |
| The PuP Pack library: upload, unpack untouched, assign, `MPF_PUP_PACK` | the PuP player code that reads the pack in place; the pack comes from its author |

## Checklist for a new game

- [ ] A `bundle_spec.json` at the game's root with `"format": 2`: facts only, no command; the build refuses cabinet data and packs no binary.
- [ ] Every setting has one target (`godot_arg`, `ini`, `hardware`); the game reads the platform's variables, detects no device.
- [ ] `bundle.json` lists `platform_addons`; the add-on exists in this repository's `addons/`.
- [ ] Installed once on each architecture's real machine (the unit tests do not prove a GPU).
