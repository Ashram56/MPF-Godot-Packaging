# native_video build fix

`heap.zig` replaces `vendor/gdzig/src/heap.zig` (gdzig 14458fb) in
[godot-native-video](https://github.com/claytercek/godot-native-video) v0.3.1
([issue 26](https://github.com/claytercek/godot-native-video/issues/26)). gdzig's `engine_allocator` reserved
`alignment` extra bytes for an aligned block, but the payload starts up to `alignment + 3` bytes in, so the end
of a u16 string (the file path) overran the block. The fix reserves `alignment + 4` and, in `remap`, moves the
payload when the new block aligns differently.

- Windows: the x86_64 DLLs in `../native_video/` were built with this fix by hand (`../native_video/FIX.md`).
- macOS: `.github/workflows/native_video_macos.yml` builds the universal dylibs on a GitHub macOS runner and
  commits them to `../native_video/`. It runs when this folder changes on a branch, or from the Actions tab.
