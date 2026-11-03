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

You need an MPF machine folder with a Godot (GMC) project: `project.godot` and MPF's `config/` side by side, say in `~/my-machine`. The
bundle is **files and facts** (format 2, [platforms/game-bundles.md](../../platforms/game-bundles.md)): it carries no start command
and no script; the platform launches the game itself (`python -m mpf_godot run game -c <configs>`) and applies its settings.

```sh
godot --headless --path ~/my-machine --import          # once: the machine does not import at its first start
python3 common/games/make_bundle.py ~/my-machine --id my-machine --name "My machine" --version 1.0 \
        --hardware virtual=hw_virtual --hardware proc=hw_proc --keep data -o dist/
# dist/my-machine@1.0.tar.xz  and  dist/my-machine@1.0.tar.xz.sha256
```

1. `--configs` (default `config`) are the MPF config files of `config/` always loaded.
2. **Virtual or P-ROC**: each `--hardware NAME=FILE[,FILE]` is a set of extra config files of `config/` (`hw_virtual.yaml` with
   `hardware: platform: virtual`, `hw_proc.yaml` with `platform: p_roc`, ...). Two sets or more give a *Hardware* setting on the page
   (default `virtual`); the platform adds the chosen set to `--configs`. Without `--hardware` your configs name the platform themselves.
3. `--keep PATH` lists what an update carries over to the next version: the files your game *writes* (settings, high scores, audits),
   relative to `game/`. `.platform/` (the page's settings, the PuP link and `MPF_GAME_DATA`, a writable folder of the game's own) is
   always kept.
4. Your own settings: `--settings settings.json`, a schema in your folder (`groups`, `options`, each with one target: `godot_arg`,
   `ini` or `hardware`; the contract table in game-bundles.md). The platform stores the values and applies them at the start.
5. **Platform add-ons**: GoZen and the patched GMC come from the platform (`gde_gozen`, `mpf-gmc` by default, `--platform-addon` to
   choose); your own copies in `addons/` are left out. Optional facts: `--dmd-rom` (the Serum colourisation on a ZeDMD), `--pup-rom`
   and `--pup-manifest` (a game that reads a PuP Pack from `MPF_PUP_PACK`), `--arch`, `--description`, `--icon`.
6. The tool refuses a bundle that breaks the contract (`mpf_contract.problems`: no `project.godot`, a config file missing, a bad
   settings schema), and names what is missing.
7. Put the archive on the machine: upload it on the page (*Games*, *Add a game*), or copy it (and its `.sha256`) to `/data/inbox/` over
   SSH and reboot, or put it in the image before flashing (next section). It is checked, installed to `/opt/games/my-machine@1.0`
   and, if it is the first game, becomes the active one.

What the platform gives the game at start: `MPF_DMD_OUTPUT`, `MPF_PUP_PACK`, `MPF_ADDONS`, `MPF_BOARD`, `MPF_GAME_DATA`, and the Godot
user arguments of its settings (game-bundles.md, "What the game reads at start"). Your game **must write only inside its own folder**:
on a production image the root is read-only. Logs go to `game/logs/` (in RAM on a production image); everything you want to keep goes
under a path listed in `--keep` or in `MPF_GAME_DATA`.

Test it first on a PC: `python -m mpf_godot run ~/my-machine -c config,hw_virtual` is what the platform runs.
`python3 -m unittest tests.test_inject` shows the tool producing a bundle the loader installs.

A program that is not an MPF + Godot game (no `project.godot`) cannot be a format 2 bundle: the platform runs only MPF and Godot.

## Before flashing: `inject_image.py`

Pure Python 3.8+, standard library only: runs as it is on **Windows, macOS and Linux**, no root, no loop device, no extra tool to
install, no network. Download the image (`.img.xz` is read directly) and your files, then:

```sh
python3 common/games/inject_image.py x86-debian13-uefi.img.xz \
        --bundle my-game-1.4.tar.xz --pup pack.zip:my-game \
        --bundle my-machine@1.0.tar.xz -o x86-with-games.img        # Windows: py -3 common\games\inject_image.py ...
```

It copies the image and appends **one small FAT32 partition** labelled `MPFSEED` (GPT on x86, MBR on the Raspberry Pi 4) that holds
an `inbox/` folder with the files; nothing in the image's own partitions changes. At the first boot `mpf-persist` makes the
read/write data partition (`mpfdata`) in the free space of the card, copies the seed's inbox into it once, and
`mpf-netconfig-inbox.service` installs the files before the game starts; if anything fails the file goes to `/data/inbox/failed/`
with a log, visible from the page. Flash the result as usual (balenaEtcher, Raspberry Pi Imager, Rufus).

