# Hand-off: x86 PC image with the Tron bundle in Serum colour (ZeDMD 128x32)

For the session that builds the x86 mini PC image ([#23](https://github.com/Ashram56/MPF-Godot-Packaging/pull/23)). Written 2026-10-30 at Vincent's request.

## Decision (Vincent, 2026-10-30)

**libserum and the whole colour pipeline are managed by the platform** (this repository and the image generator), not hand-built by a game session.
The image generator builds `zedmd_feed` and the game's `dmd_serum` colouriser (libserum linked in) as part of the image/toolchain and installs them,
declaring their build tools (git, CMake >= 3.25, a C++17 compiler; zig for another CPU) in `toolchain.py` like every other build dependency
(game-bundles rule 12: nothing is compiled or generated on the machine that plays).

## What to build from

| Part | Reference |
|---|---|
| Game | Tron-Legacy-MPF [PR #69](https://github.com/Ashram56/Tron-Legacy-MPF/pull/69), branch `claude/project-thread-34zlzp`, read at commit `0f6338a32f9d708932e64f0722b2cf113426588f` (2026-10-30 17:24 UTC; the PR is still moving, take its head when building and note the commit). Not merged: build with `--allow-branch` (a test package). |
| Colouriser | `game/native/dmd_serum/` of that PR (`dmd_serum.cpp`, `build.sh OUT [WORKDIR]`; libserum `v2.8.0`, libframeutil pinned in `build.sh`, GPL v2) |
| Feeder | this repository's plain `zedmd_feed` (PR [#32](https://github.com/Ashram56/MPF-Godot-Packaging/pull/32): SIGPIPE fix) |
| Pipeline | Godot add-on pipes the 128x32 frames to `dmd_serum`, which colours them with libserum, runs the rotations and pipes RGB to `zedmd_feed`. No Python or MPF on the picture path |

## Steps for the image generator

1. Build `zedmd_feed` and `dmd_serum` for `x86_64` (and `arm64` with zig) on the build box; put them where the game looks: `game/native/bin/<arch>/` of the installed game (or ship them in the image and point the game at them).
2. Build the Tron bundle with `common/games/build_game_package.py ~/tron-legacy-mpf --repo-branch 34zlzp --allow-branch --target x86_64 --pup-zip <author's PuP Pack zip>` (the game's `scripts/package/build_bundle.py` also builds the two programs when `game/native/bin/<arch>` is empty).
3. The player brings the Serum file: **`DIR/trn_174h/trn_174h.cROMc`**, never in git or in the bundle. Start with `run.py --zedmd --zedmd-serum DIR`.
4. Install the bundle through the page, then `common/games/check_installed.sh 60`.

## Known limits (from PR #69)

- Incomplete sequences are accepted: the game's DMD is not yet conformant with PinMAME (66.9 % of PinMAME's frames found; attract and coin pages 0 %). Frames Serum does not know stay in Tron blue. The table and method are in `docs/dmd_conformance.md` of the PR.
- Not run on a real ZeDMD; the arm64 zig cross build is not tried.
- A session continues to work on PR #69: do not edit it; open a note on it if something is missing.
