# Closing a decoder mid-video sometimes crashes the app (SIGSEGV in libnvmmlite_video)

| | |
|---|---|
| Id | `jetson-ffmpeg/close-crash` (this file: `fixes/jetson-ffmpeg/close-crash.md`) |
| Component | jetson-ffmpeg |
| Kind | bug |
| Affected versions | jetson-ffmpeg at `8d70c17efeee57f4d956df500fec78a73f8c27d4` (v3.10.0), libnvmpi; later revisions not checked |
| Platforms | Jetson AGX Orin, L4T R36.4.3 (JetPack 6.2): crashes; Jetson Xavier NX, L4T R35.6.4 (JetPack 5.1.4): not seen in 100 runs |
| Found on | Tron Legacy MPF, 2026-10-05 (Tron-Legacy-MPF commit f269df7); JetPack 5 checked 2026-10-09 |
| Fact | observed (9 of 100 repro runs crashed on the Orin, 0 with the patch); cause inferred from where it crashes |
| Our fix | [`../../build/gozen/nvmpi_flush.patch`](../../build/gozen/nvmpi_flush.patch), `src/` part (`nvmpi_decoder_close()`, `deinitDecoderCapturePlane()`, the capture loop's frame drop while `closing`) |
| Applied by | [`../../platforms/jetson/install_jetson_hwdec.sh`](../../platforms/jetson/install_jetson_hwdec.sh); checked by [`../../platforms/jetson/jetson_selftest.sh`](../../platforms/jetson/jetson_selftest.sh) |
| Upstream | jetson-ffmpeg, https://github.com/gjrtimmer/jetson-ffmpeg/issues; status: **draft, not filed** |

## Problem

When a decoder is closed while its video is still playing (a video switch), NVIDIA's decoder thread sometimes crashes
with SIGSEGV inside `libnvmmlite_video.so`, inside `v4l2_close` or after the CAPTURE DMA buffers were freed. 9 of 100
runs of the repro crashed on the AGX Orin with stock libnvmpi. On the Xavier NX it did not crash in 100 runs, stock or
patched.

## Cause

It looks like the decoder still writes a frame into a buffer that `deinitDecoderCapturePlane()` has already destroyed
(inferred):

- the decoder is torn down while it is still decoding the queued bitstream;
- the CAPTURE DMA buffers and the frame pool are freed while the decoder device is still open.

## Fix

In `nvmpi_decoder_close()`:

1. Let the decoder finish the queued bitstream first: for at most 300 ms, dequeue OUTPUT buffers until none is
   queued. Meanwhile the capture thread drops frames instead of waiting for the frame pool while `closing` is set
   (the flag from [slow-close.md](slow-close.md)).
2. Stop the capture plane (`setStreamStatus(false)`, `reqbufs(DMABUF, 0)`) and `delete ctx->dec` before freeing the
   CAPTURE DMA buffers and the frame pool. `deinitDecoderCapturePlane()` skips that part when `dec` is already gone.

After it: 0 crashes in 100 runs of the repro on the Orin, and 2 and 5 minute sessions ran clean. It costs nothing on
the Xavier NX, so it is kept there too.

## How to check

[`../repro/nvmpi_seek_close.c`](../repro/nvmpi_seek_close.c) (build line at its top), `crash` mode: decodes 100 frames
and closes the decoder mid-stream, three times. Run it in a loop:

    for i in $(seq 100); do ./nvmpi_seek_close in.mp4 crash > /dev/null || echo crashed; done

`bash platforms/jetson/jetson_selftest.sh --stock` runs 100 of them against both builds.

## Upstream issue (draft, not filed)

**Title:** Closing an nvmpi decoder mid-stream sometimes crashes in libnvmmlite_video (JetPack 6)

**Body:**

```markdown
## Environment

- Jetson AGX Orin Developer Kit (t234), L4T R36.4.3 (JetPack 6.2), Ubuntu 22.04, `oot` kernel
- jetson-ffmpeg at 8d70c17efeee57f4d956df500fec78a73f8c27d4 (libnvmpi built with `scripts/build.sh --install`),
  `h264_nvmpi` in FFmpeg 7.1

## What happens

When a decoder is closed while a video is still playing, NVIDIA's decoder thread sometimes crashes (SIGSEGV) inside
`libnvmmlite_video.so`: 9 of 100 runs of the repro below crashed. The crash happens inside `v4l2_close`, or after the
CAPTURE DMA buffers were freed. It looks like the decoder still writes a frame into a buffer that
`deinitDecoderCapturePlane()` has already destroyed.

On a Jetson Xavier NX, L4T R35.6.4 (JetPack 5.1.4), it did not crash in 100 runs.

## Fix we use, in nvmpi_decoder_close()

1. Let the decoder finish the queued bitstream first: for at most 300 ms, dequeue OUTPUT buffers until none is
   queued. Meanwhile the capture thread drops frames instead of waiting for the pool while a `closing` flag is set.
2. Stop the capture plane (`setStreamStatus(false)`, `reqbufs(DMABUF, 0)`) and `delete ctx->dec` *before* freeing
   the CAPTURE DMA buffers and the frame pool. `deinitDecoderCapturePlane()` skips that part when `dec` is already
   gone.

After this: 0 crashes in 100 runs of the same repro on the Orin, and 2 and 5 minute sessions of an app playing three
videos at once ran clean.

## How to reproduce

Attached nvmpi_seek_close.c (build line at its top), with any H.264 mp4. `crash` mode decodes 100 frames and closes
the decoder mid-stream, three times. Run it in a loop:

    for i in $(seq 100); do ./nvmpi_seek_close in.mp4 crash > /dev/null || echo crashed; done

Patch (against 8d70c17, `src/` part): <link to build/gozen/nvmpi_flush.patch in MPF-Godot-Packaging>
```
