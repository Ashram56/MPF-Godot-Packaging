# GDE GoZen, patched: FFmpeg video for Godot with GPU decoding on Linux (Jetson) and Windows

[GDE GoZen](https://github.com/VoylinsGamedevJourney/gde_gozen) is a Godot add-on that plays video files with FFmpeg:
mp4, mkv and ogg play as they are, with no conversion to Theora. Its `VideoPlayback` node (`video_playback.gd`) shows
a video and plays its sound. This copy is GoZen at `f9448619` with our fixes, for an app that plays several videos at
once alongside other windows, on slow boards too. It needs Godot 4.4 or later (tested with 4.6.3).

## How it differs from upstream

| Change | Where | Fix document |
|---|---|---|
| Opens, loops and closes videos without stalling the main thread | `video_playback.gd` | [main-thread-stalls](../../fixes/gde-gozen/main-thread-stalls.md) |
| Never seeks from decode work (upstream `seek_frame()` can retry for minutes near the end of a file) | `video_playback.gd` | [seek-frame-retry-loop](../../fixes/gde-gozen/seek-frame-retry-loop.md) |
| Up to 3 frames decoded ahead per video on worker threads; videos with sound follow the audio clock | `video_playback.gd` | [decode-ahead](../../fixes/gde-gozen/decode-ahead.md) |
| Jetson hardware decoder first (`<codec>_nvmpi`), software fallback | `bin/*.so`, `gozen.patch` | [hwdec-nvmpi-first](../../fixes/gde-gozen/hwdec-nvmpi-first.md) |
| Windows GPU decoding through Direct3D 11 Video, else DXVA2 | `bin/*.dll`, `gozen.patch` | [d3d11va-dxva2-windows](../../fixes/gde-gozen/d3d11va-dxva2-windows.md) |
| Frames decoded at the size shown (`set_target_size()`, Jetson) and uploaded as NV12 | `bin/*`, `video_playback.gd`, both shaders | [set-target-size-nv12](../../fixes/gde-gozen/set-target-size-nv12.md) |
| FFmpeg trimmed to local playback, no libvpx, libaom or TLS (`lean=yes`) | `bin/*`, `gozen.patch` | [lean-build-option](../../fixes/gde-gozen/lean-build-option.md) |
| jetson-ffmpeg fixes in the FFmpeg wrapper (a flush recreates the decoder) | `bin/*.so` | [../../fixes/jetson-ffmpeg/](../../fixes/jetson-ffmpeg/) |

Environment switches, read when a video opens:

| `GOZEN_HWDEC` | Effect |
|---|---|
| unset or `1` | hardware decoder when there is one, else software |
| `0` | software only |
| `d3d11va` or `dxva2` | Windows: only that GPU path, else software |

Godot's log names the decoder for each video: `GoZen: hardware decoder h264_nvmpi` (Jetson),
`GoZen: hardware decoding h264 (d3d11va)` (Windows), or a line saying it fell back to software.

## Files and platforms

| File | Built for |
|---|---|
| `bin/libgozen.linux.template_release.arm64.so` | Linux arm64 (Jetson, Raspberry Pi and others), glibc 2.31+ (JetPack 5, Ubuntu 20.04+) |
| `bin/libgozen.linux.template_release.x86_64.so` | Linux x86_64, glibc 2.31+ |
| `bin/libgozen.macos.template_release.universal.dylib` | macOS 11+, arm64 and Intel in one file; software decoding (no GPU path); built by `.github/workflows/gozen_macos.yml` (Actions, macos-15) from the same GoZen revision and patch; built, not yet run on a Mac |
| `bin/libgozen.windows.template_release.x86_64.dll` | Windows 10/11 x86_64 (MinGW-w64 cross build, all static: no DLL beside it) |
| `gozen.gdextension` | maps every entry, debug included (the editor binary), to the release builds above |
| `video_playback.gd` | the `VideoPlayback` node, patched |
| `yuv_to_rgb_forward.gdshader`, `yuv_to_rgb_compatibility.gdshader` | YUV to RGB, with an `nv12` switch |

No macOS build: on macOS use [`../native_video/`](../native_video/).

Hardware decoding:

| Platform | Decoder | Needs |
|---|---|---|
| Jetson (JetPack 5 or 6) | NVDEC through jetson-ffmpeg's `*_nvmpi` | libnvmpi on the board: [`../../platforms/jetson/install_jetson_hwdec.sh`](../../platforms/jetson/install_jetson_hwdec.sh), then [`../../platforms/jetson/jetson_selftest.sh`](../../platforms/jetson/jetson_selftest.sh) |
| Windows | FFmpeg's D3D11VA, else DXVA2 hwaccels (NVIDIA, AMD, Intel) | nothing to install |
| other Linux | software | - |

Tested: Jetson AGX Orin, L4T R36.4.3 (JetPack 6.2); Jetson Xavier NX, L4T R35.6.4 (JetPack 5.1.4); one Windows PC with
d3d11va.

## Install into a game

    python -m mpf_godot addons GAME --video

Besides the patched GMC, it copies this folder to `GAME/addons/gde_gozen/` on Linux (x86_64, arm64) and Windows
(x86_64), and `native_video` on Windows and macOS. In a
scene, use the `VideoPlayback` node as upstream documents it; set `decode_to_display_size = true` on a node shown
smaller than its video to decode at the node's size with the Jetson decoder.

## Rebuild

    bash build/gozen/build_gozen.sh [arm64] [x86_64] [windows]     # default: all three; needs Docker and git

[`../../build/gozen/build_gozen.sh`](../../build/gozen/build_gozen.sh) checks out GoZen and jetson-ffmpeg at the pinned
revisions (`GOZEN_REV`, `JETSON_FFMPEG_REV`), applies [`../../build/gozen/gozen.patch`](../../build/gozen/gozen.patch) and
[`../../build/gozen/nvmpi_flush.patch`](../../build/gozen/nvmpi_flush.patch), builds FFmpeg 7.1 and GoZen in Docker
(Ubuntu 20.04 for Linux, so the binaries run on glibc 2.31; Ubuntu 24.04 with MinGW-w64 for Windows) and copies the
binaries to `bin/`. Start from a clean work folder. Record each binary's sha256 in the commit message.

The jetson-ffmpeg revision must match the one `install_jetson_hwdec.sh` builds libnvmpi from: the wrapper in GoZen's
FFmpeg and the library on the board share one patch.

## Licence

GDE GoZen and FFmpeg are LGPL 2.1 (`LICENSE`). FFmpeg is built without `--enable-gpl` or `--enable-nonfree` and linked
statically into `libgozen*.so` and `libgozen*.dll`; the Windows DLL also carries MinGW-w64's runtime, under its own
permissive licences and the GCC runtime exception. The sources are the pinned revisions in `build/gozen/build_gozen.sh`
plus `build/gozen/gozen.patch` and `build/gozen/nvmpi_flush.patch`.
