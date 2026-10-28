# Large animations stall for seconds when they load: lossless frames decompress slowly on ARM

| | |
|---|---|
| Id | `godot/vram-compressed-frames` (this file: `fixes/godot/vram-compressed-frames.md`) |
| Component | Godot |
| Kind | improvement |
| Affected versions | Godot 4.6.3-stable (measured) |
| Platforms | all (an import setting); measured on Jetson Xavier NX, L4T R35.6.4 (ETC2 on ARM; S3TC/BPTC on PCs) |
| Found on | a Stern SAM recreation, 2026-10-09 |
| Fact | observed (clip suite, Xavier NX nvpmodel mode 5) |
| Our fix | each animation frame imported with `compress/mode=2` (VRAM compressed) in its `.import` file |
| Applied by | the game's media generator or import presets (for example a `gen_media.py` that writes the `.import` files) |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: none needed (a project setting) |

## Problem

An animation of 319 frames of 1024x256 loaded when its slide was created stalled the game 2.3 s on a Jetson Xavier NX.

## Cause

Frames imported lossless take about 7 ms each to decompress on the Xavier NX, on the thread that loads them.

## Fix

Import the animation frames VRAM-compressed (`compress/mode=2`; ETC2 R11 on ARM, S3TC/BPTC on PCs). A frame then
loads in about 1.5 ms and takes half the GPU memory. Measured:

| | Lossless | VRAM compressed |
|---|---|---|
| Per frame loaded | 7 ms | 1.5 ms |
| Longest stall, two clips | 2.34 s, 1.04 s | 1.00 s, 0.95 s |
| Largest animation created | 2.24 s | 0.91 s |
| Image quality | - | 40.8 dB PSNR against lossless, no visible difference at 1280x320 |

Keep lossless only the images whose pixels a script reads back (`Image.get_pixel()` and the like).

## How to check

Time the creation of a slide holding a long animation with each import mode (`Time.get_ticks_usec()` around the
load, or the frame gap).

## Upstream issue (draft, not filed)

None needed: an import setting.

**Title:** -

**Body:**

```markdown
None needed (an import setting).
```
