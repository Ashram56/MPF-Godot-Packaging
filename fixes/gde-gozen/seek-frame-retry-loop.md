# The app freezes for minutes when a video seeks near its end: `seek_frame()` steps back one frame per retry at EOF

| | |
|---|---|
| Id | `gde-gozen/seek-frame-retry-loop` (this file: `fixes/gde-gozen/seek-frame-retry-loop.md`) |
| Component | GDE GoZen |
| Kind | bug |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` (`src/gozen_video.cpp` `GoZenVideo::seek_frame()`); later revisions not checked |
| Platforms | all (C++ loop); seen on Jetson Xavier NX, L4T R35.6.4, nvpmodel mode 3 (10 W, 2 cores), `h264_nvmpi` |
| Found on | Tron Legacy MPF, 2026-10-09 (Tron-Legacy-MPF commit 4fb806b) |
| Fact | observed (freeze: 9 min at 10 W, 2 cores; froze for good at about 93 s at 10 W, 4 cores); code (the EOF branch below); inferred (that this loop is what ran for minutes) |
| Our fix | avoided, not fixed: [`../../addons/gde_gozen/video_playback.gd`](../../addons/gde_gozen/video_playback.gd) never calls `seek_frame()` from its decode tasks (`_fill_queue()`, `_decode_one()`) |
| Applied by | `python -m mpf_godot addons GAME --video` |
| Upstream | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are off on GitHub); status: **draft, not filed** |

## Problem

A first version of decoding ahead on worker tasks caught up with a late video by calling `seek_frame(target)` when it
was more than a second behind. Near the end of a clip, that call ran for minutes on a busy board. Other videos' decode
tasks queued behind it, `close()` waited for it, and the whole app froze: 9 min at 10 W with 2 cores; at 10 W with 4
cores a 10-minute session froze for good at about 93 s.

## Cause

`GoZenVideo::seek_frame()` at `f9448619` (code):

```cpp
} else if (response == AVERROR_EOF) {
    _log_err("End of file reached! Going back 1 frame!");
    if ((response = _seek_frame(frame_nr--)) < 0)
        return _log_err("Couldn't seek");
    continue;
}
```

- On EOF it seeks again and steps back one frame, with no limit on the number of retries (the `attempts` counter
  only covers `EAGAIN`).
- `frame_nr--` is a post-decrement: the first retry seeks to the same frame again.
- Each retry is a full `_seek_frame()`: `avcodec_flush_buffers()`, a seek back to the previous keyframe, then
  decoding forward to the target. With a long GOP that is many frames per retry.
- When the target lies past the last frame the decoder outputs (a frame count from the container larger than the
  frames really decoded, or a decoder that loses trailing frames when it drains), every retry decodes the whole GOP to
  EOF again, one frame back each time (inferred).
- With a hardware decoder each flush also recreates the decoder (see
  [../jetson-ffmpeg/flush-hang.md](../jetson-ffmpeg/flush-hang.md)).
- `current_frame` is then set to the decremented `frame_nr`, one lower than the frame actually sought.

On a 2-core board, with this running on the one thread Godot gives low-priority tasks
([../godot/worker-pool-low-priority-ratio.md](../godot/worker-pool-low-priority-ratio.md)), that added up to minutes
(inferred).

## Fix

We do not change GoZen's C++ here; the player avoids the call:

- decode tasks only call `next_frame()`, at most a second of frames per task, and never seek;
- they run as high-priority tasks, so they do not queue behind opens and closes;
- a late video drops or slips frames instead of seeking ([decode-ahead.md](decode-ahead.md)).

The upstream fix belongs in `seek_frame()`: cap the EOF retries (a few), step back before the first retry
(`--frame_nr`), and seek directly to the last decodable frame (or return an error) instead of decoding the GOP again
for every frame.

Result with the player change (Xavier NX, 10 W, 4 cores, 620 s session): no freeze, 36.9 FPS, 0 black screens.

## How to check

1. Open a video whose container reports more frames than it decodes (or any clip, with a hardware decoder that drops
   trailing frames at drain), on a slow CPU.
2. Call `seek_frame(get_frame_count() - 1)` and time it; watch the log for repeated "End of file reached! Going back 1
   frame!" lines.
3. With a cap on the retries, the call returns within one GOP's decode.

## Upstream issue (draft, not filed)

**Title:** seek_frame() near the end of a file retries without limit, one frame back per retry, each time decoding a whole GOP

**Body:**

```markdown
## Environment

GDE GoZen at f9448619324ad7d0d4e79d3bd501bde477ea4b7f, Godot 4.6.3, Linux arm64 (Jetson Xavier NX, 2 cores at
10 W), FFmpeg 7.1 with the `h264_nvmpi` hardware decoder. The loop itself is platform independent.

## What happens

An app called `seek_frame(target)` from a worker task to catch up with a late video, near the end of a clip. The call
ran for minutes (9 min once), and everything waiting on it froze. The log repeats "End of file reached! Going back 1
frame!".

## Cause

In `GoZenVideo::seek_frame()`:

    } else if (response == AVERROR_EOF) {
        _log_err("End of file reached! Going back 1 frame!");
        if ((response = _seek_frame(frame_nr--)) < 0)
            return _log_err("Couldn't seek");
        continue;
    }

- There is no limit on EOF retries (`attempts` only counts EAGAIN).
- `frame_nr--` is a post-decrement, so the first retry seeks to the same frame again.
- Every retry flushes the decoder, seeks back to the previous keyframe and decodes forward to EOF again. With a long
  GOP, that is many frames per retry, and with a hardware decoder each flush can also recreate the decoder.
- When the requested frame is past the last frame the decoder outputs (the container's frame count is a bit larger
  than what decodes, or the decoder drops a few trailing frames at drain), it takes one full GOP decode per missing
  frame before the loop ends.
- `current_frame` ends up one lower than the frame actually shown.

## Suggested fix

- Cap the EOF retries (for example 3), then return an error or show the last decoded frame.
- Step back before retrying (`--frame_nr`), or better, remember the last frame decoded before EOF in the first pass
  and use it directly, instead of seeking again.
- Set `current_frame` to the frame actually shown.

## Workaround we use

Never call `seek_frame()` from per-frame decode work; decode forward with `next_frame()` only and drop frames when
late.
```
