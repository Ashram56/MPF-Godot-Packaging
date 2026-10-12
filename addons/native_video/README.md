# native_video, patched: OS video decoding for Godot on macOS and Windows

[godot-native-video](https://github.com/claytercek/godot-native-video) plays MP4/MOV (H.264, HEVC) through the
operating system's decoder: AVFoundation on macOS, Media Foundation on Windows. It is a drop-in `VideoStream` for
Godot's `VideoStreamPlayer` (`NativeVideoStream`). It needs Godot 4.6+ and a RenderingDevice renderer (Forward+ or
Mobile); the Compatibility (OpenGL) renderer is not supported.

This copy is upstream v0.3.1 (`6d51d93`) rebuilt with one fix. Use it on macOS, where GDE GoZen has no build; on
Windows [`../gde_gozen/`](../gde_gozen/) is the default (GPU decoding, and native_video stuttered there in our use),
and native_video is the fallback.

## How it differs from upstream

| Change | Fix document |
|---|---|
| gdzig's allocator overran aligned blocks: video opens failed, panicked or corrupted the heap depending on the path length | [gdzig-heap-overrun](../../fixes/native-video/gdzig-heap-overrun.md) (upstream [#26](https://github.com/claytercek/godot-native-video/issues/26)) |

Do not replace these files with an upstream release zip until upstream ships the fix.

## Files and platforms

| File | Platform | Built |
|---|---|---|
| `libnative_video.macos.debug.dylib`, `libnative_video.macos.release.dylib` | macOS universal (arm64 + x86_64) | with the fix |
| `native_video.windows.debug.x86_64.dll`, `native_video.windows.release.x86_64.dll` | Windows x86_64 | with the fix |
| `native_video.windows.*.x86_32.dll`, `native_video.windows.*.arm64.dll` | Windows x86 and arm64 | upstream v0.3.1, without the fix |
| `native_video.gdextension` | maps each platform and build to its binary | - |

Upstream's limits apply: no Compatibility renderer, nothing drawn under `--headless`, HEVC on Windows only with a
decoder installed (the "HEVC Video Extensions" package), single-precision Godot builds only.

## Install into a game

    python -m mpf_godot addons GAME --video

Besides the patched GMC, it copies this folder to `GAME/addons/native_video/` on macOS and Windows, and GDE GoZen on
Linux and Windows. Load a
video with `NativeVideoStream` (or `load()` on an `.mp4`, `.mov`, `.m4v` file) into a `VideoStreamPlayer`.

## Rebuild

[`../../build/native_video/README.md`](../../build/native_video/README.md): the v0.3.1 sources, gdzig `14458fb` with
[`../../build/native_video/heap.zig`](../../build/native_video/heap.zig) in place of `src/heap.zig`, Zig 0.16.0, and a
Godot 4.6 console binary for bindgen. Windows DLLs are built by hand; the macOS dylibs by a GitHub Actions workflow
that is not ported to this repository yet.

## Licence

MIT, Copyright (c) 2024 Clay Tercek (`LICENSE`). gdzig is a build dependency compiled into the binaries.
