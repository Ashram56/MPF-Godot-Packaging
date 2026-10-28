# Game bundles: what a game builds, what this platform installs

One platform image, one game bundle. The split is the same for every game:

| Part | Made by | Contains |
|---|---|---|
| **Platform** (this repository) | `install/`, `platforms/*/image`, `python -m mpf_godot setup` | Python with MPF, Godot, ffmpeg, the display stack, the setup web page (`common/netconfig`), **every binary add-on** (`addons/gde_gozen` for arm64, x86_64, Windows; `native_video`), the patched GMC |
| **Game bundle** (the game's repository) | the game's `build_bundle.py` | the MPF machine folder, the Godot project, sounds, DMD frames and fonts, the Godot import already made: code and multimedia only, **no binary** |

The binaries stay identical for every game; a game never ships its own copy.

## Building a bundle (the game's side)

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
   texture format depends on the GPU: ARM GPUs (Pi 4, Jetson) take ETC2/ASTC, PCs S3TC/BPTC. `--target all` keeps
   **both** (about 300 MB packed for Tron), so one archive installs anywhere; a single target drops the other
   format from every `.import` and deletes its `.ctex` (Godot imports the host's preferred format whatever the setting says).
3. **No binary:** `platform_addons` goes into `bundle.json`; nothing from `addons/` is packed except what the game tracks itself.
4. **Write `bundle.json`** (format 1: `id`, `name`, `version`, `target` with `arch` `arm64`, `x86_64` or `arm64+x86_64`
   and `texture_formats`, `source` commit, `requires`, `run`, `options`, `keep_on_update`, `platform_addons`) and
   **`SHA256SUMS`**, pack as `<id>-<version>-linux-<target>.tar.xz` with a `.sha256` next to it.
`game/.godot` (the import) is packed on purpose; the version defaults to `YYYY.MM.DD-<short commit>`; `requires.godot` is this platform's pinned Godot.
5. **Check** with `xz -t`, `tar -xJOf ARCHIVE <id>/bundle.json`, and that no `libgozen` is in a universal archive.

Tron also has its own builder (Tron-Legacy-MPF `scripts/package/build_bundle.py`, `docs/bundle.md`), which adds its
runner scripts, option schema, board profiles and a PuP install; a game that needs more than the spec says can do the
same around this one. A small update is a zip of the changed files plus `REMOVED.txt`, made from two bundles' `SHA256SUMS`.

## Installing (the platform's side)

The setup web page (`common/netconfig/mpf_netconfig.py`, upload field "Game bundle") does, in order: verify the
`.sha256`; unpack; reject a bundle whose `target.os` or `arch` (split on `+`) does not match the machine; `sha256sum -c`;
move the previous install's `keep_on_update` paths into the new tree; swap folders; **install each add-on listed
in `platform_addons` from this platform's `addons/<name>`, only the binaries of this machine**
(`MPF_PLATFORM_DIR`, default found from the netconfig file or from `MPF_GOZEN_SO`); replace the Pi's GoZen with a
board-specific build when `MPF_GOZEN_SO` is set; apply the board profile and first-run defaults.

Same thing by hand: `python -m mpf_godot addons GAME --video` copies the patched GMC and GoZen into a game folder.

## Checklist for a new game

- [ ] A `bundle_spec.json` at the game's root; the build refuses cabinet data and packs no binary.
- [ ] `bundle.json` lists `platform_addons`; the add-on exists in this repository's `addons/`.
- [ ] Installed once on each architecture's real machine (the unit tests do not prove a GPU).