- `--bundle` (repeatable): the **first** one becomes the active game, the others are installed and wait to be chosen on the page.
- `--pup FILE:GAME`: the pack of that game (`my-game` or `my-game@1.4`). Without `:GAME` it goes to the active game.
- Works on the Raspberry Pi 4 image and on the x86 USB stick image (its installer copies the games to the disk it installs on). A Jetson
  is flashed with NVIDIA's tools, not from a disk image: copy the files to `/data/inbox` over SSH, or use the page.
- The seed holds the files as they are: a big pack or bundle makes a big image to flash (the tool prints the size), and a file is
  limited to 4 GiB (FAT32). Keep it for what must be there at the first boot and add the rest from the page. The space of the seed
  stays used; the card needs room after it for the data partition (at least 512 MB).
- Start again from the original image to change the content: an image that already carries a `MPFSEED` partition is refused.
- Checked end to end: the x86 image with a pinball game bundle booted under QEMU, made its data partition, imported and installed
  the game and made it the active one.

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
# dist/my-game-1.0.0-base-linux-all.tar.xz  and  ...tar.xz.sha256
```

With a URL it clones the game's repository into `~/mpf-game-builds/<id>` (`--workdir` changes it), runs its setup, builds, and checks.
Options: `--repo FOLDER` uses a clone you already made *as it is* (your branch, your changes: nothing is cloned or checked out),
`--repo URL` another remote, `--ref BRANCH_OR_TAG`, `--version 1.4.0 --label serum-zedmd` (name: `<id>-<version>-<label>-linux-<target>`; the commit is only in bundle.json), `--target arm64|x86_64|all`
(default `all`: one archive for every machine, no binary inside), `--skip-setup` when the workspace is already prepared (rebuilds
take minutes instead of the first run's 30 to 60), `--dry-run` to see the commands.

**Which branch.** The package is built from the game's **merged default branch**: the tool fetches `origin`, and refuses a commit that is not in it (or a clone with
local changes) unless you add `--allow-branch` for a test package. It prints `source: <branch> at <commit>`. A bundle built from an older work branch
once crashed in a loop on a machine because later fixes were missing.

**No recipe needed for the SAM games.** Without a recipe the tool follows their convention: `scripts/setup.py` (with `--no-monitor` when it
has that option), then `scripts/package/build_bundle.py` with `--out`, and `--target` / `--version` / `--label` only when that script's `--help` lists them,
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
3. **Build** (the game's `build`, or by convention `.venv/bin/python scripts/package/build_bundle.py --target all --version X.Y.Z --label L --out DIR`), which stages the game, makes the Godot
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
imports the textures and packs. The PuP Pack is never part of it: the author's zip, uploaded separately on the page.

1. **A complete package.** Every file the game needs at run time exists in the repository folder when the build starts, **generated files
   included** (config, media, sounds, baked fonts, generated slides and data tables that git ignores). The game's own setup or build
   step produces them, here nothing is generated. `mpf_godot bundle` stops and lists any path of the spec's `copy` that is missing
   (`optional` lists those that may be absent), and the check refuses a Godot project that uses `mpf-gmc` without the add-on.
2. **Facts, no command** (`"format": 2`, owner decision 2026-10-30): the bundle carries no start command, settings tool, install command or board script; the platform launches the game and applies its settings, profiles, PuP Pack and add-ons ([platforms/game-bundles.md](../../platforms/game-bundles.md), "The contract"). Format 1 below still builds for existing games until they move.
3. **`bundle_spec.json`** (or `game_package.json`, at the root or in `scripts/package/`) ([platforms/game-bundles.md](../../platforms/game-bundles.md), example in
   `examples/bundle/bundle_spec.json`, JSON schema in `schema/game_package.schema.json`, checked by `mpf_godot bundle`): id, files, exclusions, and the facts of format 2: `game_dir`, `mpf`, `dmd`, `pup` (`rom`, `manifest`), `addons`, `settings`, `profiles`, `platform_addons`, `keep_on_update`.
4. **Optionally `mpf-package.json`** at the repository root when the game is not built by the Stern SAM convention: `id` (what `bundle.json`
   must say), `submodules`, `tools`, `disk_gb`, `min_python`, `setup` (commands, run in the clone), `build` (the command;
   `{python} {version} {target} {out} {platform}` are replaced), `env`, `target`, `publish_folder`, `needs`.

The rule is enforced by `tests/test_no_game_content.py` (it fails on a game name, a recipes folder or a PuP Pack path outside `fixes/` and
`platforms/`) and stated in [CONTRIBUTING.md](../../CONTRIBUTING.md). For plain MPF
code (an MPF + Godot folder with no build step) use `make_bundle.py` above. `tests/test_build_game.py` runs the whole tool on a small game.

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
`sha256sum -c`; a `.sha256` next to the archive is checked too). `make_bundle.py` and `mpf_godot bundle` write both. A bundle with a
`format` the page does not know is refused.

**Format 2** (every new bundle): files and facts, no command. The keys, what the platform does with each, and what is refused are in
[platforms/game-bundles.md](../../platforms/game-bundles.md#the-contract-bundlejson-format-2); `common/netconfig/mpf_contract.py` reads
it. A bundle made by `make_bundle.py`:

```json
{
  "format": 2,
  "id": "my-machine",              // lowercase letters, digits, . _ - (at most 64): the folder name and what --pup names
  "name": "My machine",            // shown on the page
  "version": "1.0",                // letters, digits, . _ + - (at most 64)
  "description": "text shown under the name",
  "icon": "game/icon.png",         // optional, relative to the bundle's folder
  "target": {"os": "linux", "arch": "all"},        // all | arm64 | x86_64 | arm64+x86_64: refused on other machines
  "game_dir": "game",                              // project.godot and MPF's config/
  "mpf": {"configs": ["config"], "hardware": {"virtual": ["hw_virtual"], "proc": ["hw_proc"]}},
  "settings": {"schema": "settings.json"},         // the page's form; the Hardware setting picks a set of mpf.hardware
  "platform_addons": ["gde_gozen", "mpf-gmc"],     // add-ons taken from the platform (the same build for every game)
  "keep_on_update": ["game/data"]
}
```

| Field | Meaning |
|---|---|
| `keep_on_update` | paths (files or folders, relative to the bundle) carried from the previous version of the same game; `.platform/` always is |
| `platform_addons` | add-ons (`gde_gozen`: GoZen binaries for the machine; `mpf-gmc`: the patched GMC; `dmd_out`) that the platform installs instead of the bundle shipping them |
| `monitor` | optional `{"layout": "game/monitor/monitor.yaml", "image": "game/monitor/playfield.jpg"}` (these are the defaults): the game's MPF Monitor layout, drawn by the page's *Switch monitor* tab (playfield, switches, lamps); without it the tab lists the switches |

**Format 1** (`run.start`, `run.check`, `options.tool`, `pup.install`, `profiles.apply`, `requires.env`): bundles built before
2026-10-30 still install and start until they are rebuilt; nothing new is built in format 1, and a format 2 bundle with one of those
keys is refused.

### What the base system gives a game, and what it must leave alone

- **Environment**: `GODOT`, `MPF_GAME_VENV` (the Python environment with MPF), `DISPLAY`, and the `MPF_*` names of the contract. The
  names are fixed: a format 2 bundle cannot ask for others (`requires.env` is refused); format 1 bundles still get theirs.
- **Board settings**: the platform's Godot `override.cfg` (audio buffer, mix rate, frame cap of the machine) is copied to
  `game/override.cfg` at every install: set the board's FPS and audio there, not by command-line arguments that a game may not accept.
- **GMC is the platform's**: `platform_addons: ["gmc"]` is not a name; list **`"mpf-gmc"`** and the loader installs the platform's
  mpf-gmc 1.0.0 (the official release, with the three fixes of [fixes/gmc](../../fixes/README.md#gmc): half BCP lines, parse errors,
  AZERTY keys; made by `python -m mpf_godot patch-gmc` in the base system's `toolchain/addons/mpf-gmc`) into `game/addons/mpf-gmc`,
  replacing whatever the bundle brought. A game then does not ship GMC at all. A game with **its own extra GMC changes** keeps
  shipping its copy and does not list `mpf-gmc` (the platform's would overwrite them). The install is refused, not skipped, when
  the platform has no GMC.
- **GoZen is the platform's**: a bundle that lists `platform_addons: ["gde_gozen"]` gets the platform's build (VAAPI on x86, V4L2 on a Pi 4,
  NVMPI on a Jetson). The game ships no GoZen of its own, and the loader puts the platform's copy back after a
  PuP Pack install anyway. Keep the pack's videos as they are (H.264 plays on the GPU decoder): do not re-encode them to
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
