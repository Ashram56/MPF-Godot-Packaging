# Four windows run at a quarter of the refresh rate: each vsync'd window waits for its own vertical blank

| | |
|---|---|
| Id | `godot/vsync-one-window-multiwindow` (this file: `fixes/godot/vsync-one-window-multiwindow.md`) |
| Component | Godot |
| Kind | improvement |
| Affected versions | Godot 4.6.3-stable (seen); later versions not checked |
| Platforms | Jetson Xavier NX, L4T R35.6.4, X11 + openbox, NVIDIA Tegra Vulkan driver, Mobile renderer (seen); other drivers not checked |
| Found on | Tron Legacy MPF, 2026-10-09 (Tron-Legacy-MPF commit 042695c) |
| Fact | observed (frame time 4 refreshes with 4 vsync'd windows, 1 refresh with vsync on one) |
| Our fix | vsync kept on one window only: `DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED, id)` on every other window (a game script; Tron-Legacy-MPF `game/pup/pup_player.gd` `_vsync_one_window()`) |
| Applied by | the game's script, once its extra windows are created |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: **draft, not filed** |

## Problem

A Godot process with four windows (the main window and three extra `Window` nodes, all on one 1920x1080 60 Hz screen)
ran at about 15 FPS: every frame took four screen refreshes (67 ms).

## Cause

With vsync on every window (the default: each new window inherits the project's vsync mode), each window's present
waits for its own vertical blank, one after the other. So a frame takes one refresh per window (observed). Whether
this comes from Godot's Vulkan swapchain handling (presenting each window in turn with FIFO) or from the driver is
not known (inferred: Godot presents the windows one after the other).

## Fix

Vsync stays on one window; every other window gets `VSYNC_DISABLED`. One vsync'd window still paces the frames of all
of them. The other windows can tear in principle; they redraw every frame anyway and no tearing was noticed.

Measured on the Xavier NX with two other fixes in the same change (frame decoding off the main thread, and
[../jetson-ffmpeg/planes-mapped-once.md](../jetson-ffmpeg/planes-mapped-once.md)): 5.4 FPS to 55.5 FPS, median frame
16.67 ms. The vsync change alone is the step from 4 refreshes per frame to 1.

## How to check

1. Create three extra `Window` nodes besides the main window, each drawing something that moves.
2. Print `Engine.get_frames_per_second()`: about 15 FPS on a 60 Hz screen with vsync on every window.
3. Set `VSYNC_DISABLED` on all windows but one: about 60 FPS.

## Upstream issue (draft, not filed)

**Title:** Multiple windows with vsync: each window waits for its own vblank, so N windows run at 1/N of the refresh rate (Vulkan, X11)

**Body:**

```markdown
### Tested versions

- Reproducible in 4.6.3-stable. Other versions not checked.

### System information

Jetson Xavier NX, L4T R35.6.4 (JetPack 5.1.4), Ubuntu 20.04, X11 + openbox (no compositor), NVIDIA Tegra Vulkan
driver, Mobile renderer. One 1920x1080 60 Hz screen.

### Issue description

An app with the main window and three extra `Window` nodes, all with the default vsync mode (enabled), runs at
about 15 FPS on a 60 Hz screen: each frame takes four refreshes (67 ms). Each window's present seems to wait for its
own vertical blank, one window after the other.

Disabling vsync on every window but one (`DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED, id)`)
brings it to 60 FPS; the one vsync'd window still paces all of them.

Expected: with several windows on the same screen, a frame waits for one vertical blank, not one per window. Or, if
this is a driver limit, a note in the docs of `Window` / `window_set_vsync_mode()`: with several windows, keep vsync
on one of them.

Not checked on other GPUs or drivers, or on Wayland.

### Steps to reproduce

1. A scene that creates three `Window` nodes (any size, same screen) and draws something moving in each.
2. Print `Engine.get_frames_per_second()` every second: about 15 on a 60 Hz screen.
3. Set `VSYNC_DISABLED` on the root window and two of the three windows: about 60.

### Minimal reproduction project (MRP)

Not attached yet: the steps above are the whole project.
```
