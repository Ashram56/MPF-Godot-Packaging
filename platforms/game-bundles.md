# Game bundles: what a game builds, what this platform installs

One platform image, one game bundle. The split is the same for every game:

| Part | Made by | Contains |
|---|---|---|
| **Platform** (this repository) | `install/`, `platforms/*/image`, `python -m mpf_godot setup` | Python with MPF, Godot, ffmpeg, the display stack, the setup web page (`common/netconfig`), **every binary add-on** (`addons/gde_gozen` for arm64, x86_64, Windows; `native_video`), the patched GMC |
| **Game bundle** (the game's repository) | the game's `build_bundle.py` | the MPF machine folder, the Godot project, sounds, DMD frames and fonts, the Godot import already made: code and multimedia only, **no binary** |

The binaries stay identical for every game; a game never ships its own copy.

## Building a bundle (the game's side)

Done on any PC where the game's own setup has finished (the generated media must be current). Tron's builder is the
worked example (Tron-Legacy-MPF `scripts/package/build_bundle.py`, `docs/bundle.md`):

```sh
python scripts/package/build_bundle.py --target all        # universal: arm64 + x86_64, no binary
python scripts/package/build_bundle.py --target x86_64     # one architecture (embeds the add-ons; see below)
python scripts/package/build_bundle.py --version 2026.10.28 --out DIR
```

1. **Stage** the tracked game files plus the generated config, media, sounds and baked fonts into `<name>/`. Never
   cabinet data (`data`, `audits`, `logs`, `*.local.cfg`, `options.json`): the builder refuses to finish if any is there.
2. **Seed and run the Godot import** (`godot --headless --path game --import`) so the machine does not. The VRAM
   texture format depends on the GPU: ARM GPUs (Pi 4, Jetson) take ETC2/ASTC, PCs S3TC/BPTC. `--target all` imports
   **both** (the converted textures are the big part, about 300 MB packed for Tron; `.godot/imported` keeps both
   sets and the `.import` files list both formats), so one archive installs anywhere.
3. **Leave the binaries out** (`--target all`, or `--platform-addons`) and say so in `bundle.json`:
   `"platform_addons": ["gde_gozen"]`. Without the flag, a single-architecture bundle still embeds its GoZen build
   (the older Pi flow).
4. **Write `bundle.json`** (format 1): `id`, `name`, `version`, `target` (`os: linux`, `arch`: `arm64`, `x86_64` or
   `arm64+x86_64`, `texture_formats`), `source` commits, `requires`, `run.start`, `options`, `keep_on_update`
   (what an update must not overwrite: scores, audits, options, local credentials), `platform_addons`.
5. **Write `SHA256SUMS`** for every file, pack as `<id>-<version>-linux-<arch|all>.tar.xz` with a `.sha256` next to
   it. Check with `xz -t`, and that `bundle.json` and no `libgozen` are in a universal archive.

A small update is a zip of the changed files plus `REMOVED.txt`, built from two bundles' `SHA256SUMS`.

## Installing (the platform's side)

The setup web page (`common/netconfig/mpf_netconfig.py`, upload field "Game bundle") does, in order: verify the
`.sha256`; unpack; reject a bundle whose `target.os` or `arch` (split on `+`) does not match the machine; `sha256sum -c`;
move the previous install's `keep_on_update` paths into the new tree; swap folders; **install each add-on listed
in `platform_addons` from this platform's `addons/<name>`, only the binaries of this machine**
(`MPF_PLATFORM_DIR`, default found from the netconfig file or from `MPF_GOZEN_SO`); replace the Pi's GoZen with a
board-specific build when `MPF_GOZEN_SO` is set; apply the board profile and first-run defaults.

Same thing by hand: `python -m mpf_godot addons GAME --video` copies the patched GMC and GoZen into a game folder.

## Checklist for a new game

- [ ] The game's builder follows steps 1-5 and has a test that no cabinet data and (universal) no binary is packed.
- [ ] `bundle.json` lists `platform_addons`; the add-on exists in this repository's `addons/`.
- [ ] Installed once on each architecture's real machine (the unit tests do not prove a GPU).
