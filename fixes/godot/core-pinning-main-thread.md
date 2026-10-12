# Late frames on a 4-core board: Godot's main thread shares its core

| | |
|---|---|
| Id | `godot/core-pinning-main-thread` (this file: `fixes/godot/core-pinning-main-thread.md`) |
| Component | Godot |
| Kind | improvement |
| Affected versions | Godot 4.6.3-stable (measured) |
| Platforms | Linux with 4+ cores and a real display; measured on Jetson Xavier NX, L4T R35.6.4 |
| Found on | Tron Legacy MPF, 2026-10-09 (Tron-Legacy-MPF commit 34cd6ce) |
| Fact | observed (clip suite, two runs each way, Xavier NX nvpmodel mode 5) |
| Our fix | `mpf_godot/launcher.py` `core_pinning()` / `start_core_pinning()`; `MPF_GODOT_PIN=0` turns it off |
| Applied by | the launcher (`python -m mpf_godot run`), on Linux with 4+ cores, not under Xvfb |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: none needed (the launcher does it) |

## Problem

On a Jetson Xavier NX (mode 5, 4 cores) Godot's main thread peaks at 93-99% of a core. Any other thread scheduled on
its core makes a frame late.

## Cause

The main thread runs the game's scripts and submits every frame; the other threads (render thread, video decoding,
audio, MPF) compete with it for the same cores.

## Fix

The launcher pins Godot's main thread alone to the last core, and every other Godot thread and MPF to the other
cores, again every 2 s for new threads (`os.sched_setaffinity()` per thread id). Clip suite, two runs each way:

| | FPS | Frames over 2 vblanks |
|---|---|---|
| No pinning | 49.8 / 53.0 | 24 / 38 |
| Main thread alone on the last core | 51.6 / 54.7 | 22 / 24 |
| MPF alone on one core instead | 42.5 / 49.7 | - |

`jetson_clocks` (every clock at its maximum) gave nothing measurable and is not used.

## How to check

Run the same scenario with `MPF_GODOT_PIN=0` and without; compare FPS and late frames. `taskset -p <tid>` shows each
thread's mask.

## Upstream issue (draft, not filed)

None needed: the launcher does it. A Godot option to set the main thread's affinity would make it unnecessary, but it
is Linux-specific and easy to do from outside.

**Title:** -

**Body:**

```markdown
None needed (done by the launcher).
```
