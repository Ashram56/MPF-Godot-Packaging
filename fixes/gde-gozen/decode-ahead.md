# Several videos at once fall behind: frames decoded on the main thread, just in time

| | |
|---|---|
| Id | `gde-gozen/decode-ahead` (this file: `fixes/gde-gozen/decode-ahead.md`) |
| Component | GDE GoZen |
| Kind | improvement |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` (`video_playback.gd`) |
| Platforms | all (GDScript); measured on Jetson Xavier NX, L4T R35.6.4 |
| Found on | Tron Legacy MPF, 2026-10-09 (Tron-Legacy-MPF commits 042695c one frame ahead, 4fb806b no seek and high priority, f64de13 three frames ahead) |
| Fact | observed (clip suite and full sessions, Xavier NX) |
| Our fix | [`../../addons/gde_gozen/video_playback.gd`](../../addons/gde_gozen/video_playback.gd) (`QUEUE_FRAMES`, `_fill_queue()`, `_decode_one()`, `_wait_decode()`, the clock in `_process()`) |
| Applied by | `python -m mpf_godot addons GAME --video` |
| Upstream | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are off on GitHub); status: **draft, not filed** |

## Problem

On a Jetson Xavier NX, an app with three videos and other animated windows ran at 5.4 FPS as installed. Video frames
were decoded on the main thread when due; three videos fell behind, and decoding several frames to catch up made the
next frame later still.

## Cause

`VideoPlayback._process()` calls `next_frame()` on the main thread, as many times as the clock says, then uploads the
frame. Decoding and the plane copies are on the critical path of every frame.

## Fix

In `video_playback.gd`:

- Up to 3 frames per video (`QUEUE_FRAMES`) are decoded ahead on worker tasks: one task at a time per video, so frames
  stay in order. Each task decodes the next frame and queues copies of its planes (GoZen reuses its images).
- The tasks are high priority (`WorkerThreadPool.add_task(callable, true)`), so they do not wait behind opens, closes
  and background loads.
- They never seek ([seek-frame-retry-loop.md](seek-frame-retry-loop.md)).
- `_process()` shows the frame the clock has reached; a frame not ready yet is shown late instead of waited for.
- A silent video never drops a frame: after a stall its clock slips by the delay.
- A video with its own sound takes its clock from the sound heard (playback position plus time since the last mix,
  minus the output latency) and drops the frames it is late by.
- Seek, restart and close wait for the running decode task and clear the queue (`_wait_decode()`).

Measured on the Xavier NX:

| Step | Result |
|---|---|
| One frame ahead (with two other fixes: map-once in libnvmpi, vsync on one window) | 5.4 to 55.5 FPS, median frame 16.67 ms |
| No seek in decode tasks, high priority | 620 s session at 10 W, 4 cores: no freeze (froze for good at about 93 s before), 36.9 FPS |
| Three frames ahead, audio clock (2 clips) | video frames skipped 89 / 85 to 15 / 7 (0 on silent videos); A/V drift 79-130 ms to 30-46 ms on average; FPS 53.6 / 54.8 to 52.9 / 54.7 |

## How to check

Play three videos at once on a slow board and count the video frames shown out of cadence (frame number steps of more
than 1) and the A/V offset (`audio_player.get_playback_position()` against the frame's time), with the stock script
and with ours.

## Upstream issue (draft, not filed)

**Title:** VideoPlayback: decode a few frames ahead on worker threads, follow the audio clock

**Body:**

```markdown
## Request

`VideoPlayback._process()` decodes frames on the main thread when they are due (`next_frame()`), then uploads them.
With several videos at once on a slow CPU, the videos fall behind and the catch-up decoding makes the next frame later
still. An app playing three videos at once on a Jetson Xavier NX ran at about 5 FPS with it (with other causes too).

## What we did (in video_playback.gd)

- Up to 3 frames per video decoded ahead on WorkerThreadPool tasks, one task at a time per video (frames in order).
  Each task calls `next_frame()` and queues copies of the planes (GoZen reuses its images for the next frame).
- High-priority tasks, so they never queue behind low-priority work (opens, closes, resource loads).
- No seek inside decode tasks: forward decoding only.
- `_process()` shows the frame the clock has reached; a frame not ready yet is shown late, never waited for.
- Silent videos never drop a frame (their clock slips after a stall). Videos with sound take their clock from the
  sound heard (playback position + time since last mix - output latency) and drop the frames they are late by.
- Seek, restart and close wait for the running decode task and clear the queue.

## Measured (Jetson Xavier NX, three videos)

- Video frames skipped per clip 89 / 85 to 15 / 7 (0 on silent videos).
- A/V drift 79-130 ms to 30-46 ms on average.
- Combined with two other fixes, 5.4 to 55.5 FPS.

Our file: <link to addons/gde_gozen/video_playback.gd in MPF-Godot-Packaging>
```
