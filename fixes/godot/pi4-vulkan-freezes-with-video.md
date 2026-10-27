# On a Raspberry Pi 4 the game freezes while a video plays with Vulkan: the launcher uses OpenGL ES

| | |
|---|---|
| Id | `godot/pi4-vulkan-freezes-with-video` (this file: `fixes/godot/pi4-vulkan-freezes-with-video.md`) |
| Component | Godot |
| Kind | improvement |
| Affected versions | Godot 4.6.3, Vulkan Mobile renderer on Mesa V3D 4.2 (Debian 13, Raspberry Pi kernel 6.18.50) |
| Platforms | Raspberry Pi 4 |
| Found on | Raspberry Pi 4 image, 2026-10-24 |
| Fact | observed (about 7 frames per second, then the main thread sits at 100 % CPU and the game stops; with the hardware decoder or without; no error in the log). The cause is **not** known |
| Our fix | the launcher passes `--rendering-driver opengl3` on a Raspberry Pi 4 ([`../../mpf_godot/launcher.py`](../../mpf_godot/launcher.py)); `MPF_GODOT_RENDERER=vulkan` keeps Godot's choice |
| Applied by | the launcher (`python -m mpf_godot run`) |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: none needed until the cause is known |

## Problem

Playing a 1080p video in a GoZen `VideoPlayback` on a Pi 4 with Vulkan: 38 to 49 frames in the first seconds, then the
game freezes. With OpenGL ES the same clip plays at 30 fps (hardware decoder, about 47 % CPU) or 29.5 fps (software).

## Cause

Not found. Godot itself says at start-up "Platform supports less than 48 textures per stage ... Defaulting to Mobile
renderer": the V3D Vulkan driver is at the limit of what Godot asks. Finding the cause needs `gdb` and probably a Godot
build with symbols.

## Fix

On a Raspberry Pi 4 (device tree model), unless the arguments already name a renderer, the launcher adds
`--rendering-driver opengl3` (Compatibility renderer). MPF/GMC screens are 2D (slides, text, videos), which that
renderer draws. A game that needs Vulkan features can set `MPF_GODOT_RENDERER=vulkan`.

## How to check

1. On the Pi 4: `python -m mpf_godot run GAME`; Godot's log says `OpenGL API OpenGL ES 3.1` instead of `Vulkan`.
2. `MPF_GODOT_RENDERER=vulkan python -m mpf_godot run GAME` goes back to Vulkan.

## Upstream issue (draft, not filed)

Not written: the cause is unknown. Reproduce first with `gdb` on the frozen main thread.
