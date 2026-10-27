# Raspberry Pi 4: the hardware decoder's frames cost more to copy than to decode (zero-copy through the GPU)

| | |
|---|---|
| Id | `gde-gozen/v4l2m2m-zero-copy` (this file: `fixes/gde-gozen/v4l2m2m-zero-copy.md`) |
| Component | GDE GoZen |
| Kind | improvement |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` with FFmpeg 7.1 (`h264_v4l2m2m`), Godot 4.6.3 Compatibility renderer, Mesa 25.0.7 |
| Platforms | Raspberry Pi 4 (bcm2835-codec, `/dev/video10`), Linux arm64, Godot on EGL / OpenGL ES |
| Found on | Tron Legacy MPF, 2026-10-24 (Pi 4B, Debian 13 trixie, kernel 6.18 rpt) |
| Fact | observed (60 s game scenario, 3 runs; C prototype 54 fps and 1.1 ms CPU a frame) |
| Our fix | [`../../build/gozen/gozen_zerocopy.patch`](../../build/gozen/gozen_zerocopy.patch) (new `src/gozen_zerocopy.cpp/.hpp`, `src/gozen_v4l2.c/.h`, `next_frame_held()`, `show_held()`, `drop_held()`, `is_zero_copy()`, an in-place decoder restart on seek, `SConstruct`); the player side is in [`../../addons/gde_gozen/video_playback.gd`](../../addons/gde_gozen/video_playback.gd) with the fast YUV shaders; NV12 and 12 capture buffers in [`gozen_v4l2_buffers_nv12.patch`](../../build/gozen/gozen_v4l2_buffers_nv12.patch); the kernel's `bcm2835-codec` needs the completion fix ([platforms/raspberrypi.md](../../platforms/raspberrypi.md)) or it oopses when a decoder closes |
| Applied by | the build script applies the patch after `gozen_v4l2m2m*.patch`; the player uses it when `is_zero_copy()` is true; `GOZEN_ZEROCOPY=0` turns it off, `GOZEN_V4L2_RESTART=0` goes back to recreating the decoder |
| Upstream | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues; status: **draft, not filed** |

## Problem

With `h264_v4l2m2m` on a Pi 4, two 1080p videos gave 12.7 fps, worse than software decoding (15 fps): Godot's main
thread stayed at 80 to 87 % of a core even though the decoder did the work.

## Cause

- The decoder's capture buffers are **uncached** memory mappings: reading one 1080p frame costs 10 to 15 ms (1.3 ms from
  normal memory), and NEON gains only 25 %. GoZen reads every frame into its Y/U/V images.
- Godot then uploads the planes with `texture_2d_update`, and Mesa's v3d driver tiles them on the CPU (a NEON loop:
  23 % of the main thread).

## Fix

Leave the frame where the decoder put it and give the GPU the buffer:

1. `VIDIOC_EXPBUF` once per capture buffer (a dmabuf); FFmpeg 7.1 has no drm_prime output for `v4l2m2m`, so the buffer
   is found from `frame->buf[0]` (its opaque is FFmpeg's internal `V4L2Buffer`: the FFmpeg source tree stays configured
   next to GoZen and `gozen_v4l2.c` is compiled with `-Iffmpeg`).
2. `EGL_EXT_image_dma_buf_import`, one image per plane: R8 for Y, U and V with their offsets and pitches, GR88 for the
   UV plane of NV12.
3. `glEGLImageTargetTexture2DOES` into a GL texture, handed to Godot with
   `RenderingServer.texture_create_from_native_handle` (Compatibility renderer), then sampled by the existing YUV shader.
4. Frames are held (their `AVFrame` referenced, so the decoder does not reuse the buffer) until a few frames after they
   were shown; late frames are skipped instead of slipping the clock; every GL call runs on the render thread; if the
   import fails, GoZen copies frames as before.
5. A loop or seek restarts the decoder in place (`STREAMOFF`/`STREAMON` on both queues after `avcodec_flush_buffers()`),
   instead of recreating it (`avcodec_flush_buffers()` leaves a V4L2 M2M decoder answering EOF to every later request, so a looping video stopped).

Measured in the game (classic DMD, 1080p backglass full screen, 60 s): Godot CPU 160 % to 93 %, decoder workers 69 % to
12 %, video lag 4.4 s to 0.9 s (median). The frame rate stays about 13 fps: the GPU is then the limit (see
[../godot/pi4-canvas-shader-fill-rate.md](../godot/pi4-canvas-shader-fill-rate.md)). Mesa copies a **linear** dmabuf
texture to a tiled shadow on the TFU at every draw (`V3D_DEBUG=perf`: "Updating 1920x1080@0 shadow for linear texture",
`v3d_update_shadow_texture` in `src/gallium/drivers/v3d/v3d_resource.c`): 1.6 ms per 1080p plane, 12 ms a frame for two
1080p videos. Converting once per decoded frame gains nothing while the game draws fewer frames than the video has.

## How to check

Build with the patch, run with `GOZEN_HWDEC=1` and compare `GOZEN_ZEROCOPY=0` and `1`: Godot's CPU per thread, the video
lag, and `V3D_DEBUG=perf` for the shadow copies. The player must test `RenderingServer.is_on_render_thread()` (not the
`thread_model` setting).

## Upstream issue (draft, not filed)

**Title:** V4L2 M2M decoders (Raspberry Pi 4): show decoded frames without copying them (dmabuf to an EGLImage texture)

**Body:**

```markdown
On a Raspberry Pi 4 the hardware decoder's capture buffers are uncached, so copying each 1080p frame costs 10-15 ms.
We export the buffer (VIDIOC_EXPBUF), import each plane with EGL_EXT_image_dma_buf_import (R8, GR88 for NV12's UV),
bind it with glEGLImageTargetTexture2DOES and give it to Godot with texture_create_from_native_handle. Godot's CPU went
from 160 % to 93 % with two 1080p videos. Patch attached. Needs FFmpeg's internal V4L2Buffer (FFmpeg 7.1 has no drm_prime
output for v4l2m2m). Also: avcodec_flush_buffers() leaves the decoder answering EOF; restart with STREAMOFF/STREAMON.
```
