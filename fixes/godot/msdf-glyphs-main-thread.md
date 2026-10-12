# The game freezes for seconds the first time text is drawn with an MSDF font

| | |
|---|---|
| Id | `godot/msdf-glyphs-main-thread` (this file: `fixes/godot/msdf-glyphs-main-thread.md`) |
| Component | Godot |
| Kind | bug |
| Affected versions | Godot 4.6.3-stable and 4.5.2-stable (test project on both); later versions not checked |
| Platforms | all (MSDF generation is CPU work); measured on Linux arm64 (Jetson Xavier NX, nvpmodel mode 5) and Linux x86_64 |
| Found on | Tron Legacy MPF, 2026-10-09 (Tron-Legacy-MPF PR #35, commit 15ca54a) |
| Fact | observed (timings); code for the cause (glyphs rendered on first use by the drawing thread) |
| Our fix | fonts baked at setup (a game-side script, e.g. Tron-Legacy-MPF `game/tools/bake_fonts.gd`); test project [`../repro/godot_msdf_main_thread.zip`](../repro/godot_msdf_main_thread.zip) |
| Applied by | the game's setup step (a headless Godot script run once after install) |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: **draft, not filed** |

## Problem

The first lines of text froze the game for 20-30 s on a Jetson Xavier NX. With Orbitron (OFL) and the 94 printable
ASCII characters:

| `msdf_pixel_range` | Time on the main thread, Xavier NX mode 5 | Linux x86_64, Xeon 2.1 GHz, 4 cores (test project) |
|---|---|---|
| 16 | 6.8 s | 2.0 s |
| 192 (wide copy, for outlines and glow) | 45 s | 13.2 s |

4.5.2 on x86_64: 2.0 s and 12.9 s.

## Cause

`FontFile` with `multichannel_signed_distance_field = true` generates a glyph's MSDF synchronously the first time the
glyph is drawn, on the thread that draws it, usually the main thread. A larger `msdf_pixel_range` costs much more,
which the docs do not say. The importer's pre-render option helps only fonts imported into the project, not fonts
loaded at run time with `load_dynamic_font()` (as a game that lets the user pick a font does).

## Fix

Bake the glyphs once, offline:

1. A headless Godot script calls `font_render_glyph()` for every character, at every size and range the game uses.
2. It saves the `FontFile` with `ResourceSaver.save()`: the generated glyph cache is kept in the resource.
3. The game loads the saved resource at start-up with `ResourceLoader.load_threaded_request()`.

Text renders identically (0 differing pixels in our comparison). The 20-30 s freezes are gone. On the Xavier NX
baking the game's clean fonts took about 100 s at setup and 65 MB on disk.

## How to check

1. Unzip [`../repro/godot_msdf_main_thread.zip`](../repro/godot_msdf_main_thread.zip): it draws the 94 printable
   ASCII characters with an MSDF copy of Orbitron (bundled with its OFL licence) at `msdf_pixel_range` 16, then 192,
   and prints how long each first frame took.
2. `godot --path godot_msdf_main_thread`: seconds per first frame (table above).

## Upstream issue (draft, not filed)

**Title:** MSDF glyphs are generated on the main thread when first drawn (seconds per string on ARM)

**Body:**

```markdown
### Tested versions

- Reproducible in 4.6.3-stable and 4.5.2-stable.

### System information

Jetson Xavier NX, nvpmodel mode 5 (4 Carmel cores at 1.9 GHz), Linux arm64, Mobile renderer. Also Linux x86_64
(Xeon 2.1 GHz, 4 cores).

### Issue description

With a `FontFile` that has `multichannel_signed_distance_field = true` (`msdf_size = 256`), the first time a
character is drawn its MSDF is generated synchronously on the thread that draws it, usually the main thread.
With Orbitron (OFL) and the 94 printable ASCII characters:

| `msdf_pixel_range` | Jetson Xavier NX | Linux x86_64, 4 cores |
|---|---|---|
| 16 | 6.8 s | 2.0 s |
| 192 | 45 s | 13.2 s |

So the first lines of text freeze an app for many seconds. A larger pixel range costs much more, which the docs do
not say.

The importer's pre-render option helps only fonts imported into the project, not fonts loaded at run time with
`load_dynamic_font()` (an app that lets the user pick a font).

Workaround: render every glyph once offline (`font_render_glyph()` in a headless script), save the `FontFile` with
`ResourceSaver.save()` (the glyph cache is kept), and load that resource at start-up with
`ResourceLoader.load_threaded_request()`. Text renders identically.

Expected, any of:
- MSDF glyph generation on a worker thread (the glyph shows a frame later);
- a run-time API or import option to pre-render a character set;
- a note in the `msdf_pixel_range` docs about its cost.

### Steps to reproduce

The attached project draws the 94 printable ASCII characters with an MSDF copy of Orbitron at `msdf_pixel_range`
16 and then 192, and prints how long each first frame took.

### Minimal reproduction project (MRP)

godot_msdf_main_thread.zip (attached; Orbitron is OFL, its licence is included)
```
