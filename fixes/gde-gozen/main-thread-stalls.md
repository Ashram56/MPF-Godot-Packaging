# Every video switch freezes all windows for 1 to 2.5 s: VideoPlayback opens, loops and frees videos on the main thread

| | |
|---|---|
| Id | `gde-gozen/main-thread-stalls` (this file: `fixes/gde-gozen/main-thread-stalls.md`) |
| Component | GDE GoZen |
| Kind | bug |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` (`video_playback.gd`), Godot 4.6.3; later revisions not checked |
| Platforms | all (GDScript); worst with a slow-to-open hardware decoder: Jetson AGX Orin, L4T R36.4.3, and Jetson Xavier NX, L4T R35.6.4, with `h264_nvmpi` |
| Found on | Tron Legacy MPF, 2026-10-05 (Tron-Legacy-MPF commit f269df7); `close()` never waiting 2026-10-12 (Tron-Legacy-MPF commit 0023339) |
| Fact | code (the calls below) and observed (timing logs on the Orin) |
| Our fix | [`../../addons/gde_gozen/video_playback.gd`](../../addons/gde_gozen/video_playback.gd) (`_open_video()`, `_process()`, `restart()`, `close()`, `_release_video()`, `_exit_tree()`) |
| Applied by | `python -m mpf_godot addons GAME --video` (copies the patched add-on into the game) |
| Upstream | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are off on GitHub); status: **draft, not filed** |

## Problem

An app that switches short videos often, on several windows drawn by one Godot process, froze every window for 1 to
2.5 s on each switch with the Jetson's hardware decoder. With software decoding the same steps took up to about
0.1 s.

## Cause

The decode work is on a worker thread, but `video_playback.gd` still waits for it, or does part of it, on the main
thread:

1. `set_video_path()` starts `_open_video` on the `WorkerThreadPool` but calls `_open_audio()` on the main thread,
   which opens a second FFmpeg context.
2. `_process()` calls `WorkerThreadPool.wait_for_task_completion(_video_thread)` on the first frame after the task
   started, not once it has finished: the main thread blocks until the file is open.
3. At the end of a looping video, `_process()` calls `seek_frame(0)` on the main thread. With a hardware decoder a
   seek recreates the decoder (about 0.1 s).
4. `close()` sets `video = null` on the main thread, so the last reference is dropped there: freeing the
   `GoZenVideo` closes its decoder on the main thread.
5. (after the fixes above) `close()` waited for an open or a loop restart of the same node still running: a switch
   during a restart froze every screen 0.3-0.6 s with several decoders being created at once.

## Fix

All in `video_playback.gd`:

- `_open_video(with_audio)` opens the `AudioStreamFFmpeg` on the worker thread with the video; the main thread only
  assigns `audio_player.stream` afterwards.
- `_process()` checks `WorkerThreadPool.is_task_completed(_video_thread)` before `wait_for_task_completion()`.
- A new `restart()` goes back to the first frame by running `seek_frame(0)` on a worker task. The current frame stays
  up meanwhile. Looping uses it.
- `close()` hands the last reference to the closed `GoZenVideo` to a worker task (`_release_video`), so it is freed
  there. `_exit_tree()` waits for those tasks.
- `close()` never waits for an open or a restart still running: the video goes to the worker that frees it once that
  task is done (`_open_video()` and `_seek_start()` take the video they work on as an argument).

Measured with timing logs over a 2-minute session on the Orin (hardware decoding): the longest video step on the main
thread went from 2.4 s (a `close()`; opening averaged 0.8 s) to 10 ms. The 0.3-0.6 s waits in `close()` (2 runs in 5
of one test scene on the Xavier NX) are gone.

## How to check

Add timing around each `VideoPlayback` call made from the main thread (`Time.get_ticks_usec()`), switch videos on
three nodes every few seconds for 2 minutes, and print the longest. Or watch the frame gaps at each switch.

## Upstream issue (draft, not filed)

**Title:** VideoPlayback stalls the main thread when it opens, loops or closes a video

**Body:**

```markdown
## Environment

- GDE GoZen at f9448619324ad7d0d4e79d3bd501bde477ea4b7f, Godot 4.6.3, Linux arm64.
- Jetson AGX Orin, L4T R36.4.3 (JetPack 6.2), FFmpeg's `h264_nvmpi` hardware decoder (jetson-ffmpeg). Opening,
  seeking and closing a decoder takes tens of ms or more there, so the stalls are easy to see. The same code paths
  run on the main thread with software decoding too (up to about 0.1 s each).

## What happens

An app that switches short videos often, on three windows drawn by one Godot process, froze for 1 to 2.5 s on every
switch. The video work is on a worker thread, but `video_playback.gd` still waits for it, or does part of it, on the
main thread:

1. `set_video_path()` starts `_open_video` on the WorkerThreadPool but calls `_open_audio()` on the main thread,
   which opens a second FFmpeg context.
2. `_process()` calls `WorkerThreadPool.wait_for_task_completion(_video_thread)` on the first frame after the task
   started, not once it has finished. The main thread then blocks until the file is open.
3. Looping: at the end of a looping video, `_process()` calls `seek_frame(0)` on the main thread. With a hardware
   decoder a seek recreates the decoder.
4. `close()` sets `video = null` on the main thread, so the last reference is dropped there, and freeing the
   `GoZenVideo` closes its decoder on the main thread.

Every window of the process stalls meanwhile.

## Changes we use (all in video_playback.gd)

- `_open_video(with_audio)` opens the `AudioStreamFFmpeg` on the worker thread with the video; the main thread only
  assigns `audio_player.stream` afterwards.
- `_process()` checks `WorkerThreadPool.is_task_completed(_video_thread)` before `wait_for_task_completion()`.
- A new `restart()` goes back to the first frame by running `seek_frame(0)` on a worker task. The current frame stays
  up until then; looping uses it.
- `close()` hands the last reference to the closed `GoZenVideo` to a worker task, so it is freed there, and never
  waits for an open or a restart still running (the task frees the video once done). `_exit_tree()` waits for those
  tasks.

Measured with timing logs over a 2-minute session on the Orin (hardware decoding): the longest video step on the main
thread went from 2.4 s (a `close()`; opening averaged 0.8 s) to 10 ms.

Our copy of the file, with the changes: <link to addons/gde_gozen/video_playback.gd in MPF-Godot-Packaging>
```
