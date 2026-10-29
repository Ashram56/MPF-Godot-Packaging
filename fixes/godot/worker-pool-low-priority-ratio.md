# Video switches stall about 1.3 s on a 4-core board: background tasks queue on one thread

| | |
|---|---|
| Id | `godot/worker-pool-low-priority-ratio` (this file: `fixes/godot/worker-pool-low-priority-ratio.md`) |
| Component | Godot |
| Kind | improvement |
| Affected versions | Godot 4.6.3-stable (measured) |
| Platforms | all (a project setting); matters on 4-core boards; measured on Jetson Xavier NX, L4T R35.6.4 |
| Found on | a Stern SAM recreation, 2026-10-09 |
| Fact | observed (clip suite, Xavier NX nvpmodel mode 5) |
| Our fix | project setting `threading/worker_pool/low_priority_thread_ratio=0.5` |
| Applied by | a project setting a game sets in its `project.godot` |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: none needed (a project setting) |

## Problem

On a 4-core board, a video switch stalled every window 1.27 / 1.29 s in the two test clips when video opens, closes,
restarts and background resource loads overlapped.

## Cause

`WorkerThreadPool` runs low-priority tasks on a share of its threads: `low_priority_thread_ratio`, 0.3 by default.
On 4 cores that is one thread. Video opens, closes and restarts and background loads (`add_task(..., false)`,
`ResourceLoader.load_threaded_request()`) then queue behind each other, and the main thread waits for the one it
needs.

## Fix

`threading/worker_pool/low_priority_thread_ratio=0.5`: low-priority tasks get 2 threads on 4 cores. Stalls at video
switches 1.27 / 1.29 s to 0.95 / 0.61 s; the rest unchanged.

Work that must not wait behind them (decoding the next video frame) goes in high-priority tasks
(`WorkerThreadPool.add_task(callable, true)`): see [../gde-gozen/decode-ahead.md](../gde-gozen/decode-ahead.md).

## How to check

Play a scene where several videos switch at once while resources load in the background; compare the longest frame
gap with the default ratio and with 0.5.

## Upstream issue (draft, not filed)

None needed: a project setting.

**Title:** -

**Body:**

```markdown
None needed (a project setting).
```
