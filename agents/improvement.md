# Agent E: improvements (optional)

> **Feed back what you learn.** Whatever game you run this agent on, report every game-agnostic learning to
> Ashram56/MPF-Godot-Packaging (this repository) in the same session, without being asked: a pull request if you
> have write access, otherwise a GitHub issue opened directly. How and what: [CONTRIBUTING.md](../CONTRIBUTING.md).
> **Route it:** MPF implementation learnings (rules, display, sound, VPX bridge, PuP, install kit, Godot, GoZen,
> GMC, MPF, platforms and boards) stay here. Taking a ROM or a VPX table apart (formats, decompile, traces, IO
> tables) goes to [Ashram56/Stern-SAM-Decryption](https://github.com/Ashram56/Stern-SAM-Decryption) instead (its
> CONTRIBUTING.md), with at most a pointer here.

Make the recreated game look, sound or play better than the ROM **without losing the original**: an HD
display, cleaner fonts, colour, new modes, desktop conveniences. Runs only after the
[strict recreation](recreation.md) works, and never changes what that agent guarantees. Part of the
[master plan](README.md) (A to G in full: [Stern-SAM-Decryption `agents/README.md`](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/agents/README.md)). Tron is the worked example. File paths in `code` are the Tron game repo's ([Tron-Legacy-MPF](https://github.com/Ashram56/Tron-Legacy-MPF)) unless said otherwise.

## 1. Rules

1. **Switchable, with the ROM one option away.** Every improvement is a mode or an option (command-line flag,
   environment variable, Godot project setting or MPF setting); the ROM's behaviour stays reachable.
2. **Classic stays byte-exact.** The 128x32 classic output, the render captures and the real-hardware DMD
   (P-ROC) are always classic. Pixel-hash tests guard classic frames; re-take a hash only after rendering the
   same frames on the base branch and seeing them agree.
3. **Every departure gets a row in the game repo's `docs/rom_differences.md`** in the same commit: what the
   ROM does, what the game does, why, and the switch back. Rules changes and new modes also get their own
   tests and must not change any ROM scenario; new modes go in their own feature module.
4. **Same layout as the ROM** for display work: glyph advances and positions are the ROM's; only the
   rendering changes. No learned upscaler, no network at build time: deterministic and offline.
5. **The owner judges the look.** Offer a default, show before/after pictures, keep the alternatives as
   options. Record each decision below with its date.
6. **Third-party colourisation and anything else with third-party rights stays in the private repo**
   (Tron: `Ashram56/Tron-Legacy-MPF-Private`); public repos, this one included, only point there. Its agent notes are in that
   repo's `docs/agents/colorization.md`. Don't name the third-party tools or packs here.

## 2. The HD display (built)

How it works, game agnostic: [dmd_hd_upscaling.md](../knowledge/dmd_hd_upscaling.md). In short: frames
upscaled shade by shade (level sets) at build time; ROM fonts traced to vector outlines; by default text in
a clean TrueType font at the ROM's positions (MSDF, sharp at any size; its fields are baked once at setup by
`game/tools/bake_fonts.gd`, since Godot makes them on its main thread and froze a Jetson 20 s and more); text baked into recorded animations
found, cleared and redrawn live (`scripts/frame_text.py`); pictures that are only frames and blocks drawn as
rectangles. Mode precedence and options are in `game/tools/dmd_mode.gd`.

**Display options in the service menu** (Tron: ADJUSTMENTS > DISPLAY ADJUSTMENTS, text glow and size; MPF
`tron/settings.py` DisplaySettings, Godot `dmd_mode.gd` service_setting()). The operator edits them like the
ROM's adjustments, but they are the game's own items (added to a ROM menu at run time, a row in
`rom_differences.md`), not ROM adjustment numbers. MPF reaches Godot through machine variables: GMC already
monitors them (`monitor_start?category=machine_vars`: every value at connect, every change after), and
`MPF.game.machine_update` fires on each, so no extra BCP command is needed. Keep two variables per option: the
persisted operator value, and a live one, not persisted, that the display follows (-1 = the value the display
was started with, so command-line options still work until the operator changes it). The value being edited
goes to the live one at once, so the operator sees it on the menu text itself; BACK and leaving the screen put
the stored one back. Text nodes join a group and redraw on change; anything that draws at draw time from the
style (rather than caching it) then follows without more code. Test the Godot side with
`slide_capture.gd`'s `machine_vars` job key, which calls `MPF.game.update_machine` as GMC does.

