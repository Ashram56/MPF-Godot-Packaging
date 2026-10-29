# Games on the images: bundles, several versions, your own MPF code

An image is a **base system** (Python with MPF, Godot, GoZen, ffmpeg, the display stack, the setup page) and **games** that run on it.
A game is a **bundle**: one archive with a `bundle.json` that says everything the page needs. Nothing in the base system is specific
to a game, so the same image runs a Stern SAM recreation with its PuP Pack, another recreation, a different MPF machine, or your own
code with no PuP Pack at all.

| You want to | Do this |
|---|---|
| put the game and its PuP Pack **in the image before flashing** | [`inject_image.py`](#before-flashing-inject_imagepy) |
| load a game or a new version **on a running machine** | the page on port 8080 (*Games*), or drop the files in the inbox |
| **run your own MPF code** | [`make_bundle.py`](#your-own-mpf-code-without-a-pup-pack), then one of the two above |
| **build the package of a game** from its repository (a human, on a PC) | [`build_game_package.py`](#building-the-package-of-a-game-from-its-repository) |
| keep **several versions or games** and pick one | [Several games and versions](#several-games-and-versions) |

## Your own MPF code, without a PuP Pack

You need an MPF machine folder (`config/`, `modes/`, ...) or any program the base system can run. Say it is in `~/my-machine` and
starts with `mpf both` (MPF and the media controller on a screen) or with a launcher script of yours.

```sh
python3 common/games/make_bundle.py ~/my-machine --id my-machine --name "My machine" --version 1.0 \
        --start "mpf both" --keep data -o dist/
# dist/my-machine@1.0.tar.xz  and  dist/my-machine@1.0.tar.xz.sha256
```

1. `--start` is what runs the game, in the folder `game/` of the bundle (your folder is copied there). `python3` and `python` are the
   base system's Python environment with MPF installed; any other program name is looked up in that environment's `bin` first (`mpf`),
   then on the `PATH`. Several words are fine (`mpf both -t`, `python3 run.py --fullscreen`).
2. `--keep PATH` lists what an update carries over to the next version: the files your game *writes* (settings, high scores, audits),
   relative to `game/`. Everything else is replaced by the new version. Without `--keep` an update starts from a clean state.
3. **Virtual or P-ROC**: every bundle made this way gets a *Hardware* setting on the page, `virtual` (default) or `proc`. The bundle
   starts `scripts/package/start.py`, which runs your `--start` command plus `--hw-virtual-args=-x` (MPF's virtual platform) or
   `--hw-proc-args=...` (nothing by default: the hardware platform your config asks for; for example `--hw-proc-args="-c proc"` for
   an extra config file). The choice is kept in `settings/options.json` and carried over by updates. `--no-hw-option` leaves it out.
4. No `--pup-dir`: the bundle has no PuP Pack, the page shows no pack upload for it. Godot, GoZen and the media controller are not
   needed unless your game uses them. Use `--no-display` for a game that opens no window.
5. Put the archive on the machine: upload it on the page (*Games*, *Add a game*), or copy it (and its `.sha256`) to `/data/inbox/` over
   SSH and reboot, or put it in the image before flashing (next section). It is checked, installed to `/opt/games/my-machine@1.0`
   and, if it is the first game, becomes the active one.

What the base system provides to the command, as environment variables: `GODOT` (path to Godot, if the image has it),
`MPF_GAME_VENV` (the Python environment with MPF), `DISPLAY`. A bundle that wants them under another name lists it in `requires.env`.
Your game **must write only inside its own folder**: on a production image the root is read-only and only the games' folder and `/data`
are writable. Logs: write them to `game/logs/` (it is a link to RAM on a production image: they are lost at power-off, which is what
saves the flash); everything you want to keep goes under a path listed in `--keep`.

Test it first on a PC: `tar -xJf dist/my-machine@1.0.tar.xz && cd my-machine@1.0/game && mpf both` is the same command the image
will run. `python3 -m unittest tests.test_inject` shows the tool producing a bundle the loader accepts.

## Before flashing: `inject_image.py`

```sh
python3 common/games/inject_image.py rpi4-image.img \
        --bundle dist/my-game-1.4.tar.xz --pup ~/Downloads/pack.zip:my-game \
        --bundle dist/my-machine@1.0.tar.xz -o rpi4-with-games.img
```

It copies the image and appends **one partition** (`mpfdata`, the read/write data partition of the read-only mode)
that holds an `inbox/` folder with the files. Nothing in the image's own partitions changes, and no root, loop device or network is
needed. At the first boot the partition grows to the end of the card and `mpf-netconfig-inbox.service` installs the files before
the game starts; if anything fails the file goes to `/data/inbox/failed/` with a log, visible from the page.

- `--bundle` (repeatable): the **first** one becomes the active game, the others are installed and wait to be chosen on the page.
- `--pup FILE:GAME`: the pack of that game (`my-game` or `my-game@1.4`). Without `:GAME` it goes to the active game.
- Works on the Raspberry Pi 4 image and on the x86 USB stick image (its installer copies the games to the disk it installs on). A Jetson
  is flashed with NVIDIA's tools, not from a disk image: copy the files to `/data/inbox` over SSH, or use the page.
- A big pack or bundle makes a big partition and a big image to flash; the tool prints the size. Keep it for what must be there at
  the first boot and add the rest from the page.
- Start again from the original image to change the content: an image that already carries a data partition is refused.

## Building the package of a game from its repository

`build_game_package.py` makes the archive that the page installs, from a clone of the game's repository, in one command, and checks
it the way the page will. Needs Linux or WSL, `git`, `python3` 3.10+ and an internet connection; nothing else is installed by hand
(the game's own setup fetches Godot, MPF and what the game needs). Standard library only.

```sh
git clone https://github.com/Ashram56/MPF-Godot-Packaging && cd MPF-Godot-Packaging
python3 common/games/build_game_package.py https://example.com/my-game.git --out dist
```

**This repository knows no game.** The game comes with its own package description (see *What the game provides* below); nothing about a
game, its files or its build is kept here. **Which game?** The first argument says it, two ways: the **git URL of the game's repository**,
or a **folder** holding a clone:

```sh
python3 common/games/build_game_package.py https://example.com/my-game.git --out dist
python3 common/games/build_game_package.py ~/my-game --out dist      # your clone, your branch, as it is
# dist/my-game-<date>-<commit>-linux-all.tar.xz  and  ...tar.xz.sha256
```

With a URL it clones the game's repository into `~/mpf-game-builds/<id>` (`--workdir` changes it), runs its setup, builds, and checks.
Options: `--repo FOLDER` uses a clone you already made *as it is* (your branch, your changes: nothing is cloned or checked out),
`--repo URL` another remote, `--ref BRANCH_OR_TAG`, `--version 2026.10.29` (default: the date and the commit), `--target arm64|x86_64|all`
(default `all`: one archive for every machine, no binary inside), `--skip-setup` when the workspace is already prepared (rebuilds
take minutes instead of the first run's 30 to 60), `--dry-run` to see the commands.

**Which branch.** The package is built from the game's **merged default branch**: the tool fetches `origin`, and refuses a commit that is not in it (or a clone with
local changes) unless you add `--allow-branch` for a test package. It prints `source: <branch> at <commit>`. A bundle built from an older work branch
once crashed in a loop on a machine because later fixes were missing.

**No recipe needed for the SAM games.** Without a recipe the tool follows their convention: `scripts/setup.py` (with `--no-monitor` when it
has that option), then `scripts/package/build_bundle.py` with `--out`, and `--target` / `--version` only when that script's `--help` lists them,
else `bundle_spec.json` with `mpf_godot bundle`. The checks also refuse an archive whose `run.start` script is missing, or whose Godot project uses
`mpf-gmc` that neither the archive nor `platform_addons` provides.

**It assumes nothing is installed.** Before anything starts it checks what the run needs (Python's version and its `venv`/`xz` modules, `git` when it
has to clone, the tools the recipe lists, free disk space) and reports **everything missing at once**, with the install command for your system.
`--check` only does that check; `--install-deps` installs a missing git or `python3-venv` with apt (Debian, Ubuntu, Raspberry Pi OS; root or sudo).
**First run and `--skip-setup`.** The workspace is named after the recipe's `id` (`~/mpf-game-builds/<id>`), and `--skip-setup` only works on a workspace
that a full run already prepared. On a fresh one it fails late, with a bare `FileNotFoundError ... toolchain/godot/Godot_v...` from `mpf_godot bundle`: run once
without `--skip-setup`. The `id` of the game's `mpf-package.json` must equal the `id` of the spec it packs: the check
stops with `bundle.json id is X, the recipe says Y` after the whole build. While setting up a game with a private `pup_pack` submodule the log shows
`could not read Username ... Failed to clone 'pup_pack'`: expected without access, the game builds without the PuP Pack (it is never in the archive).
Be aware that git is needed for the whole build, not only for the clone: the game's own setup fetches its asset submodule with it and the
bundler stages the files git tracks (`mpf_godot bundle`), so a game's `mpf-package.json` lists `git` in `tools`.

What each step does, so it can also be done by hand:

1. **Get the repository** and its submodules (the game's `mpf-package.json` says whether it needs them).
2. **Setup** (the game's `setup`, or by convention `python3 scripts/setup.py --no-monitor`) in the clone: a Python venv with MPF, Godot, the generated
   MPF config, media, sounds and baked fonts. About 12 GB of disk; the longest step.
3. **Build** (the game's `build`, or by convention `.venv/bin/python scripts/package/build_bundle.py --target all --version V --out DIR`), which stages the game, makes the Godot
   import for both GPU families and writes `bundle.json` and `SHA256SUMS`. It uses this repository's `mpf_godot bundle` (the tool finds
   the checkout; the recipe sets `MPF_GODOT_PACKAGING`). Any game with a `bundle_spec.json` and no `build` is built with
   `python -m mpf_godot bundle bundle_spec.json` ([platforms/game-bundles.md](../../platforms/game-bundles.md)).
4. **Check**: the `.sha256`, `bundle.json` (format 1, the id the recipe says, a version, the target), that every platform add-on it names exists in this
   repository, that no cabinet data (`game/data`, `*.local.cfg`, logs) is inside and that a universal archive carries no GoZen binary. A failure stops with the reason.

Then put it on a machine: drop the file on the page (*Install and updates*), or `inject_image.py` (above) before flashing, or `--publish https://host/games`
(`WEBDAV_USER` and `WEBDAV_PASS` in the environment) which uploads the archive and its `.sha256` to `<URL>/<folder>/`, the layout of the page's
*Updates* card. The **PuP Pack is never in the archive**: it is the author's zip, uploaded separately (*Add a game or a PuP Pack*).

## What the game provides (the contract)

This repository holds **no game**: no recipe, no spec, no file list, no name. The game's own repository (or the session that creates the
game) produces a **complete game package** and describes it; this repository only checks the description, adds the platform's add-ons,
imports the textures and packs. The PuP Pack is never part of it (`pup.install`, installed separately).

1. **A complete package.** Every file the game needs at run time exists in the repository folder when the build starts, **generated files
   included** (config, media, sounds, baked fonts, generated slides and data tables that git ignores). The game's own setup or build
   step produces them, here nothing is generated. `mpf_godot bundle` stops and lists any path of the spec's `copy` that is missing
   (`optional` lists those that may be absent), and the check refuses a Godot project that uses `mpf-gmc` without the add-on.
2. **`bundle_spec.json`** (or `game_package.json`, at the root or in `scripts/package/`) ([platforms/game-bundles.md](../../platforms/game-bundles.md), example in
   `examples/bundle/bundle_spec.json`, JSON schema in `schema/game_package.schema.json`, checked by `mpf_godot bundle`): id, files, exclusions, `keep_on_update`, `requires`, `run`, `options`, `pup`, `platform_addons`.
3. **Optionally `mpf-package.json`** at the repository root when the game is not built by the Stern SAM convention: `id` (what `bundle.json`
   must say), `submodules`, `tools`, `disk_gb`, `min_python`, `setup` (commands, run in the clone), `build` (the command;
   `{python} {version} {target} {out} {platform}` are replaced), `env`, `target`, `publish_folder`, `needs`.

The rule is enforced by `tests/test_no_game_content.py` (it fails on a game name, a recipes folder or a PuP Pack path outside `fixes/` and
`platforms/`) and stated in [CONTRIBUTING.md](../../CONTRIBUTING.md). For plain MPF
code use `make_bundle.py` above. `tests/test_build_game.py` runs the whole tool on a small game.

Not checked by the tool: that the game *runs*. **Always install the archive on a machine and watch it** (page upload, then on the machine
`sh common/games/check_installed.sh 60`: the service must stay active for 60 s with no restart, else it prints the first errors). The rules
a bundle must follow so that it runs, with the reason for each, are in [platforms/game-bundles.md](../../platforms/game-bundles.md#rules-every-prebuilt-bundle-follows).

## Several games and versions

Every game lives in `/opt/games/<id>@<version>` (`/data/persist/games` on a production image). One is the **active game**: it is
what starts at power-on, what the page's settings card configures, and what a pack without a game name goes to.

- Installing a **new version** of a game keeps the old one: it stays in the list, and *Activate at startup* on the page goes back to it.
  The new version starts with a copy of the old one's settings and scores (`keep_on_update`) and **shares its PuP Pack** (hard links,
  one copy of the videos on the disk). An update of the *active* game becomes active at once.
- Installing **another game** (another `id`) leaves the active one alone: pick it on the page. Each game has its own folder, settings,
  scores and PuP Pack; a game without `pup` has none. Two games with different packs, or one with and one without, work the same way.
- Installing the **same version** again replaces it, keeping what `keep_on_update` lists.
- *Delete* on the page removes one version; the data of the others is untouched. The disk is the limit: the page refuses an upload that
  would not fit.

## Updates over the air (WebDAV)

The page's *Updates* card reads a WebDAV folder: one folder, or one sub-folder per game, holding `<id>@<version>.tar.xz` (+ `.sha256`)
and PuP Pack `.zip` files. The page asks for the server address and the folder separately (default `MPF Games`). Installing a bundle from
the list follows the rules above (new version kept beside the old one, settings, scores and pack carried over); a pack goes to the page's
PuP Pack library and is given to a game in the grid (common/netconfig/README.md). The page reads a `.json` on the server that lists
which updates fit which installed game, (`build_game_package.py --publish URL` writes it: `mpf-games.json` at the root of the folder: an entry
per game id, version and architecture, with the file, size and sha256; publishing the same version again replaces its entry). Without
it the file name or sub-folder (starting with the game's `id`) decides.

## The bundle

An archive (`tar -cJf`, `.tar.xz`) with **one top folder** of any name, holding `bundle.json` and, optionally, `SHA256SUMS` (checked with
`sha256sum -c`; a `.sha256` next to the archive is checked too). `make_bundle.py` writes both. A bundle with `format` above 1 is
refused by a page that does not know it.

```json
{
  "format": 1,
  "id": "my-machine",              // lowercase letters, digits, . _ - (at most 64): the folder name and what --pup names
  "name": "My machine",            // shown on the page
  "version": "1.0",                // letters, digits, . _ + - (at most 64)
  "description": "text shown under the name",
  "icon": "game/icon.png",         // optional, relative to the bundle's folder
  "target": {"os": "linux", "arch": "all"},        // all | arm64 | x86_64 | arm64+x86_64: refused on other machines
  "run": {"start": "mpf both", "cwd": "game", "needs_display": true},
  "requires": {"env": {"GODOT": "path to Godot"}},  // variables it reads; a name ending in VENV gets the venv folder
  "keep_on_update": ["game/data", "game/options.json"],
  "options": {"tool": "scripts/package/bundle_options.py", "schema": "scripts/package/options.json"},
  "pup": {"pack_dir": "pup_pack", "media_dir": "pup_media", "install": "python3 scripts/pup/pup_setup.py --pup-zip ZIP_PATH_OR_URL", "needs_restart": true},
  "platform_addons": ["gde_gozen", "mpf-gmc"],     // add-ons taken from the platform (the same build for every game)
  "gozen": {},                                      // what the bundle's own GoZen builds carry (v4l2m2m, zero_copy, vaapi...)
  "profiles": {"apply": "python3 scripts/package/board_profile.py install"}   // once per install: settings that suit this board
}
```

| Field | Meaning |
|---|---|
| `run.start` | the command (default `python3 scripts/package/start.py`); `run.cwd` its folder, relative to the bundle (default the bundle); `needs_display` false: do not wait for the X session |
| `run.check` | optional: a command (run in the bundle folder, `python3` meaning the game's venv Python) that exits 0 when the game can start, in a few seconds, with no display and nothing left running (`MPF_BUNDLE_CHECK=1` is set). The builder runs it on the extracted archive and the page before it installs; a failure refuses the bundle. `run.check_timeout`: seconds (default 90). Before it, both always check that every module the start script imports at the top of a file is in the bundle or importable by the game's Python (`common/netconfig/mpf_bundlecheck.py`) |
| `run.game_args` | `true`: the board's Godot arguments (`MPF_GAME_ARGS` of `/etc/default/mpf-game`, for example `-- --rendering-driver opengl3`) are added to `run.start`. Default: only for a game started by `scripts/package/start.py` (which forwards them), never for another command (it would reject them). `make_bundle.py --game-args` sets it |
| `keep_on_update` | paths (files or folders, relative to the bundle) carried from the previous version of the same game |
| `options.tool` | a program that answers `list` (the settings schema as JSON), `get`, `set ID VALUE...`, `unset ID...`: the page builds its form from it. No tool, no settings card. The page never writes a game's files itself |
| `pup` | present only if the game has a PuP Pack. `install` runs in the game's folder as the game user with `ZIP_PATH_OR_URL` replaced; `pack_dir` and `media_dir` are shared between versions |
| `platform_addons` | add-ons (`gde_gozen`: GoZen binaries for the machine; `mpf-gmc`: the patched GMC) that the platform installs instead of the bundle shipping them |
| `monitor` | optional `{"layout": "game/monitor/monitor.yaml", "image": "game/monitor/playfield.jpg"}` (these are the defaults): the game's MPF Monitor layout, drawn by the page's *Switch monitor* tab (playfield, switches, lamps); without it the tab lists the switches |
| `profiles.apply` | run once after the install; sets only what nobody set (the board's limits, see [platforms/README.md](../../platforms/README.md)) |

### What the base system gives a game, and what it must leave alone

- **Environment**: `GODOT`, `MPF_GAME_VENV` (the Python environment with MPF), `DISPLAY`, and every variable ending in `_VENV` of
  `/etc/default/mpf-game` (a platform can add `TF_VENV=...` for a game that reads that name). Names listed under `requires.env` that
  end in `VENV` receive the venv folder too. A game that reads another name for its Python should say so in `requires.env`, or read
  `MPF_GAME_VENV`, the standard name.
- **Board settings**: the platform's Godot `override.cfg` (audio buffer, mix rate, frame cap of the machine) is copied to
  `game/override.cfg` at every install: set the board's FPS and audio there, not by command-line arguments that a game may not accept.
- **GMC is the platform's**: `platform_addons: ["gmc"]` is not a name; list **`"mpf-gmc"`** and the loader installs the platform's
  mpf-gmc 1.0.0 (the official release, with the three fixes of [fixes/gmc](../../fixes/README.md#gmc): half BCP lines, parse errors,
  AZERTY keys; made by `python -m mpf_godot patch-gmc` in the base system's `toolchain/addons/mpf-gmc`) into `game/addons/mpf-gmc`,
  replacing whatever the bundle brought. A game then does not ship GMC at all. A game with **its own extra GMC changes** keeps
  shipping its copy and does not list `mpf-gmc` (the platform's would overwrite them). The install is refused, not skipped, when
  the platform has no GMC.
- **GoZen is the platform's**: a bundle that lists `platform_addons: ["gde_gozen"]` gets the platform's build (VAAPI on x86, V4L2 on a Pi 4,
  NVMPI on a Jetson). Its PuP Pack install command **must not delete or replace `game/addons/gde_gozen`**; the loader puts the platform's
  copy back after the pack install anyway. Keep the pack's videos as they are (H.264 plays on the GPU decoder): do not re-encode them to
  another codec such as Theora, that forces software decoding.

Anything else in `bundle.json` is the game's own: loaders ignore unknown keys.

## Files

| File | Role |
|---|---|
| `make_bundle.py` | a folder of your code → `<id>@<version>.tar.xz` + `.sha256` |
| `inject_image.py` | bundles and packs → an image, before flashing |
| `build_game_package.py` | a game's repository → its bundle, checked |
| `check_installed.sh` | on the machine: does the installed game stay up? |
| [`../netconfig/mpf_games.py`](../netconfig/mpf_games.py) | the loader: install, versions, active game, inbox, start and stop |
| `tests/test_games.py`, `tests/test_inject.py`, `tests/test_ota.py` | the loader's contract, the two tools and the WebDAV updates |
