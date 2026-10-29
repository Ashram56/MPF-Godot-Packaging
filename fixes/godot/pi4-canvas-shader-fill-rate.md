# Raspberry Pi 4: full-screen video layers fill only about 136 Mpixel/s with Godot's canvas shader

| | |
|---|---|
| Id | `godot/pi4-canvas-shader-fill-rate` (this file: `fixes/godot/pi4-canvas-shader-fill-rate.md`) |
| Component | Godot |
| Kind | improvement |
| Affected versions | Godot 4.6.3-stable Compatibility (OpenGL ES) renderer, Mesa 25.0.7 and 26.2.2 (same times) |
| Platforms | Raspberry Pi 4 (V3D 4.2, 8 QPU at 500 MHz); probably every small GPU |
| Found on | a Stern SAM recreation, 2026-10-24 (Pi 4B, Debian 13 trixie) |
| Fact | observed (`V3D_DEBUG=shaderdb`, micro-benchmark at 1920x1080, vsync off, 3 runs per variant) |
| Our fix | [`../../addons/gde_gozen/yuv_to_rgb_fast.gdshader`](../../addons/gde_gozen/yuv_to_rgb_fast.gdshader) and [`../../addons/gde_gozen/yuv_to_rgb_fast_nv12.gdshader`](../../addons/gde_gozen/yuv_to_rgb_fast_nv12.gdshader) (unshaded, branch free); the player side (shader choice, k_y/k_u/k_v), covered layers and `render_size` are in the game (`video_playback.gd` of the add-on and the PuP player) |
| Applied by | the player picks the fast shader when a video has no rotation, interlacing or alpha |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: none needed (a project and shader choice) |

## Problem

A 1080p backglass made of two full-screen video layers ran at 15 fps on a Pi 4 with the video decoding already free
(zero-copy), the GPU's render queue at 93 %.

## Cause

The V3D does about 16 billion instructions a second. Godot's default canvas fragment shader compiles to 118 instructions
a pixel (`V3D_DEBUG=shaderdb`, 4 threads, no spills: the compiler is fine), so a full-screen layer takes 10 to 14 ms and
every further layer 10 ms more. GoZen's YUV shader (rotation, interlace branches, four reads, canvas lighting) is 150
instructions: 18 to 22 ms a layer. Not the limit: textures, bandwidth, blending (an opaque and a transparent `ColorRect`
cost the same), or the GPU clock (an overclock to 600 MHz gained nothing once the main thread became the limit).

## Fix

| Measured at 1080p, per extra full-screen layer | GPU time |
|---|---|
| Godot default canvas shader | +10.6 ms |
| same, `render_mode unshaded` | +2.6 ms |
| GoZen YUV shader | +18 ms |
| minimal unshaded YUV shader (no branches, range and colour matrix folded into constants) | +5.8 ms |

Also: no full-window `ColorRect` for a black background (3 to 6 fps) but `RenderingServer.set_default_clear_color`;
a layer fully covered by an opaque video above is neither drawn nor decoded (a silent one pauses; the Pi 4's running
hardware decoder slows the V3D by 15 to 30 %, software decoding does not); a lower render size
(`Window.content_scale_size`, the videos keep their resolution): 1600x900 +15 %, 1280x720 +38 %. Result on a full game (original
1080p videos): 15.1 to 25.4 fps; 31 fps at a 1280x720 render size. A colour key adds instructions and keeps the layer
below alive: it lost 3 to 8 %.

## How to check

`V3D_DEBUG=shaderdb godot ...` prints the instruction count per shader; `/sys/devices/platform/v3dbus/fec00000.v3d/gpu_stats`
gives the render queue's busy time. Compare an empty scene, one `ColorRect`, one more per layer, with vsync off and
fullscreen (a windowed Godot on X is copied by X: +7 ms TFU, +10 ms render).

## Upstream issue (draft, not filed)

None needed: shader and project choices. A note for Godot's documentation could say that the default canvas shader
costs 118 instructions a pixel on V3D and that `render_mode unshaded` cuts it by a factor of four.