Each game's current defaults and the way back to the ROM are on its game page (Tron:
[Tron-Legacy-MPF `docs/agents/README.md`](https://github.com/Ashram56/Tron-Legacy-MPF/blob/main/docs/agents/README.md), "E, improvements").

## 2a. Assets and loading: what keeps the HD display smooth

Measured on a Jetson Xavier NX (the slowest target; figures in Tron's [performance.md](https://github.com/Ashram56/Tron-Legacy-MPF/blob/main/docs/performance.md)), true on
every platform. The rule behind all of them: **a slide is created on Godot's main thread when MPF shows its
effect, so anything it loads or computes then stalls the whole game**. Move the work to build time, to setup, or
to worker threads at start-up.

| Finding | What to do (Tron) | Measured |
|---|---|---|
| Lossless HD frames decompress on the main thread when their slide loads (~7 ms per 1024x256 frame) | `scripts/gen_media.py` writes a VRAM-compressed `.import` for every HD effect frame (`HD_FRAME_IMPORT`: ETC2 on ARM, S3TC/BPTC on PCs; grey, so one channel) | ~1.5 ms per frame, half the GPU memory; 40.8 dB PSNR, no visible difference at 1280x320. Light Cycle multiball start 2.34 to 1.00 s |
| Letter sprites (`solid*`, `hollow*`) are read back to make their glow | Keep them lossless (no VRAM compression): the glow is made from their pixels | - |
| Large effects (300 frames) still took about 1 s to load when shown | Preload every effect with 40+ frames, plus its slide scene, on worker threads from start-up (`tron/dmd/preload_min_frames=40`, `game/tools/dmd_mode.gd`); 0 turns it off | Deff 86 0.89 s to under 0.1 s, about +200 MB memory |
| Preloading every effect (`preload_min_frames=1`) | Not kept | +130 MB video memory, start-up preload 11 to 16 s, and effects shown during the longer preload waited for it |
| Requesting every preload at once queued ahead of the game's own loads (first effect waited 2.5 s) | At most 8 background loads in flight, in effect order (`PRELOAD_IN_FLIGHT`) | - |
| Letter glows were made on the main thread at slide creation (texture read back, blurred in script), even with the glow off | None made with the glow off; with it on, made on worker threads from the files at start-up (`game/tron/letter_panel.gd` `start_glow()`); a worker never reads a texture back (that broke the separate render thread) | Deff 94 380 ms to 25-36 ms; slowest effect 0.56 to 0.19 s |
| MSDF clean fonts generate each glyph on the main thread when first drawn | Bake them at setup (`game/tools/bake_fonts.gd`, `game/fonts_ttf/baked/`), load them on worker threads at start-up (`rom_text_hd.gd` `load_baked()`) | Orbitron: 20-30 s freezes gone; renders pixel-identical |
| The clean fonts' wide copy (outline and glow, `WIDE_RANGE=192`) is the expensive one | Keep the range as small as the glow allows | Orbitron vs the ROM font: about +1 W, +450 MB memory, +150 MB video memory on a Xavier NX |
| Godot's pipeline cache was never saved (the save at exit fails with the separate render thread; a kill never saves) | `rendering/rendering_device/pipeline_cache/save_chunk_size_mb=0.1` in `game/project.godot`: saved as it grows | First-use stalls of new effects (1.4-4.7 s) gone from the second start |
| Rendering on the main thread | Godot's separate render thread is opt-in here (`run.py --render-thread` / `TRON_RENDER_THREAD=1`; never for the captures, opengl3): with Godot 4.5.2 and the DMD alone it was slower (54.3 vs 56.2 FPS, twice the late frames, glyph texture update errors). The PuP repo (Godot 4.6.3, three videos) turns it on (`thread_model=2`): main thread 54% to 29% of a core, +2 to 3 FPS. Measure again on each Godot upgrade | Here: +1.9 FPS off; PuP: +2 to 3 FPS on |
| Background loads got one worker thread on 4 cores | `threading/worker_pool/low_priority_thread_ratio=0.5` | Shorter stalls when several loads overlap |

**Finding what causes a hitch.** Godot's frame times (the perf probe's `frames.csv`, time since Godot started) and
MPF's log (wall clock) have no common clock. Search the offset (in 0.1 s steps over +-20 s) that puts the most
frames over 100 ms within 0.5 s after an MPF event, then rank event names by how many hitches they explain against
how often they fire, and compare with random times. On Tron (full game, Xavier NX mode 5, 2026-10-12) 67 of 68
hitches of 100-150 ms fell just after a `slide_deff_N_created` (15% for random times; offset 4.7 s), spread over
36 different effects, while video opens explained 11 (observed). Then time each step of a slide show in the game
itself: a `node_added` handler on the slide's root notes the time, its `ready` signal, the next `process_frame` and
`RenderingServer.frame_post_draw`; wrap the slide scripts' functions with timers summed per slide; and measure the
same process-to-drawn time at random moments as the baseline (Tron: 27.5 ms). Tron's results, full game:

| Found | Fix | Measured |
|---|---|---|
| GMC keeps each slide's PackedScene once loaded (`media.gd`), so repeat shows are not reloads: the cost is per show | Preloading the small effects too, after the large ones, and building their HD frames ahead helps first shows only | Hitches 68 to 46, slowest effect 0.26 to 0.11 s, +62 MB video memory |
| A ROM text `Label` whose glyphs are hidden in HD (a child draws the line) got `add_theme_font_override` / `_font_size_` / `_constant_` again at every update: each call re-themes the label and its children and re-shapes it | Apply the theme only where the label's own glyphs show (classic) | About 25 ms per slide; hitches 46 to 6-12, late frames 264 to 139-149 |
| What is left: a new slide's first frame on screen costs about 25 ms over a normal frame, unchanged with the glow off, the ROM fonts or no separate render thread | Not script time: reusing slides instead of creating them at each show (GMC) is the next lever | - |

A theme override on a Control is not a cheap setter: set it once, or only when its value changes (observed, Godot 4.6.3).

When adding media: a new kind of picture loaded by a slide gets a VRAM-compressed import unless a script reads its
pixels; a new effect with 40+ frames is preloaded automatically; a new font goes through `bake_fonts.gd`. After
changing any of these, run setup (media regeneration and font bake) before measuring.

## 2b. Scorbit and Wi-Fi from the service menu (built on Tron)

[Scorbit](https://scorbit.io) (live scores, claims, leaderboards) through its SDK, and a Wi-Fi menu so a cabinet
can join a network with the coin-door buttons. Both are game items added to the ROM's service menu (a row in
`rom_differences.md`); nothing in play changes. Tron: `game/tron/scorbit.py`, `game/tron/network.py`, the
screens in `game/tron/service.py`, `docs/scorbit.md`, `docs/network.md`, `tests/test_network.py`.

| Fact (tag) | What to do |
|---|---|
| The SDK ([scorbit-io/scorbit_sdk](https://github.com/scorbit-io/scorbit_sdk), 2.0.4) is a pure-Python `ctypes` wrapper on PyPI (`scorbit`) plus a native library from the GitHub release of the **same** version; the release has Linux builds only (`scorbit_sdk-<v>-{amd64,arm64}_u18.tar.gz`, `armhf_u12`), no Windows or macOS (observed) | Install both from the packaging step behind an option (Tron: `setup.py --scorbit`, library flat in `tools/scorbit/lib`); point the wrapper at it with `SCORBIT_SDK_PATH` before `import scorbit`. The library needs only glibc. Elsewhere the game runs without it and the menu says why. |
| `create_game_state` **aborts the whole process** (`std::length_error`, uncatchable) when the encrypted key's base64 is cut short (a length not a multiple of 4); a well-formed wrong key only fails authentication (observed, SDK 2.0.4) | Check the key first: `base64.b64decode(key, validate=True)` and at least 44 bytes (salt 16 + IV 12 + tag 16, `source/utils/decrypt.cpp`); show `KEY IS NOT BASE64` instead of starting. |
| Credentials are per game maker: provider name, encrypted provider key, machine id (support@scorbit.io); the SDK then keeps a device key through save/load callbacks (code) | Never in a repo: a public `scorbit.cfg` with empty keys and a git-ignored `scorbit.local.cfg`; the device key in a 0600 file under git-ignored `data/`. |
| Callbacks (events, pair code, unpair) run on SDK threads; an `Event` is valid only during its callback (code) | Parse the event inside the callback into plain values behind a lock; the MPF clock reads them. Never touch MPF from an SDK thread. |
| The SDK diffs nothing for you: each `set_*` call is queued and `commit()` sends (code) | On the MPF clock (0.5 s), compare scores, active player, ball and modes with what was sent; call setters and one `commit()` only when something changed. `set_game_started` on MPF's `game_started`, `set_game_finished` (it commits) on `game_ended` after a last tick. Modes as `MB:<name>` for multiballs (the SDK's own example category). |
| Scorbit keeps the modes in each game's history: the active list (`add_mode` / `remove_mode`) is what was played; `set_mode_completed(name)` is a one-shot "completed" event for achievements, sent in the next commit only (code: `include/scorbit_sdk/game_state.h` on the SDK's master) | It is **not in SDK 2.0.4** (neither the wrapper nor the library): call it through `getattr(gs, "set_mode_completed", None)` and skip it when missing, so a later SDK sends completions with no game change. Send timed modes (hurry-ups, Find Flynn) as active modes while their clock task or end grace runs, not only the multiball flags. Take completions from the ROM's own "item collected" hook (Tron: the Find Flynn inserts), from audit counters going up between ticks, and from a "completed" game flag; skip item collections made by a wizard mode's stages (Tron: Sea of Simulation collects an item per stage). |
| The provider's private key (64 hex) is not what the SDK takes: `encrypted_key` is it encrypted by `encrypt_tool` with the provider name plus a secret compiled into Scorbit's ready-made library (code: `encrypt_tool/source/main.cpp`, `cmake/encrypt.cmake`); the public package has no `encrypt_tool`, and one built from source lacks the secret | Ask Scorbit support for the encrypted form; reject a 64-hex value in `encrypted_key` with a clear message. Keep both forms in a git-ignored local config, the public one empty. |
| The pairing deeplink is about 230 characters: its QR code (version 10, 57 modules) cannot fit a 32-dot DMD (code: `PAIRING_DEEPLINK`) | Use `request_pair_code`: a 6-character code for the Scorbit app, shown in a big ROM font. |
| Wi-Fi backends differ per cabinet: desktop Linux runs NetworkManager (`nmcli`), the Jetson image runs systemd-networkd + `wpa_supplicant@wlan0` with no NetworkManager (Tron's image build) | Pick at run time: `nmcli` when `/run/NetworkManager` exists, else `wpa_cli` on the first socket in `/run/wpa_supplicant`, else "not available". Run every call in a worker thread; the screen polls it on the MPF clock. |
| `wpa_cli` needs the control socket's group (`ctrl_interface=... GROUP=sudo`) and `update_config=1` to save; `nmcli` needs polkit outside a desktop session (inferred from the configs; not yet run on a cabinet) | With `wpa_cli`, hash the PSK yourself (`pbkdf2_hmac("sha1", pw, ssid, 4096, 32)`, as `wpa_passphrase`; test vector "password"/"IEEE" = `f42c6fc5...`) so the password is never on a command line or in the file; `select_network`, poll `status` for `COMPLETED`, then `enable_network all` and `save_config`; remove the network again if it failed (`4WAY_HANDSHAKE` seen = wrong password). |
| SAM ROM fonts have capitals only (Tron: all 44 fonts, no lower case) (observed) | Text entry for case-sensitive input (passwords): lower case as small capitals (a smaller ROM font) beside capitals, and a line naming the kind of the character being chosen (LOWER CASE, UPPER CASE, NUMBER, the symbol's name when no font has its glyph). MINUS / PLUS change it (held: auto-repeat), SELECT adds, BACK deletes, the flipper buttons jump between kinds, an END entry finishes. |

## 2c. Display scripts on a slow GPU: 3D backgrounds and video layers with overlays

Rules for the game's display code (its PuP runtime and 3D or video scenes), found by reading the code of a game with a live 3D background
behind its DMD, three video layers and a DMD overlay (desk analysis 2026-11-23, **not yet measured as a whole**; fact tags: code, observed,
inferred). They change the engine, the platform and the display scripts only, **never a game's content** (videos, pictures, look). What the
platform must provide (video copy paths, decoder threads, per-board budgets) is MPF-Godot-Packaging's
[platforms/render-guidelines.md](https://github.com/Ashram56/MPF-Godot-Packaging/blob/main/platforms/render-guidelines.md); the measurements of the Godot
canvas shader and `clip_children` are in its `fixes/godot/`.

| Rule | Why | In the worked game |
|---|---|---|
| **Render nothing under an opaque overlay.** Compute the visible rectangles; a 3D scene behind an opaque DMD is pure overdraw | the DMD covers about 42 % of the 3D background's pixels (code, `pup.cfg` shares 0.68 x 0.62) | render in bands around the DMD, or at least at half resolution (`--arena-res=half`) |
| **A background updates at its own rate.** `SubViewport.render_target_update_mode` on a timer (15-20 Hz); the UI, video and DMD stay at the frame cap | a background does not need 30 updates a second | the 3D arena renders every frame |
| **Layers are opaque; a covered layer is neither drawn nor decoded.** A layer with an alpha plane costs a read and a blend and keeps the layers under it alive | measured -3 to -8 % with a colour key on a Raspberry Pi 4 | `covers()` / `set_covered()` of `pup_screen.gd` already do it: keep it as the contract of any new layer |
| **No mesh rebuilt per frame.** A trail or ribbon is one mesh made once; its fade is computed in the shader from a birth-time attribute and a `now` uniform | `ImmediateMesh.clear_surfaces()` and 6 vertices per segment per frame, uploaded every frame (code) | the grid floor already animates in its shader with nothing per frame on the CPU: do the same for the trails |
| **A full-window procedural layer becomes the quads it needs.** A frame or border is a strip around the edge, not a window-sized rectangle with a fragment shader | a window-sized `ColorRect` pays its shader for every pixel (code) | the neon frame is one over the whole DMD window |
| **Few viewports, few passes.** Each `SubViewport`, `clip_children` and backbuffer read is a full pass on a tile-based GPU | +20 points of GPU for `clip_children` on a Pi 4 (observed) | do not add a post-processing viewport above the 3D |
| **Lights, fog, MSAA and glow are per-board options with a cheap default on ARM.** `unshaded` materials, MSAA off, no fog or lights, glow only where the renderer supports it | V3D and Mali implement 4x MSAA only (inferred); glow is a chain of full-frame passes; Compatibility glow support to check in the log | `--arena-msaa`, `--arena-res` exist; add the cadence and a light/none setting |
| **Declare the board's budget, not the scene's cost.** A profile says how many full-screen layers and what 3D quality it allows; a new scene follows the profile | one measurement per board replaces tuning every scene | `limits.md` of the platform |

Before adding a 3D scene or a layer: list which pixels it draws that an opaque layer later covers, how often it must update, and what it
allocates per frame (meshes, `Image`s, arrays). Check with the perf probe's frame times and the board's GPU counters, not the desktop's.

## 3. Owner decisions and ideas not built

Per game, on its game page, with dates (Tron: [Tron-Legacy-MPF `docs/agents/README.md`](https://github.com/Ashram56/Tron-Legacy-MPF/blob/main/docs/agents/README.md)).
Ask the owner before starting any idea listed there as not built.

## 4. Checks

`pytest -q tests` (includes `tests/test_dmd_hd.py`, `tests/test_dmd_text.py`), `scripts/render_check.py`,
and pictures at 1920x480 and 3840x960 for the owner (render through Xvfb with `--rendering-driver opengl3`;
`--headless` draws nothing). Bump `frame_text.VERSION` when the text matching changes (it keys the cache).

Last updated 2026-11-23 (section 2c, display scripts on a slow GPU; earlier: 2026-10-16 Scorbit and Wi-Fi from the service menu, section 2b; before: finding what causes a hitch; display options in the service menu; moved to Stern-SAM-Decryption; Tron defaults and decisions to the Tron game page).
