# Zero-copy for DRM PRIME frames (rkvdec on Rock 4D, VAAPI on x86, other stateless decoders)

| | |
|---|---|
| Id | `gde-gozen/drm-prime-zero-copy` (this file: `fixes/gde-gozen/drm-prime-zero-copy.md`) |
| Component | GDE GoZen (`src/gozen_zerocopy.cpp/.hpp`, `src/gozen_video.cpp`) |
| Kind | design, not built |
| Platforms | Linux with Godot on EGL (OpenGL ES): Rock 4D (rkvdec), x86 (VAAPI), Pi 4 already has its own V4L2 version |
| Fact | code (read in the GoZen tree with our patches); hardware checks below are still open |

## What the code does today

- `GoZenVideo::_hw_download()` turns every frame the hardware decoded into system memory with
  `av_hwframe_transfer_data()`. For a DRM PRIME frame FFmpeg maps the dma-buf (`mmap`), syncs it
  (`DMA_BUF_IOCTL_SYNC`), copies it line by line and unmaps it, for every frame. The buffer is uncached for the CPU,
  so this is slow (the Pi 4 measured 10 to 15 ms per 1080p frame). Then `_copy_frame_data()` copies again into the
  `Image` planes and `texture_2d_update` uploads them: three copies of each frame.
- The Pi 4 avoids all of it: `GoZenZeroCopy` keeps the decoder's V4L2 buffer, exports it (`VIDIOC_EXPBUF`), imports
  each plane as an `EGLImage` (R8 for Y, GR88 for UV) and hands the textures to Godot with
  `texture_create_from_native_handle`. It is tied to `_v4l2m2m` decoders: the buffer is found through FFmpeg's
  `V4L2Buffer` (`gozen_v4l2_frame_buffer`).

## Design: one more source for the same machinery

Every hardware route of FFmpeg that matters here (V4L2 request, VAAPI, also Rockchip MPP) can hand out
`AV_PIX_FMT_DRM_PRIME` frames: `frame->data[0]` is an `AVDRMFrameDescriptor` with the dma-buf fds
(`objects[].fd`, `.size`, `.format_modifier`) and per layer and plane the object index, offset and pitch. That is
exactly what `_import()` needs, and it replaces `VIDIOC_EXPBUF`. Changes:

1. **Keep the frame as DRM PRIME.** `_open_hwaccel()` already knows `hw_pix_fmt`. When the zero-copy is on, skip
   `_hw_download()` for the first frame and for `next_frame_held()` (the copy path still calls it, so a failed
   import falls back by itself). The zero-copy object is created from the frame's format *before* the download,
   not after as today (`gozen_video.cpp`, where `zero_copy = new GoZenZeroCopy()`).
2. **`hold()`**: accept `AV_PIX_FMT_DRM_PRIME` with one layer NV12 (`DRM_FORMAT_NV12`, two planes; the object may be
   one fd for both planes). Fill `Held` from the descriptor: `fd`, `offset[]`, `pitch[]`, modifier, size. Clone the
   `AVFrame`: the reference keeps the decoder's buffer, and its fd stays valid, until `_unref()`.
3. **Buffer identity**: today `(generation, index, base)`. For DRM use `(generation, st_dev, st_ino)` of the fd
   (`fstat`): a dma-buf has a stable inode, and the decoder reuses its buffers, so each buffer is imported once.
4. **`_import()`**: `dmabuf = dup(held.fd)` instead of `gozen_v4l2_export()`; when the modifier is not linear (0) add
   `EGL_DMA_BUF_PLANE0_MODIFIER_LO/HI_EXT` (needs `EGL_EXT_image_dma_buf_import_modifiers`, else give up and copy).
   The rest (R8 and GR88 planes, `glEGLImageTargetTexture2DOES`, `texture_create_from_native_handle`, `KEEP_SHOWN`)
   is unchanged. Failure sets `import_failed` and playback continues on the copy path.
5. **`video_playback.gd`** needs nothing: it already uses `is_zero_copy()`, `next_frame_held()`, `show_held()` and the
   NV12 shader of the Pi 4.
6. Env: `GOZEN_ZEROCOPY=0` already disables it.

