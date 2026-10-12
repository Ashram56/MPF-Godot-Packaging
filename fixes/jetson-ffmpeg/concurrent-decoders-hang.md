# With several videos switching at once, one decoder hangs forever (JetPack 6) or segfaults (JetPack 5)

| | |
|---|---|
| Id | `jetson-ffmpeg/concurrent-decoders-hang` (this file: `fixes/jetson-ffmpeg/concurrent-decoders-hang.md`) |
| Component | jetson-ffmpeg |
| Kind | bug |
| Affected versions | jetson-ffmpeg at `8d70c17efeee57f4d956df500fec78a73f8c27d4` (v3.10.0), libnvmpi; later revisions not checked |
| Platforms | Jetson AGX Orin, L4T R36.4.3 (JetPack 6.2): hangs; Jetson Xavier NX, L4T R35.6.4 (JetPack 5.1.4): segfaults |
| Found on | Tron Legacy MPF, 2026-10-05 (Tron-Legacy-MPF commit 6c16a51); JetPack 5 checked 2026-10-09 |
| Fact | observed (repro: 4 of 6 runs hung on the Orin, 5 of 20 segfaulted on the Xavier NX; 0 with the patch); the root cause inside NVIDIA's libraries is not known |
| Our fix | [`../../build/gozen/nvmpi_flush.patch`](../../build/gozen/nvmpi_flush.patch), `src/` part (`nvmpi_dec_setup_mutex`, the capture thread's STREAMOFF on error, `put_packet()` failing while in error) |
| Applied by | [`../../platforms/jetson/install_jetson_hwdec.sh`](../../platforms/jetson/install_jetson_hwdec.sh); checked by [`../../platforms/jetson/jetson_selftest.sh`](../../platforms/jetson/jetson_selftest.sh) |
| Upstream | jetson-ffmpeg, https://github.com/gjrtimmer/jetson-ffmpeg/issues; status: **draft, not filed** |

## Problem

An app with three video windows opens and closes `h264_nvmpi` decoders from several threads. Now and then one decoder
stops for good, and the thread feeding it blocks forever in `avcodec_send_packet()`. The app's main thread waited for
that decode and the whole app froze.

- The feeding thread is in `nvmpi_decoder_put_packet()` → `NvV4l2ElementPlane::dqBuffer()` on the OUTPUT plane
  (`TegraV4L2_Poll_OPlane`).
- That decoder's `dec_capture` thread has exited.

On JetPack 5 the same repro segfaulted instead (once after
`NVMMLITE_NVVIDEODEC cbDisplayPicture ErrorInfo = VideoErrorInfo_NullFrameBuffer`).

## Cause

- The CAPTURE plane's `dqBuffer()` failed with `EINVAL` while other decoders were being created and closed. The plane
  is then in error, `dec_capture_loop_fcn()` leaves its loop, and nothing ever returns OUTPUT buffers, so
  `put_packet()` blocks forever (observed in the thread dumps).
- Why the DQBUF fails while another decoder starts or stops is probably in NVIDIA's libtegrav4l2 / NvMMLite (inferred).

## Fix

1. A global mutex, `nvmpi_dec_setup_mutex`, serialises decoder setup and teardown: `nvmpi_create_decoder()`, the
   teardown part of `nvmpi_decoder_close()` (after the capture thread is joined), and `respondToResolutionEvent()`.
   That made the `EINVAL` rare, but 1 run in 8 still hung.
2. When the capture thread stops on a decoder error (not `closing`, `isInError()`), it STREAMOFFs the OUTPUT plane.
   That wakes a `put_packet()` blocked in `dqBuffer()` with an error, and `put_packet()` returns -1 at once while the
   decoder is in error. The app sees a failed decode instead of a hang, and can recreate the decoder.

With both: 0 hangs in 20 runs on the Orin (3 decoders recovered from the error), 0 failures in 20 runs on the Xavier
NX; the flush, close and crash repros still pass.

## How to check

[`../repro/nvmpi_concurrent.c`](../repro/nvmpi_concurrent.c) (build like `nvmpi_seek_close.c`, plus `-lpthread`):

    ./nvmpi_concurrent in.mp4 3 40 10

Three threads, 40 decoders each, every other one flushed. It prints each thread's progress every 2 s; a hang shows as
a count that stops moving. `bash platforms/jetson/jetson_selftest.sh --stock` runs it 20 times against both builds.

## Upstream issue (draft, not filed)

**Title:** With several decoders starting and stopping at once, a decoder can hang forever (JetPack 6) or segfault (JetPack 5)

**Body:**

```markdown
## Environment

- Jetson AGX Orin Developer Kit (t234), L4T R36.4.3 (JetPack 6.2), Ubuntu 22.04, `oot` kernel
- Jetson Xavier NX Developer Kit (t194), L4T R35.6.4 (JetPack 5.1.4), Ubuntu 20.04
- jetson-ffmpeg at 8d70c17efeee57f4d956df500fec78a73f8c27d4, `h264_nvmpi` in FFmpeg 7.1

## What happens

An application playing three videos at once opens and closes `h264_nvmpi` decoders from several threads. Now and then
one decoder stops for good, and the thread feeding it blocks forever in `avcodec_send_packet()`:

- The feeding thread is in `nvmpi_decoder_put_packet()` → `NvV4l2ElementPlane::dqBuffer()` on the OUTPUT plane
  (`TegraV4L2_Poll_OPlane`).
- That decoder's `dec_capture` thread has exited. Its CAPTURE-plane `dqBuffer()` failed with `EINVAL` while other
  decoders were being created and closed; the plane is then in error, `dec_capture_loop_fcn()` leaves its loop and
  nothing ever returns OUTPUT buffers.

On JetPack 5 (Xavier NX), the same repro segfaults instead: 5 of 20 runs, one after
`NVMMLITE_NVVIDEODEC cbDisplayPicture ErrorInfo = VideoErrorInfo_NullFrameBuffer`.

## How to reproduce

Attached nvmpi_concurrent.c: `./nvmpi_concurrent in.mp4 3 40 10` (three threads, 40 decoders each). With stock
libnvmpi at 8d70c17, 4 of 6 runs hung on the Orin.

## Fix we use

1. A global mutex serialises decoder setup and teardown: `nvmpi_create_decoder()`, the teardown part of
   `nvmpi_decoder_close()` (after the capture thread is joined), and `respondToResolutionEvent()`. That made the
   `EINVAL` rare, but 1 run in 8 still hung.
2. When the capture thread stops on a decoder error (not closing, `isInError()`), it STREAMOFFs the OUTPUT plane.
   That wakes a `put_packet()` blocked in `dqBuffer()` with an error, and `put_packet()` returns -1 at once while the
   decoder is in error. The application sees a failed decode instead of a hang, and can recreate the decoder.

With both: 0 hangs in 20 runs on the Orin (3 decoders recovered from the error), 0 failures in 20 runs on the Xavier
NX.

The root cause, why the CAPTURE plane's DQBUF fails with `EINVAL` while another decoder starts or stops, is probably
in NVIDIA's libtegrav4l2 / NvMMLite and may be worth a report on the NVIDIA developer forum.

Patch (against 8d70c17, `src/` part): <link to build/gozen/nvmpi_flush.patch in MPF-Godot-Packaging>
```
