# Every video switch stalls about 1 s: `nvmpi_decoder_close()` waits out two 500 ms timeouts

| | |
|---|---|
| Id | `jetson-ffmpeg/slow-close` (this file: `fixes/jetson-ffmpeg/slow-close.md`) |
| Component | jetson-ffmpeg |
| Kind | bug |
| Affected versions | jetson-ffmpeg at `8d70c17efeee57f4d956df500fec78a73f8c27d4` (v3.10.0), libnvmpi; later revisions not checked |
| Platforms | Jetson AGX Orin, L4T R36.4.3 (JetPack 6.2); Jetson Xavier NX, L4T R35.6.4 (JetPack 5.1.4) |
| Found on | Tron Legacy MPF, 2026-10-05 (Tron-Legacy-MPF commit f269df7); JetPack 5 checked 2026-10-09 |
| Fact | observed (close times from the repro on both boards) |
| Our fix | [`../../build/gozen/nvmpi_flush.patch`](../../build/gozen/nvmpi_flush.patch), `src/` part (`closing` flag in `nvmpi_decoder_close()`, 50 ms `dqEvent()` slices in the capture loop) |
| Applied by | [`../../platforms/jetson/install_jetson_hwdec.sh`](../../platforms/jetson/install_jetson_hwdec.sh) (builds libnvmpi with the patch); checked by [`../../platforms/jetson/jetson_selftest.sh`](../../platforms/jetson/jetson_selftest.sh) |
| Upstream | jetson-ffmpeg, https://github.com/gjrtimmer/jetson-ffmpeg/issues; status: **draft, not filed** |

## Problem

An app that switches between short videos closes and opens decoders all the time. Each close of a decoder that has
not output a frame yet took about 1 s, and the app stalled on every switch.

| Board, libnvmpi | Close, no packet sent | Close after 30 frames |
|---|---|---|
| AGX Orin, stock `8d70c17` | 1061 ms | 17 ms |
| AGX Orin, patched | about 55 ms | - |
| Xavier NX, stock `8d70c17` | 1086 ms | 24 ms |
| Xavier NX, patched | 59 ms | 48 ms |

## Cause

A decoder that never saw a resolution change (just created, or recreated after a flush) has its `dec_capture` thread
waiting in `dqEvent()` for one. `nvmpi_decoder_close()` sets `eos` and joins that thread, which notices it only after
two 500 ms `dqEvent()` timeouts (the wait and an extra "race guard" wait).

## Fix

- A `closing` flag, set first thing in `nvmpi_decoder_close()`.
- The capture loop waits for events in 50 ms `dqEvent()` slices, and when `closing` is set it exits without waiting
  for a resolution-change event (it skips the extra 500 ms wait).

Close then takes about 55 ms.

## How to check

[`../repro/nvmpi_seek_close.c`](../repro/nvmpi_seek_close.c) (build line at its top):

    ./nvmpi_seek_close in.mp4 close

It prints the close time for a decoder that got no packet and for one after 30 frames (table above).
`bash platforms/jetson/jetson_selftest.sh --stock` runs it against the patched and the stock build.

## Upstream issue (draft, not filed)

**Title:** nvmpi_decoder_close() takes about 1 s when the decoder has not seen a resolution change

**Body:**

```markdown
## Environment

- Jetson AGX Orin Developer Kit (t234), L4T R36.4.3 (JetPack 6.2), Ubuntu 22.04, `oot` kernel
- Jetson Xavier NX Developer Kit (t194), L4T R35.6.4 (JetPack 5.1.4), Ubuntu 20.04
- jetson-ffmpeg at 8d70c17efeee57f4d956df500fec78a73f8c27d4 (libnvmpi built with `scripts/build.sh --install`),
  `h264_nvmpi` in FFmpeg 7.1

## What happens

`nvmpi_decoder_close()` takes about 1 s when the decoder never saw a resolution change, for example a decoder closed
right after it was created or recreated. An application that switches between short videos stalls on every switch.

| Board | Close, no packet sent | Close after 30 decoded frames |
|---|---|---|
| AGX Orin | 1061 ms | 17 ms |
| Xavier NX | 1086 ms | 24 ms |

## Cause

The `dec_capture` thread waits for a resolution-change event in `dqEvent()`. After `close()` sets `eos`, the thread
notices it only after two 500 ms `dqEvent()` timeouts (the wait itself and the extra wait after it), and `close()`
joins it.

## Fix we use

A `closing` flag set at the start of `nvmpi_decoder_close()`. The capture loop waits in 50 ms `dqEvent()` slices,
and when `closing` is set it exits without waiting for a resolution-change event. Close then takes about 55 ms on the
Orin, 59 ms on the Xavier NX.

## How to reproduce

Attached nvmpi_seek_close.c (build line at its top), with any H.264 mp4: `./nvmpi_seek_close in.mp4 close` prints the
close time for a decoder that got no packet yet and for one after 30 decoded frames.

Patch (against 8d70c17, `src/` part): <link to build/gozen/nvmpi_flush.patch in MPF-Godot-Packaging>
```
