# Uneven frame rate with 30 fps videos on a 60 Hz screen: cap Godot at 30 FPS

| | |
|---|---|
| Id | `godot/frame-cap-30` (this file: `fixes/godot/frame-cap-30.md`) |
| Component | Godot |
| Kind | improvement |
| Affected versions | Godot 4.6.3 (any) |
| Platforms | all; it matters on boards that cannot hold 60 FPS (measured on a Raspberry Pi 4) |
| Found on | a Stern SAM recreation on a Raspberry Pi 4, 2026-10-25 |
| Fact | observed: 44-46 FPS uneven (vsync rounding) without a cap, 29.5 FPS steady with it, CPU 170 % instead of 195 % |
| Our fix | `application/run/max_fps=30` in the game's `project.godot`, or `--max-fps 30` on Godot's command line |
| Applied by | a project setting a game sets in its `project.godot` |
| Upstream | none needed |

## Problem

A board that can draw 45 frames a second on a 60 Hz screen shows frames for one or two vertical blanks in turn:
motion judders. PuP videos are 30 fps, so drawing more frames buys nothing.

## Cause

Vsync on a 60 Hz screen: a frame that misses a vertical blank waits for the next one.

## Fix

Cap at 30 FPS. Every frame then lasts two vertical blanks; the time saved goes back to video decoding.

## How to check

Godot's monitor `Performance.TIME_FPS` and the share of frames over 40 ms, before and after.

## Upstream issue

None needed: a setting.
