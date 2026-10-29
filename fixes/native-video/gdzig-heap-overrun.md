# Videos fail to open, or the app crashes, depending on the file path's length (native_video heap overrun)

| | |
|---|---|
| Id | `native-video/gdzig-heap-overrun` (this file: `fixes/native-video/gdzig-heap-overrun.md`) |
| Component | native_video |
| Kind | bug |
| Affected versions | godot-native-video v0.3.1 (`6d51d93`) with its `vendor/gdzig` submodule at `14458fb` (`src/heap.zig`); later releases not checked |
| Platforms | Windows x86_64 (seen: panics, `OpenFailed`, heap corruption); macOS dylibs rebuilt with the same fix as a precaution (the allocator is shared code) |
| Found on | a Windows game using native_video, 2026-09-30; carried into a Stern SAM recreation 2026-10-03 (Windows) and 2026-10-04 (macOS) |
| Fact | observed (bad opens out of 80 per build, below); code (the allocator's padding) |
| Our fix | [`../../build/native_video/heap.zig`](../../build/native_video/heap.zig), a replacement for gdzig's `src/heap.zig` at `14458fb`; binaries in [`../../addons/native_video/`](../../addons/native_video/) |
| Applied by | the committed binaries, copied by `python -m mpf_godot addons GAME --video` on Windows and macOS; rebuilt by hand ([`../../build/native_video/README.md`](../../build/native_video/README.md)) |
| Upstream | godot-native-video, https://github.com/claytercek/godot-native-video/issues; status: **reported: claytercek/godot-native-video#26** |

## Problem

Opening a video with the native_video add-on failed in some runs and not others, depending on the file path's length
and the heap layout. Fresh process per run, not headless, 80 runs each:

| Build | Bad runs of 80 |
|---|---|
| Shipped debug DLL | 24 (panic) |
| Shipped release DLL | 21 (`OpenFailed`) |
| Release DLL used for debug runs too | 24 (13 heap-corruption exits `0xC0000374`, 11 not playing) |
| Debug DLL rebuilt with the fix | 0 (80 of 80 playing) |

A self-built debug DLL without the fix crashed within the first 1 to 3 runs.

## Cause

gdzig's `engine_allocator` (`vendor/gdzig/src/heap.zig`) under-allocates aligned blocks. It reserves `alignment` extra
bytes for an aligned block, but the payload starts up to `alignment + 3` bytes in. With alignment 2 (any `u16` slice,
such as the wide file path built in `mf_backend.openInner`), the NUL terminator overruns the block by 2 bytes (code).

## Fix

`heap.zig` reserves `alignment + 4` bytes in `alloc` and `remap`, and `remap` moves the payload when the new block
aligns differently. It replaces `vendor/gdzig/src/heap.zig` before building.

Results with the fix (Windows, debug DLL): 40 of 40 opens of two clips, then 80 of 80 across all clips, and a
12-module game test suite with 0 native_video crashes (55 of 55 crashed before).

Built with the fix here:

- Windows x86_64 debug and release DLLs, by hand (Zig 0.16.0, `-Dtarget=x86_64-windows-gnu`). The unpatched
  ReleaseFast build is byte-size identical (872448) to the shipped DLL, so the toolchain matches upstream's. The
  x86_32 and arm64 DLLs are upstream's, not rebuilt.
- macOS universal dylibs, by a GitHub Actions workflow on a macOS runner (`.github/workflows/native_video_macos.yml`
  in the game's repository); not ported to this repository yet.

Updating the add-on from a new upstream zip brings the bug back until gdzig or the add-on ships the fix.

## How to check

1. Build v0.3.1 with and without `heap.zig` ([`../../build/native_video/README.md`](../../build/native_video/README.md)).
2. Open and play a video 80 times, a fresh Godot process each time, with paths of several lengths; count the runs
   that panic, fail to open or exit with `0xC0000374`.

## Upstream issue (draft, not filed)

Already filed: [claytercek/godot-native-video#26](https://github.com/claytercek/godot-native-video/issues/26). Nothing
more to send; add a comment there if a later release still carries gdzig `14458fb`'s allocator.

**Title:** (filed as #26)

**Body:**

```markdown
Already reported upstream: https://github.com/claytercek/godot-native-video/issues/26
```
