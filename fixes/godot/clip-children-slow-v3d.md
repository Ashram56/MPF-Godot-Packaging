# A rounded DMD frame costs 20 points of GPU on a Raspberry Pi 4 (`clip_children`)

| | |
|---|---|
| Id | `godot/clip-children-slow-v3d` (this file: `fixes/godot/clip-children-slow-v3d.md`) |
| Component | Godot |
| Kind | improvement |
| Affected versions | Godot 4.6.3, Compatibility renderer |
| Platforms | Raspberry Pi 4 (V3D); not measured elsewhere |
| Found on | Tron Legacy MPF on a Raspberry Pi 4, 2026-10-26 |
| Fact | observed: GPU render 75 % with `clip_children` on a 535x148 panel, 55 % without; frames over 40 ms 15 % vs 4 % |
| Our fix | the game draws a rounded black panel behind the DMD and keeps the DMD inside the round area instead of clipping it (Tron-Legacy-MPF: `[dmd] corner_clip=false`, the default) |
| Applied by | the game's code |
| Upstream | none needed |

## Problem

A `Panel` with `clip_children = CLIP_CHILDREN_AND_DRAW` round a small viewport tripled the late frames.

## Cause

Inferred: clipping draws the children into an offscreen buffer and composites them, an extra pass the V3D pays
for in full every frame.

## Fix

Draw the rounded panel behind; size the content so it stays inside the rounded corners.

## How to check

Godot's GPU render time (`RenderingServer.get_frame_setup_time_usec` / the profiler) and the share of frames over 40 ms with `clip_children` on and off.

## Also: draw a dot DMD at a whole number of pixels per dot

256 dots in 535 px (2.09 px a dot), then the window scaled 1.5x to 1080p, gave a strong moiré. 512x128 render
pixels for 256x64 (2 px a dot, 3 on screen) with nearest filtering and no second dot shader: no moiré, no cost
(29.7 FPS at a 30 cap). A DMD at native 1080p (3x, a 1920x1080 render) fell to 18 FPS on the Pi 4.

## Upstream issue

None needed: a cost of the platform, not a bug.
