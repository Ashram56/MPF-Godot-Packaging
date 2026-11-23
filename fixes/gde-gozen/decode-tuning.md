# Decoder threads, loop-filter options and reusable plane sets for the software path

| | |
|---|---|
| Id | `gde-gozen/decode-tuning` (this file: `fixes/gde-gozen/decode-tuning.md`) |
| Component | GDE GoZen (`src/ffmpeg.cpp`, `src/gozen_video.cpp/.hpp`) and `video_playback.gd` |
| Kind | improvement |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` |
| Platforms | Linux x86_64 and arm64 built and measured; Windows and macOS not rebuilt (the GDScript detects `next_frame_into` and falls back) |
| Fact | observed (x86 bench; Radxa Rock 4D, base and tuned) |
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
stalled). 
Same board, `tuned.so`, software decode, three 1080p videos, `next_frame_into` mode (fps per video / CPU ms per frame):

| GOZEN_THREADS | fps per video | CPU ms per frame |
|---|---|---|
| 1 | 38.8 | 15.3 |
| 2 | 60.2 | 18.9 |
| 4 (default cap) | 86.7 | 24.0 |
| stock `base.so` (7 threads) | 88.3 | 27.2 |

`next_frame_into` gives about +4 % throughput; skip-loop-filter plus fast give -6 % CPU per frame. With one video the
cap costs speed (193 to 146 fps) and saves 14 % CPU. Reading: throughput follows the thread count, the A53 cores stay
nearly idle, and 30 fps needs far less than any of these. Two threads leave 2x headroom for 30 fps and cost 30 % less
CPU per frame than the stock build, which frees the A72 cores for Godot's main thread. Recommended: board profiles
of slow ARM boards set `GOZEN_THREADS=2`; the in-game FPS effect is not measured yet.
