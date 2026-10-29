# With the separate render thread, the log fills with `_texture_2d_update` errors when text is drawn

| | |
|---|---|
| Id | `godot/separate-render-thread-glyph-cache` (this file: `fixes/godot/separate-render-thread-glyph-cache.md`) |
| Component | Godot |
| Kind | bug |
| Affected versions | Godot 4.6.3-stable (official Linux arm64 build); 4.5.2-stable also logged them; later versions not checked |
| Platforms | Linux arm64 seen (Jetson Xavier NX, L4T R35.6.4, Vulkan, Mobile renderer, X11); other platforms not checked |
| Found on | a Stern SAM recreation, 2026-10-09 |
| Fact | observed (test project: 8 errors in 10 s with `thread_model=2`, 0 with 1) |
| Our fix | none: the errors are harmless (pixel-identical picture) and left as they are; test project [`../repro/godot_glyph_cache.zip`](../repro/godot_glyph_cache.zip) |
| Applied by | - |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: **draft, not filed** |

## Problem

With `rendering/driver/threads/thread_model=2` (Separate), drawing text at a size the font has not cached yet logs,
every few frames:

    ERROR: Condition "p_image.is_null() || p_image->is_empty()" is true.
       at: _texture_2d_update (servers/rendering/renderer_rd/storage_rd/texture_storage.cpp:1368)

In a real game (labels and `draw_string` with dynamic fonts, no outlines) it showed 7 to 15 times in 40 s. The errors
flood the log and hide real ones.

## Cause

No script is on the call stack (`debug/settings/gdscript/always_track_call_stacks` prints no backtrace): the call
comes from the engine's own glyph cache update. It looks like a texture update queued for the render thread with an
image that is empty by the time it runs (inferred). The final picture is complete: drawing the same 120 sizes in both
thread modes and comparing the last frames gives identical pixels.

## Fix

None carried. A font with `multichannel_signed_distance_field` avoids the errors, but its glyphs are then generated
on the main thread on first use ([msdf-glyphs-main-thread.md](msdf-glyphs-main-thread.md)): 3 to 7 s of start-up
stall in a real project. So the errors are left, and the game's performance summary counts them apart.

## How to check

1. Unzip [`../repro/godot_glyph_cache.zip`](../repro/godot_glyph_cache.zip): three files. It draws outlined text with
   `ThemeDB.fallback_font` at a new size each frame for 10 s, with `thread_model=2`.
2. `godot --path godot_glyph_cache`: 8 errors in 10 s.
3. `godot --path godot_glyph_cache --render-thread safe`: 0 errors.

Text drawn without an outline did not show it in the test project.

## Upstream issue (draft, not filed)

**Title:** Separate render thread: `_texture_2d_update` "p_image is empty" errors when a font's glyph cache grows

**Body:**

```markdown
### Tested versions

- Reproducible in 4.6.3-stable (official Linux arm64 build) and 4.5.2-stable.

### System information

Jetson Xavier NX, L4T R35.6.4 (JetPack 5.1.4), Ubuntu 20.04, NVIDIA Tegra Xavier (nvgpu), X11, Vulkan, Mobile renderer.

### Issue description

With `rendering/driver/threads/thread_model=2` (Separate), drawing text at sizes the font has not cached yet logs,
every few frames:

    ERROR: Condition "p_image.is_null() || p_image->is_empty()" is true.
       at: _texture_2d_update (servers/rendering/renderer_rd/storage_rd/texture_storage.cpp:1368)

No script is on the call stack (`always_track_call_stacks` prints no backtrace), so the call comes from the glyph
cache update. With `thread_model=1` (Safe) there are no errors.

The picture looks complete: drawing the same 120 sizes in both modes and comparing the final frames gives identical
pixels, so the failing update seems to be an empty one. The errors flood the log, though, and hide real ones. In a
real project (labels and `draw_string` with dynamic fonts, no outlines) it showed 7 to 15 times in 40 s.

A font with `multichannel_signed_distance_field` enabled avoids the errors.

### Steps to reproduce

The attached project (3 files) draws outlined text with `ThemeDB.fallback_font` at a new size each frame for 10 s.

    godot --path godot_glyph_cache                        # 8 errors in 10 s
    godot --path godot_glyph_cache --render-thread safe   # 0 errors

### Minimal reproduction project (MRP)

godot_glyph_cache.zip (attached)
```
