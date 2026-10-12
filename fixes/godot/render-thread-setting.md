# Godot's separate render thread: on with videos on Godot 4.6.3, a loss on 4.5.2 without them

| | |
|---|---|
| Id | `godot/render-thread-setting` (this file: `fixes/godot/render-thread-setting.md`) |
| Component | Godot |
| Kind | improvement |
| Affected versions | Godot 4.6.3-stable (gain measured); 4.5.2-stable (loss measured) |
| Platforms | all (a project setting); measured on Jetson Xavier NX, L4T R35.6.4, Vulkan, Mobile renderer |
| Found on | Tron Legacy MPF, 2026-10-09 on (Tron-Legacy-MPF commit f52ba68); the 4.5.2 loss 2026-10-10 (commit c9a8be2) |
| Fact | observed (clip suite, Xavier NX nvpmodel mode 5) |
| Our fix | project setting `rendering/driver/threads/thread_model=2`; the launcher's `--no-render-thread` turns it off (`mpf_godot/launcher.py`) |
| Applied by | a project setting a game sets in its `project.godot`; the launcher (`python -m mpf_godot run`) adds `--render-thread safe` with `--no-render-thread` or with the opengl3 renderer |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: none needed (a project setting) |

## Problem

On a slow ARM board, Godot's main thread is the critical path: it runs the game's scripts and submits every frame.
With three videos and a DMD drawn by one Godot process, the main thread used 44-46% of a core on rendering work alone.

## Cause

With `thread_model=1` (Safe, the default) rendering runs on the main thread.

## Fix

`rendering/driver/threads/thread_model=2` moves rendering to its own thread. Measured on the Xavier NX, mode 5:

| Set-up | Main thread | FPS (2 clips) | p99 frame | Frames over 2 vblanks |
|---|---|---|---|---|
| Godot 4.6.3, three videos, thread off | 44-46% of a core | 53.4 / 55.7 | 33.9 / 31.6 ms | 18 / 26 |
| Godot 4.6.3, three videos, thread on | 27-28% of a core | 55.7 / 58.1 | 29.1 / 25.0 ms | 16 / 21 |
| Godot 4.5.2, DMD only, thread off | - | 56.2 | - | - |
| Godot 4.5.2, DMD only, thread on | - | 54.3 (twice the late frames) | - | - |

So: on by default with Godot 4.6.3 and videos; off for a game on 4.5.2 with the DMD alone. Retest on every Godot
upgrade.

Known costs with it on:

- harmless glyph-cache errors in the log ([separate-render-thread-glyph-cache.md](separate-render-thread-glyph-cache.md));
- the pipeline cache save at exit fails ([pipeline-cache-not-saved-render-thread.md](pipeline-cache-not-saved-render-thread.md)):
  set `save_chunk_size_mb=0.1` with it;
- captures with the opengl3 renderer (under Xvfb) wrote no frames with it: the launcher runs those with
  `--render-thread safe`;
- a frame image that the script hands to a texture can be uploaded later than the call: if a decoder may overwrite
  that image, copy it first (done in [`../../addons/gde_gozen/video_playback.gd`](../../addons/gde_gozen/video_playback.gd)
  for a frame shown straight after a seek or a restart).

## How to check

Run the same scenario with and without `--no-render-thread` and compare FPS, p99 frame time and late frames; check the
main thread's CPU share per thread (`top -H` or a sampler).

## Upstream issue (draft, not filed)

None needed: a project setting. The two bugs it exposes have their own drafts
([separate-render-thread-glyph-cache.md](separate-render-thread-glyph-cache.md),
[pipeline-cache-not-saved-render-thread.md](pipeline-cache-not-saved-render-thread.md)).

**Title:** -

**Body:**

```markdown
None needed (a project setting).
```
