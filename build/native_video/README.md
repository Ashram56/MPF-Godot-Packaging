# native_video build fix

`heap.zig` replaces `vendor/gdzig/src/heap.zig` (gdzig `14458fb`) in
[godot-native-video](https://github.com/claytercek/godot-native-video) v0.3.1 (`6d51d93`). gdzig's `engine_allocator`
reserved `alignment` extra bytes for an aligned block, but the payload starts up to `alignment + 3` bytes in, so the
end of a `u16` string (the file path) overran the block. The fix reserves `alignment + 4` and, in `remap`, moves the
payload when the new block aligns differently. Why, and the measurements:
[`../../fixes/native-video/gdzig-heap-overrun.md`](../../fixes/native-video/gdzig-heap-overrun.md) (upstream
[issue 26](https://github.com/claytercek/godot-native-video/issues/26)).

| Platform | Binaries in `../../addons/native_video/` | Built by |
|---|---|---|
| Windows x86_64 | `native_video.windows.{debug,release}.x86_64.dll` | by hand, steps below |
| macOS universal | `libnative_video.macos.{debug,release}.dylib` | a GitHub Actions workflow on a macOS runner: `.github/workflows/native_video_macos.yml` in the Tron-Legacy-MPF repository. Not ported here yet |
| Windows x86_32, arm64 | `native_video.windows.*.{x86_32,arm64}.dll` | upstream's v0.3.1 release, not rebuilt (without the fix) |

## Rebuild on Windows

1. Sources: github.com/claytercek/godot-native-video at `6d51d93` (tag v0.3.1), plus its `vendor/gdzig` submodule
   (claytercek/gdzig at `14458fb`; the release's source archive ships it empty, fetch it separately). Replace
   `vendor/gdzig/src/heap.zig` with this folder's `heap.zig`.
2. Zig 0.16.0 on PATH (bindgen runs `zig fmt`). Other Zig versions are not supported by gdzig.
3. A Godot 4.6.x console executable for bindgen: 4.7.2's `extension_api.json` fails to parse in gdzig's bindgen. Pass
   it with `-Dgodot-path`; `-Dgodot-version` downloads one, which fails behind a proxy.
4. Build twice:

       zig build -Doptimize=Debug -Dtarget=x86_64-windows-gnu -Dgodot-path=<Godot 4.6 console exe>
       zig build -Doptimize=ReleaseFast -Dtarget=x86_64-windows-gnu -Dgodot-path=<Godot 4.6 console exe>

   Each writes `project/lib/native_video.dll`: copy it to `native_video.windows.debug.x86_64.dll` and
   `native_video.windows.release.x86_64.dll`. Check: without the fix, the ReleaseFast build is byte-size identical
   (872448) to upstream's shipped DLL.
5. Godot 4.7.2 loads the 4.6-API extension (`compatibility_minimum = "4.6"`).

## Rebuild on macOS

The same sources and `heap.zig`, Zig 0.16.0, on a Mac. Debug is `ReleaseSafe` and release `ReleaseFast`, as in
upstream's release build; one universal dylib per mode:

    for arch in aarch64 x86_64; do
      zig build -Dtarget=$arch-macos -Doptimize=ReleaseSafe  && cp project/lib/libnative_video.dylib $arch.debug.dylib
      zig build -Dtarget=$arch-macos -Doptimize=ReleaseFast  && cp project/lib/libnative_video.dylib $arch.release.dylib
    done
    lipo -create aarch64.debug.dylib x86_64.debug.dylib -output libnative_video.macos.debug.dylib
    lipo -create aarch64.release.dylib x86_64.release.dylib -output libnative_video.macos.release.dylib

The Tron-Legacy-MPF workflow above does this on a GitHub `macos-15` runner (run by hand) and commits the dylibs; it is
not ported to this repository yet.

Updating the add-on from a new upstream zip brings the bug back until upstream ships the fix.