Expected effect on the Rock 4D: no `av_hwframe_transfer_data`, no plane copy, no texture upload (the GPU samples
the decoder's buffer). The CPU per frame falls to the decoder's own work plus the held-frame bookkeeping.

## Hardware checks before it can work (only a test on the board tells)

1. Does Panfrost (Mali-G52, Rock 4D, kernel 7.2) import an rkvdec dma-buf as R8 and GR88 `EGLImage`s?
   `eglinfo` must list `EGL_EXT_image_dma_buf_import` and, if the buffers are not linear, the modifiers
   extension. rkvdec output is linear in our reading (no AFBC), to confirm with the descriptor's modifier.
2. Is the picture complete when the GPU reads it? The V4L2 request hwaccel returns the frame once the request is
   done, but the green flashes seen earlier were reads of unfinished decodes; the patched rkvdec module fixed the
   copy path. dma-bufs of rkvdec may carry no implicit fence, so the zero-copy shows the same risk: test with
   `GOZEN_HWDEC=1` and a clip, count green frames, with `dmesg` watched for "timed out" and no module reload.
3. Pool depth: `KEEP_SHOWN = 3` plus pending frames hold decoder buffers; the stateless decoder needs enough
   capture buffers (FFmpeg's pool for the request hwaccel) or the decode stalls. Measure with three videos.
4. Cache attributes of the dma-buf for the GPU (cached for Panfrost sampling): none expected, visible as artifacts.

## Why not do it in the game

It is the engine's copy path, the same for every game and board, so it belongs in the GoZen patch set
(`build/gozen/`), with the bench `bench.gd` extended with a `--mode=held` that calls `next_frame_held()`/`show_held()`.

## Order of work

1. Patch (about 150 lines, `gozen_drm_prime_zerocopy.patch`), x86 VAAPI build can test the import code path on a
   machine with a GPU (the sandbox has none: compile only), arm64 build for the Rock 4D.
2. Bench `--mode=held` with `GOZEN_HWDEC=1` on the Rock 4D (one video, three videos), then the game's FPS.
3. If the checks above pass, the same patch serves VAAPI on x86 and any DRM PRIME decoder.

## Measures that frame it (Rock 4D, rkvdec through v4l2request, patched module, 1080p, 240 frames)

| Build, mode | Videos | fps per video | CPU ms per frame | Decode ms per frame |
|---|---|---|---|---|
| stock `base.so`, hardware, copy | 1 | 102.9 | 7.3 | 9.7 |
| stock `base.so`, hardware, copy | 3 | 51.3 | 7.0 | 11.0 |
| `tuned.so`, hardware, `next_frame_into` | 1 | 113.3 | 6.8 | 8.8 |
| `tuned.so`, hardware, `next_frame_into` | 3 | 53.4 | 6.6 | 10.6 |
| `tuned.so`, software, `next_frame_into` | 3 | 86.2 | 23.6 | 7.0 |

Hardware decode costs 3.4 times less CPU than software; the one VPU limits three videos to about 155 fps in total
(decode time per frame stays near 10.6 ms). No "timed out" in dmesg, no green frame (302 frames of one clip
compared with the software decode: 0 differ). The 6.6 to 7.3 CPU ms per frame left is mostly the copy this design
removes; the VPU time (about 9 to 11 ms per frame) stays.

## First measure of the patch (Rock 4D, headless bench `--mode=held`, no GPU: hold and drop only)

`zc.so` (sha256 `0540c629…`), `GOZEN_HWDEC=1`, 1080p, 240 frames, `zero_copy=true` reported at open, no "timed out":

| Videos | Zero-copy | fps per video | CPU ms per frame | Decode ms per frame |
|---|---|---|---|---|
| 1 | on | 164.7 | 0.33 | 6.05 |
| 1 | off (`GOZEN_ZEROCOPY=0`) | 111.1 | 7.04 | 8.97 |
| 3 | on | 60.2 | 0.31 | 9.52 |
| 3 | off | 51.9 | 6.76 | 10.97 |

CPU per frame falls about 21 times; throughput +48 % for one video, +16 % for three (181 against 156 fps in total,
then the single VPU is the limit). This bench has no GPU: it does not measure the EGL import, the display or the
picture's correctness. Those are the four hardware checks above, still open.
