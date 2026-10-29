# Videos decode on the CPU on a Jetson: GoZen never asks FFmpeg for the hardware decoder

| | |
|---|---|
| Id | `gde-gozen/hwdec-nvmpi-first` (this file: `fixes/gde-gozen/hwdec-nvmpi-first.md`) |
| Component | GDE GoZen |
| Kind | improvement |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` (`src/gozen_video.cpp` `GoZenVideo::open()`) |
| Platforms | Linux arm64 on a Jetson: AGX Orin, L4T R36.4.3 (JetPack 6.2), and Xavier NX, L4T R35.6.4 (JetPack 5.1.4); elsewhere it falls back to software |
| Found on | a Stern SAM recreation, 2026-10-04 |
| Fact | observed (Godot's log says `GoZen: hardware decoder h264_nvmpi` per video; `tegrastats` shows NVDEC busy) |
| Our fix | [`../../build/gozen/gozen.patch`](../../build/gozen/gozen.patch) (`GoZenVideo::open()`, `_open_decoder()`); FFmpeg built with jetson-ffmpeg's `*_nvmpi` decoders by [`../../build/gozen/build_gozen.sh`](../../build/gozen/build_gozen.sh); libnvmpi installed on the board by [`../../platforms/jetson/install_jetson_hwdec.sh`](../../platforms/jetson/install_jetson_hwdec.sh) |
| Applied by | the committed binaries in `addons/gde_gozen/bin/` (rebuilt by `build/gozen/build_gozen.sh`), copied by `python -m mpf_godot addons GAME --video` |
| Upstream | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are off on GitHub); status: **draft, not filed** |

## Problem

On a Jetson, three 1080p videos at once decoded in software on the CPU cores the game needs. The board's NVDEC decodes
1080p H.264 at about 350 fps, against about 70 fps on one CPU core.

## Cause

`GoZenVideo::open()` takes `avcodec_find_decoder(codec_id)`: FFmpeg's software decoder. FFmpeg's Jetson decoders
(jetson-ffmpeg's `h264_nvmpi`, `hevc_nvmpi`, ...) are separate decoders found only by name, and GoZen has no option to
ask for one.

## Fix

`gozen.patch`, in `GoZenVideo::open()`:

- unless `GOZEN_HWDEC=0` is set, look up `<codec>_nvmpi` by name (`avcodec_find_decoder_by_name()`) and open it first;
- if it is not compiled in, or fails to open (no `libnvmpi.so`, not a Jetson), fall back to the software decoder;
- log which one is used: `GoZen: hardware decoder h264_nvmpi` or `GoZen: hardware decoder h264_nvmpi unavailable,
  using software`.

The FFmpeg 7.1 built into GoZen carries jetson-ffmpeg's `nvmpi` decoders (at `8d70c17`, with
[`../../build/gozen/nvmpi_flush.patch`](../../build/gozen/nvmpi_flush.patch)); they load `libnvmpi.so` when a video
opens, so the same binary runs on any arm64 Linux.

The game side also checks for the decoder devices (`/dev/nvmap` plus `nvhost-nvdec*` or `v4l2-nvdec`) before using
it: without them NVIDIA's libraries crash rather than fail (observed).

The hardware decoder needed four more fixes in jetson-ffmpeg to be usable: see [../jetson-ffmpeg/](../jetson-ffmpeg/).

## How to check

1. On a Jetson with libnvmpi installed (`ldconfig -p | grep nvmpi`), play a video: the log says
   `GoZen: hardware decoder h264_nvmpi`; `sudo tegrastats` shows NVDEC busy.
2. With `GOZEN_HWDEC=0`: software decoding.
3. On a PC that is not a Jetson: the log says the hardware decoder is unavailable, and the video plays in software.

## Upstream issue (draft, not filed)

**Title:** Option to prefer a named FFmpeg decoder (e.g. `h264_nvmpi` on Jetson), with fallback to software

**Body:**

```markdown
## Request

`GoZenVideo::open()` always takes `avcodec_find_decoder(codec_id)`. Some hardware decoders in FFmpeg are separate
decoders found only by name, for example jetson-ffmpeg's `h264_nvmpi` / `hevc_nvmpi` on NVIDIA Jetson boards (also
`*_v4l2m2m`, `*_rkmpp` on other ARM boards). There is no way to ask GoZen for one.

## What we do (a patch on f9448619)

Unless `GOZEN_HWDEC=0` is in the environment, `open()` looks up `<codec name>_nvmpi` with
`avcodec_find_decoder_by_name()` and opens it first; if that decoder is not compiled in or fails to open (its library
missing, not a Jetson), it falls back to the software decoder. It logs which one is used.

On a Jetson Xavier NX and AGX Orin, 1080p H.264 then decodes at about 350 fps on NVDEC, against about 70 fps on one
CPU core, and three videos at once leave the CPU to the app.

## Suggested API

A generic version would cover more boards:
- `GoZenVideo.set_preferred_decoders(PackedStringArray)` (tried in order, then software), or a suffix list such as
  `["nvmpi", "v4l2m2m", "rkmpp"]`;
- or FFmpeg's hwaccel API (`hw_device_ctx`) for the platforms that have one (VAAPI, D3D11VA, VideoToolbox);
- a way to read back which decoder is in use.

Our patch, for reference: <link to build/gozen/gozen.patch in MPF-Godot-Packaging>
```
