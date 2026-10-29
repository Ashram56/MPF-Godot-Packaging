# Game bundles: what a game builds, what this platform installs

One platform image, one game bundle. The split is the same for every game:

| Part | Made by | Contains |
|---|---|---|
| **Platform** (this repository) | `install/`, `platforms/*/image`, `python -m mpf_godot setup` | Python with MPF, Godot, ffmpeg, the display stack, the setup web page (`common/netconfig`), **every binary add-on** (`addons/gde_gozen` for arm64, x86_64, Windows; `native_video`), the patched GMC |
| **Game bundle** (the game's repository) | the game's `build_bundle.py` | the MPF machine folder, the Godot project, sounds, DMD frames and fonts, the Godot import already made: code and multimedia only, **no binary** |

The binaries stay identical for every game; a game never ships its own copy.

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
4. **Write `bundle.json`** (format 1: `id`, `name`, `version`, `target` with `arch` `arm64`, `x86_64` or `arm64+x86_64`
   and `texture_formats`, `source` commit, `requires`, `run`, `options`, `keep_on_update`, `platform_addons`) and
   **`SHA256SUMS`**, pack as `<id>-<version>-linux-<target>.tar.xz` with a `.sha256` next to it.
`game/.godot` (the import) is packed on purpose; the version defaults to `YYYY.MM.DD-<short commit>`; `requires.godot` is this platform's pinned Godot.
5. **Check** with `xz -t`, `tar -xJOf ARCHIVE <id>/bundle.json`, and that no `libgozen` is in a universal archive.

A game can have its own builder (by convention `scripts/package/build_bundle.py` in its repository), which adds its
runner scripts, option schema, board profiles and a PuP install; a game that needs more than the spec says can do the
same around this one. A small update is a zip of the changed files plus `REMOVED.txt`, made from two bundles' `SHA256SUMS`.

## Rules every prebuilt bundle follows

They are the same for every game, each one comes from a bundle that installed fine and then crashed in a loop on a machine
(observed 2026-10-29: `mpf-game.service` restarted 22 times). `build_game_package.py` checks the ones a tool can check.

| # | Rule | Why, and what breaks without it |
|---|---|---|
| 1 | **Build only from the game's merged default branch** (`main`), never from a work branch. The tool refuses otherwise (`--allow-branch` for a test package) and prints the branch and commit. | The fixes of a game live on branches until they are merged. A bundle built from an older branch lacks them: the bundle that looped was built from a branch that was 5 fixes behind. |
| 2 | **A bundle never regenerates anything at start.** The game's launcher must see `bundle.json` (a bundle) and skip every generator: no "are the media current?" step, nothing that empties `game/media`. | The bundle has the generated files but not the generators' inputs (the ROM extraction). A launcher that regenerates finds the inputs missing, fails, and has already emptied the media: crash loop. |
| 3 | **Ship the files the media fingerprint reads** (names tables, font lists, image lists) so that the stamp inside the bundle matches. | A fingerprint over files that are not in the bundle can never match, which triggers rule 2's failure even if regeneration is skipped for the wrong reason. |
| 4 | **`platform_addons` lists `gde_gozen` and `mpf-gmc`** unless the game ships its own patched GMC (then it lists only `gde_gozen`). The tool refuses a project that uses `mpf-gmc` when neither is true. | No GMC means no BCP server: Godot starts, MPF never connects. |
| 5 | **The game's GMC patch step accepts the platform's patched GMC** (the tag of the platform's patch counts as patched) and never re-patches or replaces it. | The platform installs its GMC after the unpack; a game that patches again breaks it. |
| 6 | **Read the Python venv from `MPF_GAME_VENV`** and declare any other name in `requires.env`; take Godot options only if `run.game_args` is true. | The service forwards those names only. A launcher that rejects Godot options crashes when `MPF_GAME_ARGS` is set. |
| 7 | **Never convert the PuP videos** and never replace `game/addons/gde_gozen` in the pack's install command. | The platform's GoZen decodes H.264 on the GPU; Theora forces software decoding. |
| 8 | **List every Python file the start chain reaches** in the game's `copy` or `git_tracked`: the start script, what it imports at the top of a file, what it launches by name. The builder and the page both run `mpf_bundlecheck.py` on the unpacked archive and refuse one where an import cannot be found. | A script imported by `start.py` was missing from the game's list (observed 2026-10-29): `ModuleNotFoundError`, the service restarted every 10 s. Nothing in the game's own tests saw it because they only read the imports of one file, not of the files it imports. |
| 9 | **Give the game a `run.check`** when its start needs more than imports (a file read at start, a config): a command that exits 0 when the game can start, in a few seconds, with no display. | The import check cannot see a missing table or a bad config; the game's own check can. |
| 10 | **Deliver a bundle only from a commit that is on the remote default branch.** The tool refuses a commit that is not (`--allow-branch` makes a test package that is not delivered). | A bundle built from an unpushed commit cannot be rebuilt or fixed by anyone else (observed 2026-10-29). |
| 11 | **Install the archive on a machine and watch it run** before calling it done: `common/games/check_installed.sh 60` (the service stays active, no restart). A build that "checks" has not been run. | Every item above was invisible to the build's own checks. |
| 12 | **A tool the game runs on the machine (to make media from the PuP Pack, to build art) declares its Python packages** in `bundle.json` `requires.python_packages`; the platform installs them: numpy is in the toolchain's `REQUIREMENTS` (every platform's venv) and the page's installer pip-installs the bundle's list into `MPF_GAME_VENV` (best effort, logged). A game must not pip-install into its own folder. | A PC with a clean venv (`pip install mpf` has no numpy) failed to make the HD letters and clips: the game fell back to the dot animations (Tron, 2026-10-29). |

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
| HD DMD shows the dot animations and ROM letters on a machine, the PuP clips on the builder (2026-10-29) | The art made from the PuP Pack (clips, letters) needs numpy and lived inside the pack-install folder that a library pack reuse replaced; a clean venv has no numpy | Rule 12; the game keeps the made art beside the pack and remakes it at start |

What a bundle that cannot start does on a machine: the page's installer unpacks it, runs `mpf_bundlecheck.py` and the game's
`run.check`, and **refuses it before touching anything**: the installed game stays the active one, the message says what is missing.

## Installing (the platform's side)

The setup web page (`common/netconfig/mpf_netconfig.py`, upload field "Game bundle") does, in order: verify the
`.sha256`; unpack; reject a bundle whose `target.os` or `arch` (split on `+`) does not match the machine; `sha256sum -c`;
**check that it can start** (`mpf_bundlecheck.py` and `run.check`; a failure refuses the bundle and leaves everything as it was);
move the previous install's `keep_on_update` paths into the new tree; swap folders; **install each add-on listed
in `platform_addons` from this platform's `addons/<name>`, only the binaries of this machine**
(`MPF_PLATFORM_DIR`, default found from the netconfig file or from `MPF_GOZEN_SO`); replace the Pi's GoZen with a
board-specific build when `MPF_GOZEN_SO` is set; apply the board profile and first-run defaults.

Same thing by hand: `python -m mpf_godot addons GAME --video` copies the patched GMC and GoZen into a game folder.

## The game's PuP Pack

The pack is the author's zip, never in a bundle. A game that has a PuP integration (Stern-SAM-Decryption `agents/pup_pack.md`)
declares in `bundle.json` how to install it; the setup page's "PuP Pack" upload calls that command in the installed game:

```json
"pup": {"install": "python3 scripts/pup/pup_setup.py --pup-zip ZIP_PATH_OR_URL",
        "pack_dir": "pup_pack/mygame", "needs_restart": true}
```

`ZIP_PATH_OR_URL` is replaced by the uploaded zip, `pack_dir` (relative to the game) tells the page whether a pack is installed
(it then sets `pup.enabled`), and `pup_pack`, `pup_media` belong in `keep_on_update`. The page reads the settings tool
from `options.tool`, the start command from `run.start` and the environment names to forward from `requires.env`
(`MPF_GAME_VENV` names the game's Python venv), so nothing in the page is specific to a game.

## Platform or game

| Platform (this repository, the same for every game) | Game (its repository, built with `bundle_spec.json`) |
|---|---|
| Python, MPF, Godot, ffmpeg, display stack, kernel and board work | MPF machine config, rules, DMD frames, sounds, fonts |
| GoZen and native_video binaries, patched GMC, the setup page, `mpf_godot bundle` | `bundle_spec.json`, the settings schema and tool, board profiles (`profiles` in `bundle.json`) |
| Board limits and fixes (`platforms/`, `fixes/`) | the PuP integration code and its install command; the pack itself comes from its author |

## Checklist for a new game

- [ ] A `bundle_spec.json` at the game's root; the build refuses cabinet data and packs no binary.
- [ ] `bundle.json` lists `platform_addons`; the add-on exists in this repository's `addons/`.
- [ ] Installed once on each architecture's real machine (the unit tests do not prove a GPU).
