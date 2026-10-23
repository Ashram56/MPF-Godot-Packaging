# Videos decode on the CPU on a Raspberry Pi 4: GoZen only knows the Jetson's hardware decoder

| | |
|---|---|
| Id | `gde-gozen/hwdec-v4l2m2m` (this file: `fixes/gde-gozen/hwdec-v4l2m2m.md`) |
| Component | GDE GoZen |
| Kind | improvement |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` with [hwdec-nvmpi-first](hwdec-nvmpi-first.md) applied |
| Platforms | Linux arm64 on a Raspberry Pi 4 with the Raspberry Pi kernel (`bcm2835-codec`, `/dev/video10`: H.264); elsewhere it falls back to software |
| Found on | Raspberry Pi 4 image, 2026-10-23 |
| Fact | **not yet checked on a board** (the build is written; no Pi 4 has run it) |
| Our fix | [`../../build/gozen/gozen_v4l2m2m.patch`](../../build/gozen/gozen_v4l2m2m.patch) (`GoZenVideo::open()`); FFmpeg built with `--enable-v4l2-m2m` by [`../../build/gozen/build_in_docker.sh`](../../build/gozen/build_in_docker.sh) |
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

## How to check

1. On the Pi 4 image, play an H.264 video: the log says `GoZen: hardware decoder h264_v4l2m2m`; `top` shows far less CPU.
2. `GOZEN_HWDEC=0`: software decoding.
3. A video that does not open on `/dev/video10`: the log says the decoder is unavailable, then the video plays in software.

## Upstream issue (draft, not filed)

Same request as [hwdec-nvmpi-first](hwdec-nvmpi-first.md): a list of preferred decoder names (`nvmpi`, `v4l2m2m`, `rkmpp`), tried in order,
then software, and a way to read back which one is in use.
