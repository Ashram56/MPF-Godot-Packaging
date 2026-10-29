# Looping or seeking a video freezes the app forever: the decode after `avcodec_flush_buffers()` never returns

| | |
|---|---|
| Id | `jetson-ffmpeg/flush-hang` (this file: `fixes/jetson-ffmpeg/flush-hang.md`) |
| Component | jetson-ffmpeg |
| Kind | bug |
| Affected versions | jetson-ffmpeg at `8d70c17efeee57f4d956df500fec78a73f8c27d4` (v3.10.0), FFmpeg 7.1 wrapper `ffmpeg/dev/common/libavcodec/nvmpi_dec.c`; later revisions not checked |
| Platforms | Jetson AGX Orin, L4T R36.4.3 (JetPack 6.2), Ubuntu 22.04; Jetson Xavier NX, L4T R35.6.4 (JetPack 5.1.4), Ubuntu 20.04 |
| Found on | a Stern SAM recreation, 2026-10-05; JetPack 5 checked 2026-10-09 |
| Fact | observed (repro hangs every time on both boards with stock libnvmpi; passes with the patch) |
| Our fix | [`../../build/gozen/nvmpi_flush.patch`](../../build/gozen/nvmpi_flush.patch), `nvmpi_dec.c` part (`nvmpi_flush_decoder()`, `nvmpi_decode()`, `nvmpi_prime_extradata()`) |
| Applied by | [`../../build/gozen/build_gozen.sh`](../../build/gozen/build_gozen.sh) (GoZen's FFmpeg) and [`../../platforms/jetson/install_jetson_hwdec.sh`](../../platforms/jetson/install_jetson_hwdec.sh) (the whole patch, same revision); checked by [`../../platforms/jetson/jetson_selftest.sh`](../../platforms/jetson/jetson_selftest.sh) |
| Upstream | jetson-ffmpeg, https://github.com/gjrtimmer/jetson-ffmpeg/issues; status: **draft, not filed** |

## Problem

After `avcodec_flush_buffers()` on an `h264_nvmpi` context, the next `avcodec_send_packet()` never returns. Every
time, with mp4, mkv and ts input. Any seek freezes the app, and so does looping a video (a seek to 0). The same flush
happens on every loop of `ffmpeg -stream_loop 9 -c:v h264_nvmpi -i in.mp4 -f null -`.

While it hangs:

- the caller's thread is blocked in `nvmpi_decoder_put_packet()` → `NvV4l2ElementPlane::dqBuffer()` on the OUTPUT
  plane, waiting for a free bitstream buffer;
- the `dec_capture` thread spins in `dqEvent()`, waiting for a resolution-change event.

## Cause

`nvmpi_flush_decoder()` calls `nvmpi_decoder_flush()`, which resets the decoder in place (STREAMOFF/STREAMON). The
V4L2 decoder then sends no new `V4L2_EVENT_RESOLUTION_CHANGE` for the same stream, because the size did not change.
The capture plane is never set up again, no OUTPUT buffer is returned, and `put_packet()` blocks forever (inferred
from the thread state). Re-arming the capture plane in place was tried: on R36 its DQBUF then fails with `EINVAL`.

## Fix

In `nvmpi_dec.c`:

- A flush closes the decoder (`nvmpi_decoder_close()`).
- The next `nvmpi_decode()` creates a new one from the saved `nvDecParam` and primes it with the extradata again
  (`nvmpi_prime_extradata()`).
- The decoder is created lazily, so a flush right before the codec is freed creates nothing.
- A flush does nothing when no packet was sent since the decoder was created (`fed`): GoZen flushes right after
  opening and right before freeing.

Creating a decoder takes about 20 ms on an AGX Orin.

Results on the board: 3 loops and 3 mid-stream seeks pass for mp4, mkv and ts; `ffmpeg -stream_loop 9 -c:v h264_nvmpi`
completes (5879 frames).

Known leftover, not caused by this change: on a recreated decoder, draining at EOF can lose up to about 10 trailing
frames.

## How to check

[`../repro/nvmpi_seek_close.c`](../repro/nvmpi_seek_close.c) (build line at its top), with any H.264 mp4:

    ./nvmpi_seek_close in.mp4 flush

Stock libnvmpi at `8d70c17`: prints `pass 0: 100 frames`, then hangs (Orin; on the Xavier NX killed after 60 s). With
the patch: passes. `bash platforms/jetson/jetson_selftest.sh --stock` runs it against both builds.

## Upstream issue (draft, not filed)

**Title:** avcodec_flush_buffers() on *_nvmpi hangs the next decode (JetPack 6 and 5)

**Body:**

```markdown
## Environment

- Jetson AGX Orin Developer Kit (t234), L4T R36.4.3 (JetPack 6.2), Ubuntu 22.04, `oot` kernel
- Jetson Xavier NX Developer Kit (t194), L4T R35.6.4 (JetPack 5.1.4), Ubuntu 20.04
- jetson-ffmpeg at 8d70c17efeee57f4d956df500fec78a73f8c27d4, FFmpeg 7.1 patched with `scripts/ffpatch.sh`
- Decoder: `h264_nvmpi` (1080p H.264 decodes at about 350 fps, so the hardware path itself works)

## What happens

After `avcodec_flush_buffers()` on an `h264_nvmpi` context, the next `avcodec_send_packet()` never returns. Every
time, with mp4, mkv and ts input. Any seek freezes the application, and so does looping a video (a seek to 0).

Thread state while it hangs:

- The caller is blocked in `nvmpi_decoder_put_packet()` → `NvV4l2ElementPlane::dqBuffer()` on the OUTPUT plane,
  waiting for a free bitstream buffer.
- The `dec_capture` thread spins in `dqEvent()`, waiting for a resolution-change event.

## Cause (as far as we can tell)

`nvmpi_flush_decoder()` calls `nvmpi_decoder_flush()`, which resets the decoder in place (STREAMOFF/STREAMON). The
V4L2 decoder then sends no new `V4L2_EVENT_RESOLUTION_CHANGE` for the same stream, because the size did not change.
The capture plane is never set up again, no OUTPUT buffer is returned, and `put_packet()` blocks forever.

Re-arming the capture plane in place inside libnvmpi did not work: on R36 the capture plane returns `EINVAL` after
STREAMOFF/STREAMON.

## How to reproduce

    // open an H.264 mp4 with h264_nvmpi, decode a few frames, then:
    avcodec_flush_buffers(ctx);
    av_seek_frame(fmt, -1, 0, AVSEEK_FLAG_BACKWARD);
    av_read_frame(fmt, pkt);
    avcodec_send_packet(ctx, pkt);   // never returns

Also: `ffmpeg -stream_loop 9 -c:v h264_nvmpi -i in.mp4 -f null -`.

Complete program attached (nvmpi_seek_close.c, build line at its top): `./nvmpi_seek_close in.mp4 flush` prints
`pass 0: 100 frames` and then hangs, on both boards.

## Fix we use

In `ffmpeg/dev/common/libavcodec/nvmpi_dec.c`, the flush closes the decoder (`nvmpi_decoder_close()`), and the next
`nvmpi_decode()` creates a new one from the saved `nvDecParam` and primes it with the extradata again. The decoder is
created lazily, so a flush right before the codec is freed creates nothing. A flush also does nothing when no packet
was sent since the decoder was created. Creating a decoder takes about 20 ms on an AGX Orin.

With it: 3 loops and 3 mid-stream seeks pass for mp4, mkv and ts; `ffmpeg -stream_loop 9 -c:v h264_nvmpi` completes
(5879 frames); the repro passes on both boards.

Known leftover: on a recreated decoder, draining at EOF can lose up to about 10 trailing frames.

Patch (against 8d70c17, `nvmpi_dec.c` part): <link to build/gozen/nvmpi_flush.patch in MPF-Godot-Packaging>
```
