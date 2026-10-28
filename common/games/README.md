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
3. No `--pup-dir`: the bundle has no PuP Pack, the page shows no pack upload for it. Godot, GoZen and the media controller are not
   needed unless your game uses them. Use `--no-display` for a game that opens no window.
4. Put the archive on the machine: upload it on the page (*Games*, *Add a game*), or copy it (and its `.sha256`) to `/data/inbox/` over
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

It copies the image and appends **one partition** (`mpfdata`, the read/write data partition of the [read-only mode](../readonly/README.md))
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
  "platform_addons": ["gde_gozen"],                // binaries taken from the platform (the same build for every game)
  "gozen": {},                                      // what the bundle's own GoZen builds carry (v4l2m2m, zero_copy, vaapi...)
  "profiles": {"apply": "python3 scripts/package/board_profile.py install"}   // once per install: settings that suit this board
}
```

| Field | Meaning |
|---|---|
| `run.start` | the command (default `python3 scripts/package/start.py`); `run.cwd` its folder, relative to the bundle (default the bundle); `needs_display` false: do not wait for the X session |
| `keep_on_update` | paths (files or folders, relative to the bundle) carried from the previous version of the same game |
| `options.tool` | a program that answers `list` (the settings schema as JSON), `get`, `set ID VALUE...`, `unset ID...`: the page builds its form from it. No tool, no settings card. The page never writes a game's files itself |
| `pup` | present only if the game has a PuP Pack. `install` runs in the game's folder as the game user with `ZIP_PATH_OR_URL` replaced; `pack_dir` and `media_dir` are shared between versions |
| `platform_addons` | binary add-ons (`gde_gozen`) that the platform installs for the machine instead of shipping them in the bundle |
| `profiles.apply` | run once after the install; sets only what nobody set (the board's limits, see [platforms/README.md](../../platforms/README.md)) |

Anything else in `bundle.json` is the game's own: loaders ignore unknown keys.

## Files

| File | Role |
|---|---|
| `make_bundle.py` | a folder of your code → `<id>@<version>.tar.xz` + `.sha256` |
| `inject_image.py` | bundles and packs → an image, before flashing |
| [`../netconfig/mpf_games.py`](../netconfig/mpf_games.py) | the loader: install, versions, active game, inbox, start and stop |
| `tests/test_games.py`, `tests/test_inject.py` | the loader's contract and the two tools |
