# native_video build report (M7-B10/B11/B13)
Date 2026-09-30. Agent: Video playback debug agent. Upstream repro / root-cause text: `docs/qa/native_video_bug_repro.md` (ready to paste into an issue).

## Result
- Root cause: gdzig `engine_allocator` (`vendor/gdzig/src/heap.zig`) under-allocates aligned blocks (alignment 2, i.e. any u16 slice such as the wide path in `mf_backend.openInner`) and the NUL terminator overruns the block by 2 bytes. Outcome depends on path length / heap layout.
- Fix: padding = alignment + 4 in `alloc` and `remap` (+ payload move in `remap`). File: `tools/native_video_build/gdzig_heap_fixed.zig` (replacement for gdzig `src/heap.zig` at commit 14458fb).
- Installed in `godot/addons/native_video/`: `native_video.windows.debug.x86_64.dll` and `...release.x86_64.dll` rebuilt from v0.3.1 (6d51d93) + the fix (x86_32, arm64 and macOS files untouched, not used here). `native_video.gdextension`: debug key points at the debug DLL again (interim release override removed).

## Numbers (non-headless, fresh process per run)
| Configuration | Bad runs of 80 |
|---|---|
| Shipped debug DLL (before) | 24 (panic) |
| Shipped release DLL (before) | 21 (OpenFailed) |
| Release DLL mapped as debug ("interim", re-measured) | 24 (13 heap-corruption exits 0xC0000374, 11 playing=false) |
| **Patched debug DLL (installed)** | **0 (80 of 80 playing=true)** |

Unpatched self-built debug DLL: crash in the first 1-3 runs of "StartGame 1". Patched debug: 40 of 40 (StartGame 1, ZEN), then 80 of 80 (all clips, project smoke).
Live session: `run_batch1.py --attempts 1`: 12/12 modules PASS, 0 native_video crashes (was 55/55 crashes), including "media_bg_main background video is playing". Log `logs/godot_qa/batch1_20260930_215703.json`.

## How to rebuild
1. Sources: github.com/claytercek/godot-native-video @ 6d51d93 (tag v0.3.1) plus the `vendor/gdzig` submodule (claytercek/gdzig @ 14458fb; the source archive ships it EMPTY, download it separately). Replace `vendor/gdzig/src/heap.zig` with `tools/native_video_build/gdzig_heap_fixed.zig`.
2. Zig 0.16.0 (windows x86_64 zip, ~97 MB); put it on PATH (bindgen spawns `zig fmt`).
3. A Godot 4.6.x console exe for bindgen (4.7.2's `extension_api.json` fails to parse in gdzig's bindgen). Use `-Dgodot-path`; the `-Dgodot-version` fetch fails behind the proxy.
4. `zig build -Doptimize=Debug -Dtarget=x86_64-windows-gnu -Dgodot-path=<Godot_4.6 console exe>` and again with `-Doptimize=ReleaseFast`; output `project/lib/native_video.dll`, copy to the two x86_64 DLL names. The unpatched ReleaseFast build is byte-size identical (872448) to the shipped DLL, confirming the toolchain matches upstream.
5. Godot 4.7.2 loads the 4.6-API extension fine (compatibility_minimum 4.6).

## Remaining risk
- The fix is in a dependency (gdzig); DLLs are a local build until upstream merges it. Updating the addon from a new upstream zip reintroduces the bug until upstream fixes gdzig.
- `media_video_slide.gd` `_start_clip()` retry helper kept (harmless, a 0.3 s timer per clip start); with the fixed DLL no retry was needed in the suites. May be removed later by the Godot developer.
- Sample: 80 + 40 smoke opens and one live suite, all green. No 32-bit/arm64 DLLs rebuilt.
- Scratch dir `C:\qa_nv` (222 MB: Zig, Godot 4.6, sources) could not be deleted by this agent (path protected); delete it manually.

## macOS (2026-10-04)
The macOS dylibs are rebuilt from the same sources with the same fix by `.github/workflows/native_video_macos.yml` (the fix file: `pup_addons/native_video_build/heap.zig`).
