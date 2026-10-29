# Every start recompiles every pipeline: the Vulkan pipeline cache is never saved with the separate render thread

| | |
|---|---|
| Id | `godot/pipeline-cache-not-saved-render-thread` (this file: `fixes/godot/pipeline-cache-not-saved-render-thread.md`) |
| Component | Godot |
| Kind | bug |
| Affected versions | Godot 4.6.3-stable and 4.5.2-stable (test project on both); later versions not checked |
| Platforms | Linux arm64 seen (Jetson Xavier NX, L4T R35.6.4, Vulkan, Mobile renderer, X11); Linux x86_64 with lavapipe shows the error only (lavapipe writes no cache data) |
| Found on | a Stern SAM recreation, 2026-10-09 |
| Fact | observed (test project and game); the error text and line are from Godot's log |
| Our fix | project setting `rendering/rendering_device/pipeline_cache/save_chunk_size_mb=0.1`; test project [`../repro/godot_pipeline_cache.zip`](../repro/godot_pipeline_cache.zip) |
| Applied by | a project setting a game sets in its `project.godot` |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: **draft, not filed** |

## Problem

The first use of each material stalls the game on every start, never only on the first one. On a Jetson Xavier NX a
particle effect with a light took 4.0-4.7 s on its first appearance, every start; a test scene had 1.4 s and 2.3 s
hitches every start. No `pipelines.*.cache` file is ever in `user://vulkan`.

At exit Godot logs:

    finalize can only be called from the render thread

(`rendering_device.cpp:7470` in 4.6.3, `:7248` in 4.5.2).

## Cause

Godot saves the pipeline cache at exit, and while running whenever the cache has grown by
`rendering/rendering_device/pipeline_cache/save_chunk_size_mb` (3 MB by default).

- With `rendering/driver/threads/thread_model=2`, the save at exit runs off the render thread and fails with the
  error above.
- A process ended by a kill, a power cut or a cabinet's power switch never reaches the save at exit anyway.
- A small 2D game rarely grows the cache by 3 MB in one run, so the save while running never happens either.

## Fix

`rendering/rendering_device/pipeline_cache/save_chunk_size_mb=0.1` in the game's `project.godot`: the cache is saved
while the game runs, as it grows. From the second start the stalls are gone (start-up stall 0.6 s instead of 4.7 s;
the test scene's 1.4 s and 2.3 s hitches gone).

## How to check

1. Unzip [`../repro/godot_pipeline_cache.zip`](../repro/godot_pipeline_cache.zip) (three files, no assets): a 3D scene
   with `thread_model=2`, where a burst of emissive particles and an omni light appear at 2 s. Each run prints the
   files in `user://vulkan` at start and the longest frame.
2. Run it twice: `godot --path godot_pipeline_cache`. Xavier NX: both runs find no cache file and have a long frame at
   the burst (4.6.3: 2.1 s and 1.7 s; 4.5.2: 1.6 s and 1.5 s); the exit logs the error.
3. Run it twice with `--render-thread safe`: the second run finds `pipelines.mobile.*.cache` and its longest frame is
   0.2 s.

## Upstream issue (draft, not filed)

**Title:** With the separate render thread, the Vulkan pipeline cache is never saved ("finalize can only be called from the render thread")

**Body:**

```markdown
### Tested versions

- Reproducible in 4.6.3-stable and 4.5.2-stable.

### System information

Jetson Xavier NX, L4T R35.6.4 (JetPack 5.1.4), NVIDIA Tegra Vulkan driver, X11, Mobile renderer,
`rendering/driver/threads/thread_model=2`. Linux x86_64 with lavapipe shows the error only (lavapipe writes no
pipeline cache data at all).

### Issue description

Every start compiles every pipeline again: the pipeline cache file is never written.

- Godot saves the pipeline cache at exit, and whenever it has grown by
  `rendering/rendering_device/pipeline_cache/save_chunk_size_mb` (3 MB by default).
- With the separate render thread, the save at exit fails:
  `finalize can only be called from the render thread` (rendering_device.cpp:7470 in 4.6.3, :7248 in 4.5.2).
- A process ended by a kill or a power cut never reaches the save at exit anyway.
- A small 2D project rarely grows the cache by 3 MB in one run, so the cache stays empty.

On a slow GPU each first use of a material stalls: a particle effect with a light took 4.0-4.7 s on its first
appearance, on every start.

Workaround: `save_chunk_size_mb=0.1`, so the cache is saved as it grows. From the second start the stalls are gone.

Expected: the save at exit works with the separate render thread (run it on the render thread), and the
documentation of `save_chunk_size_mb` mentions that a killed process never saves.

### Steps to reproduce

The attached project (3 files, no assets) is a 3D scene with `thread_model=2` where a burst of emissive particles and
an omni light appear at 2 s. Each run prints the files in `user://vulkan` at start and the longest frame. Run it twice:

    godot --path godot_pipeline_cache                        # separate render thread
    godot --path godot_pipeline_cache --render-thread safe   # for comparison

Xavier NX: with the separate render thread both runs show no cache file and a long frame at the burst (4.6.3: 2.1 s
and 1.7 s; 4.5.2: 1.6 s and 1.5 s), and the exit logs the error. With `--render-thread safe` the second run finds
`pipelines.mobile.*.cache` and its longest frame is 0.2 s.

### Minimal reproduction project (MRP)

godot_pipeline_cache.zip (attached)
```
