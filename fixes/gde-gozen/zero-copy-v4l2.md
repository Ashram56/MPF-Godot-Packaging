# Videos from the Raspberry Pi 4 hardware decoder are copied twice before they are drawn

| | |
|---|---|
| Id | `gde-gozen/zero-copy-v4l2` (this file: `fixes/gde-gozen/zero-copy-v4l2.md`) |
| Component | GDE GoZen |
| Kind | improvement |
| Affected versions | GDE GoZen f9448619 with [hwdec-v4l2m2m](hwdec-v4l2m2m.md) |
| Platforms | Raspberry Pi 4 (Compatibility renderer, `h264_v4l2m2m`) |
| Found on | Tron Legacy MPF on a Raspberry Pi 4, 2026-10-24/25 |
| Fact | observed: software decode 50 FPS but videos 0.7 s late, 330 % CPU; hardware decode + zero-copy 44 FPS uncapped, in time, 195 % CPU |
| Our fix | [`../../build/gozen/gozen_zerocopy.patch`](../../build/gozen/gozen_zerocopy.patch) and [`gozen_v4l2_buffers_nv12.patch`](../../build/gozen/gozen_v4l2_buffers_nv12.patch); the add-on's [`video_playback.gd`](../../addons/gde_gozen/video_playback.gd) and fast YUV shaders |
| Applied by | `build/gozen/build_gozen.sh` (the arm64 library in `addons/gde_gozen/bin/`); `GOZEN_HWDEC=1` turns the hardware decoder on, `GOZEN_ZEROCOPY=0` turns zero-copy off |
| Upstream | GDE GoZen, https://github.com/VoylinsGamedevJourney/gde_gozen/issues; status: **draft, not filed** |

## Problem

With the hardware decoder each frame was copied out of the decoder's buffer, then uploaded to the GPU: the saving
in CPU was small and the GPU, already the limit, did more.

## Cause

GoZen hands frames to Godot as CPU images (`get_y_data()` and so on), so a hardware-decoded frame goes GPU memory -> CPU copy -> texture upload.

## Fix

- The decoder's capture buffers are exported (`VIDIOC_EXPBUF`), imported as EGLImages and shown as Godot textures:
  nothing copied. Late frames are skipped instead of slipping the clock. With a separate render thread the GL calls
  run on it.
- 12 capture buffers, NV12 (`GOZEN_V4L2_PIXFMT=yuv420p` for three planes).
- A fast YUV shader for the common case (no rotation, interlacing or alpha): about 3x cheaper on V3D.
- The kernel's `bcm2835-codec` driver can oops (an inverted completion test): the Pi needs the fixed module
  (platforms/raspberrypi.md); without it keep `GOZEN_HWDEC` off.

## How to check

`GOZEN_HWDEC=1`: the log says `hardware decoder h264_v4l2m2m` and zero-copy; `top` shows the game near 195 % at
the cap instead of 330 %.

## Upstream issue (draft, not filed)

**Title:** Zero-copy display of V4L2 M2M hardware-decoded frames (Raspberry Pi)

**Body:**

```markdown
On a Raspberry Pi 4 with h264_v4l2m2m, exporting the capture buffers as dmabufs and importing them as EGLImages
avoids the copy and upload of every frame (330 % -> 195 % CPU in a game with three 1080p30 videos). Patch available.
```
