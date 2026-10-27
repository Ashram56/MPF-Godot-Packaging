# Godot crashes at start with `--render-thread separate` and OpenGL ES (Raspberry Pi 4)

| | |
|---|---|
| Id | `godot/gles-separate-render-thread-crash` (this file: `fixes/godot/gles-separate-render-thread-crash.md`) |
| Component | Godot |
| Kind | bug |
| Affected versions | Godot 4.6.3 (Compatibility renderer, EGL on X11), and later until fixed upstream |
| Platforms | Linux with EGL (seen on a Raspberry Pi 4, Mesa V3D, Debian 13) |
| Found on | Tron Legacy MPF on a Raspberry Pi 4, 2026-10-25 |
| Fact | code (`drivers/egl/egl_manager.cpp`) and observed (the crash, then 29.5 FPS steady with the fix) |
| Our fix | [`../../build/godot/egl_release_current.patch`](../../build/godot/egl_release_current.patch): one line, a Godot rebuilt with it |
| Applied by | a Godot build with the patch (no LTO needed: same speed); the launcher keeps `--render-thread safe` without it |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: **draft, not filed** |

## Problem

With `--rendering-driver opengl3 --render-thread separate` Godot 4.6.3 crashes at start-up on the Pi 4. With
`--render-thread safe` it runs, but the main thread does all the GL work: on a Pi 4 with PuP videos it was the
limit (about 90 % of a core).

## Cause

`EGLManager::release_current()` calls `eglMakeCurrent(..., EGL_NO_CONTEXT)` but leaves `current_window` set. The
render thread then takes the context, and the next `make_current()` on the main thread thinks the window is still
current and skips `eglMakeCurrent`, so GL calls run with no context bound.

## Fix

Reset `current_window = nullptr` in `release_current()`. With it, `--render-thread separate --max-fps 30` gave
29.5 FPS, the steadiest of every combination tried, with the main thread at 49 % instead of about 90 %.

## How to check

`godot --rendering-driver opengl3 --render-thread separate` on a GLES device: crash without the patch, runs with it.

## Upstream issue (draft, not filed)

**Title:** EGLManager::release_current() leaves current_window set: crash with --render-thread separate on GLES

**Body:**

```markdown
Godot 4.6.3, Compatibility renderer, X11 + EGL (Raspberry Pi 4, Mesa V3D). Starting a project with
`--render-thread separate` crashes. EGLManager::release_current() unbinds the context but keeps current_window,
so a later make_current() on the same window returns early without eglMakeCurrent. Setting
current_window = nullptr in release_current() fixes it (one line).
```
