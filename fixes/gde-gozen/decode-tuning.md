# Decoder threads, loop-filter options and reusable plane sets for the software path

| | |
|---|---|
| Id | `gde-gozen/decode-tuning` (this file: `fixes/gde-gozen/decode-tuning.md`) |
| Component | GDE GoZen (`src/ffmpeg.cpp`, `src/gozen_video.cpp/.hpp`) and `video_playback.gd` |
| Kind | improvement |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` |
| Platforms | Linux x86_64 and arm64 built and measured; Windows and macOS not rebuilt (the GDScript detects `next_frame_into` and falls back) |
| Fact | observed (x86 bench; Radxa Rock 4D baseline), tuned arm64 numbers pending |
| Our fix | [`../../build/gozen/gozen_decode_tuning.patch`](../../build/gozen/gozen_decode_tuning.patch), [`../../addons/gde_gozen/video_playback.gd`](../../addons/gde_gozen/video_playback.gd) (`_pool`, `_take_planes()`, `_recycle_planes()`) |
| Upstream | not filed |

## What it changes

- Video decoder threads: `processor_count - 1`, capped at 4 by default (audio 1). `GOZEN_THREADS=n` forces a value.
- `GOZEN_SKIP_LOOP_FILTER=nonref|all` and `GOZEN_FAST=1` (FFmpeg `AV_CODEC_FLAG2_FAST`) are opt-in: they cut CPU
  per frame at a small quality cost.
- `next_frame_into(planes)` decodes into planes the caller owns (size and format checked), so the plane images can
  be recycled instead of allocated and copied for every frame. `video_playback.gd` keeps a pool and gives planes
  back on the render thread after the texture update.

## Measures

x86 bench (`Platform tools/decode-bench/`): `next_frame_into` gains little (the copy-on-write copy is cheap there),
the threads cap lowers CPU per frame, skip-loop-filter plus fast give about -8 % CPU.

Radxa Rock 4D, stock `base.so`, software decode, 1080p, 240 frames: one video 193 fps (decode 5.1 ms, 29.7 CPU ms
per frame), three videos 88 fps each (27.2 CPU ms). The decoder is far faster than the 30 fps needed: the lever is
CPU per frame (one video at 30 fps is about 0.9 core), not speed. Hardware decode could not be measured (rkvdec
stalled). Tuned numbers: to add after the second run.
