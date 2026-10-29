# Videos decode on the CPU on a Raspberry Pi 4: GoZen only knows the Jetson's hardware decoder

| | |
|---|---|
| Id | `gde-gozen/hwdec-v4l2m2m` (this file: `fixes/gde-gozen/hwdec-v4l2m2m.md`) |
| Component | GDE GoZen |
| Kind | improvement |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` with [hwdec-nvmpi-first](hwdec-nvmpi-first.md) applied |
| Platforms | Linux arm64 on a Raspberry Pi 4 with the Raspberry Pi kernel (`bcm2835-codec`, `/dev/video10`: H.264); elsewhere it falls back to software |
| Found on | Raspberry Pi 4 image, 2026-10-23 |
| Fact | observed on a Raspberry Pi 4 (2026-10-24): 1080p30 H.264 loops at 27.5 fps with `h264_v4l2m2m` (OpenGL ES, about 119 % CPU for the game), 29.5 fps in software (about 155 %); opening a video takes 0.4 s, a loop 0.22 s |
| Our fix | [`../../build/gozen/gozen_v4l2m2m.patch`](../../build/gozen/gozen_v4l2m2m.patch) (`GoZenVideo::open()`), [`gozen_v4l2m2m_flush.patch`](../../build/gozen/gozen_v4l2m2m_flush.patch) (decoder recreated on flush, time base set, bounded seek retry, `GOZEN_TRACE=1`); FFmpeg built with `--enable-v4l2-m2m` by [`../../build/gozen/build_in_docker.sh`](../../build/gozen/build_in_docker.sh) |
| Applied by | the committed binary `addons/gde_gozen/bin/libgozen.linux.template_release.arm64.so` once rebuilt by `build/gozen/build_gozen.sh arm64` |
| Upstream | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are off on GitHub); status: **draft, not filed** (same request as hwdec-nvmpi-first) |

## Problem

The Pi 4 has an H.264 hardware decoder (V4L2 memory-to-memory, kernel driver `bcm2835-codec`, only in the Raspberry
Pi kernel). GoZen asks FFmpeg for the software decoder, so videos use the four CPU cores the game needs.

## Cause

`GoZenVideo::open()` knows one hardware decoder by name, `<codec>_nvmpi`. FFmpeg's `<codec>_v4l2m2m` decoders are separate
decoders found only by name, and GoZen never asks for them.

## Fix

After `<codec>_nvmpi`, `GoZenVideo::open()` tries FFmpeg's own `<codec>_v4l2m2m` decoder, then the software decoder.
`GOZEN_HWDEC=0` turns both off. The log names the one used: `GoZen: hardware decoder h264_v4l2m2m`. HEVC on the Pi 4
uses a different kernel interface (`rpi-hevc-dec`, stateless) that FFmpeg's `hevc_v4l2m2m` does not drive, so HEVC
stays in software until FFmpeg gets the Raspberry Pi V4L2-request patch.

## Two traps on the way

- `avcodec_flush_buffers()` on a V4L2 M2M decoder leaves it answering EOF: GoZen's `seek_frame()` then looped for ever
  (`frame_nr--` retried the same frame). The decoder is recreated instead, and the retry is bounded.
- Without `pkt_timebase`/`time_base` on the decoder context, every frame came back with `AV_NOPTS_VALUE`; `seek_frame()`
  skipped them all and read the whole file (9 s for 20 s of video, at every loop). FFmpeg's own tool sets both.

The hardware decoder saves little CPU in the game (about 35 points), because the frames are copied: not looked into yet.

## Limits measured in the game (Pi 4, 2026-10-24)

- **Throughput.** Real 1080p30 H.264 videos (900 frames per stream, nothing else running): one stream 56 fps, two streams 41 and 57 fps,
  three streams 22, 55 and 37 fps. The decoder gives about 55-60 1080p frames per second in all, so two 30 fps streams just fit and three do not.
  CPU cost per frame: about 1.2 ms with `h264_v4l2m2m`, 26 ms in software (a 30 fps video in software takes about 0.8 core).
- **Crash with several decoders.** With 4 or 5 `h264_v4l2m2m` decoders open at once in the game the video froze, then the decoder firmware crashed
  (`bcm2835_mmal_vchiq: timed out waiting for sync completion`, `Failed disabling i/p port, ret -62`, videobuf2 WARNINGs). It stays unusable until the next reboot
  (`ffmpeg -c:v h264_v4l2m2m` answers `VIDIOC_REQBUFS failed`). Seen twice: with a weak power supply and with a good one (CMA 419 MB free). Do not open more than two.
- **No loop.** `ffmpeg -stream_loop` with `h264_v4l2m2m` stops at the end of the file (software loops).
- **A game may not use it.** A game's player script (`gozen_player.gd`) can set `GOZEN_HWDEC=0` when `/dev/nvmap` is missing (a Jetson test), and such a game then decodes in software on a Pi 4.
  Forcing `GOZEN_HWDEC=1` lowers the CPU but not the frame rate: the game is limited by the GPU (V3D), not by decoding.
- A cap on the number of simultaneous hardware decoders is still to do.

## How to check

1. On the Pi 4 image, play an H.264 video: the log says `GoZen: hardware decoder h264_v4l2m2m`; `top` shows far less CPU.
2. `GOZEN_HWDEC=0`: software decoding.
3. A video that does not open on `/dev/video10`: the log says the decoder is unavailable, then the video plays in software.

## Upstream issue (draft, not filed)

Same request as [hwdec-nvmpi-first](hwdec-nvmpi-first.md): a list of preferred decoder names (`nvmpi`, `v4l2m2m`, `rkmpp`), tried in order,
then software, and a way to read back which one is in use.
