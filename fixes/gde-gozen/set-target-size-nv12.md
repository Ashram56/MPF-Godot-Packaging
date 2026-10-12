# Small video windows still copy full-size frames: decode at the shown size, as NV12

| | |
|---|---|
| Id | `gde-gozen/set-target-size-nv12` (this file: `fixes/gde-gozen/set-target-size-nv12.md`) |
| Component | GDE GoZen |
| Kind | improvement |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` (`src/gozen_video.cpp`, `video_playback.gd`, both YUV shaders) |
| Platforms | scaling: Jetson with jetson-ffmpeg's nvmpi decoders (measured on Xavier NX, L4T R35.6.4); NV12 path: Jetson and Windows (GPU frames come back as NV12) |
| Found on | Tron Legacy MPF, 2026-10-09 (Tron-Legacy-MPF commit 2c1c6dd) |
| Fact | observed (clip suite, Xavier NX nvpmodel mode 5) |
| Our fix | [`../../build/gozen/gozen.patch`](../../build/gozen/gozen.patch) (`set_target_size()`, `get_target_size()`, `is_nv12()`, `_open_decoder()`, NV12 branch of `open()` and `_copy_frame_data()`); [`../../addons/gde_gozen/video_playback.gd`](../../addons/gde_gozen/video_playback.gd) (`decode_to_display_size`, two-plane upload); [`../../addons/gde_gozen/yuv_to_rgb_forward.gdshader`](../../addons/gde_gozen/yuv_to_rgb_forward.gdshader) and [`../../addons/gde_gozen/yuv_to_rgb_compatibility.gdshader`](../../addons/gde_gozen/yuv_to_rgb_compatibility.gdshader) (`nv12` uniform) |
| Applied by | the committed binaries plus the add-on scripts, copied by `python -m mpf_godot addons GAME --video`; a game turns on `decode_to_display_size` on its `VideoPlayback` nodes |
| Upstream | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are off on GitHub); status: **draft, not filed** |

## Problem

Three 1080p videos shown in small windows (868x488 and 868x254 on one 1920x1080 screen) still had every full-size frame
copied and uploaded by the CPU. And the hardware decoder's NV12 output went through a CPU conversion (`sws_scale`) to
YUV420P first.

## Cause

- GoZen decodes at the file's size: it has no way to ask the decoder for a smaller output.
- GoZen uploads YUV420P natively (three R8 planes); any other format, NV12 included, goes through `sws_scale`.

## Fix

In `gozen.patch`:

- `GoZenVideo.set_target_size(size)`, called before `open()`: with an nvmpi decoder, the decoder is opened with
  `output_format=nv12` and, when the video is shown smaller than its file, `resize=WxH` (the Jetson's VIC scales it;
  aspect kept, even sizes, never up).
- The frame size is taken from the first decoded frame, so a scaled decoder works with the rest of GoZen.
- NV12 is used natively: Y as an R8 image, U and V interleaved as one RG8 image, no V image. `is_nv12()` tells the
  script.

In `video_playback.gd`: `decode_to_display_size` (off by default) calls `set_target_size()` with the node's size; with
NV12 it copies and uploads two planes. Both YUV shaders take an `nv12` uniform (chroma from `.rg` of one texture). A
binary without these methods keeps the three-plane path (`has_method()` checks).

Measured on the Xavier NX (three windows, a 1080p video decoded at 868x488 or 868x254: 4 to 8 times fewer pixels per
frame):

| | Before | After |
|---|---|---|
| Godot's main thread | 51-55% of a core | 44-46% |
| FPS (2 clips) | 52.9 / 54.7 | 53.4 / 55.7 |
| Frames over 2 vblanks | 19 / 33 | 18 / 26 |

## How to check

1. On a Jetson, set `decode_to_display_size = true` on a `VideoPlayback` node smaller than the video.
2. `video.get_y_data().get_size()` is the scaled size and `video.is_nv12()` is true.
3. Compare the main thread's CPU share with the option off and on.

## Upstream issue (draft, not filed)

**Title:** Decode at the display size (decoder-side scaling) and use NV12 natively

**Body:**

```markdown
## Request

Two changes that cut the per-frame CPU work when videos are shown smaller than their files:

1. `GoZenVideo.set_target_size(Vector2i)` before `open()`: when the decoder can scale (jetson-ffmpeg's nvmpi
   decoders have `resize=WxH`, done by the Jetson's VIC), decode at the shown size (aspect kept, never up). The frame
   size is then read from the first decoded frame.
2. NV12 as a native format: upload Y as R8 and UV as one RG8 texture, with an `nv12` switch in the YUV shaders
   (`chroma = texture(u_data, uv).rg`), instead of converting NV12 to YUV420P with sws_scale on the CPU. Hardware
   decoders (nvmpi with `output_format=nv12`, D3D11VA / DXVA2 after `av_hwframe_transfer_data()`, VAAPI) output NV12.

## Measured

Jetson Xavier NX, three 1080p videos in windows of 868x488 and 868x254 on one 1920x1080 screen (4 to 8 times fewer
pixels per frame): Godot's main thread 51-55% of a core to 44-46%; FPS 52.9 / 54.7 to 53.4 / 55.7.

## Our implementation (patch on f9448619)

- `set_target_size()`, `get_target_size()`, `is_nv12()` on GoZenVideo;
- `video_playback.gd`: `decode_to_display_size` export (off by default), two-plane upload with NV12;
- both YUV shaders: `uniform bool nv12`.

Patch and files: <link to build/gozen/gozen.patch and addons/gde_gozen/ in MPF-Godot-Packaging>
```
