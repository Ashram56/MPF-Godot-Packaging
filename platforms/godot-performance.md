# GMC + Godot performance on a slow target

> Moved here from Stern-SAM-Decryption `knowledge/sam_to_mpf_playbook.md` on 2026-10-27 (Godot/GMC findings live in this
> repository). Method for the display itself: Stern-SAM-Decryption `agents/improvement.md`, section 2a.
A Jetson Xavier NX cabinet (4 cores at 1.9 GHz, CPU and GPU sharing 6.8 GB) runs the DMD, three PuP videos and the
light cycles in one Godot process: every window freezes together when Godot's main thread stalls. Measured on
Tron (full game, 2026-10-12); method and figures in [agents/improvement.md](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/agents/improvement.md) section 2a.

| Practice | Why (Tron's measurement) |
|---|---|
| Measure before guessing: frame times from a probe, MPF's log, and per-slide timing (`node_added` / `ready` / next frame / `frame_post_draw`) against a baseline frame | 67 of 68 hitches were slide shows; the guessed causes (light cycles, videos, power mode) were not |
| Never block the main thread on a worker (`wait_for_task_completion`, a `load()` of something still loading); hand the object to the worker or poll `is_task_completed()` | A video switch waiting for a loop restart froze every screen 0.3-0.6 s |
| Theme overrides (`add_theme_*_override`) are not setters: set them once, never on every update, and not on nodes whose own drawing is hidden | About 25 ms per slide shown; hitches 46 to 6-12 |
| Creating node trees during play is the expensive part of a slide; GMC caches the PackedScene, not the nodes. Prefer few persistent nodes changed in place (pooled slides, or one display node drawing from data) | A new slide's first frame still costs about 25 ms over a normal one |
| Keep display content file-driven (pictures by path, timing and text as data) so higher-resolution or replacement art needs no code | The HD frames already swap in by path; a data-driven display keeps that and drops per-show nodes |
| Load on worker threads at start-up, in display order, a few at a time; VRAM-compress pictures nobody reads back; bake fonts at setup | Effect stalls 0.9 s to under 0.1 s; MSDF freezes of 20 s gone |
| Text: shape once (`TextLine`) and draw it; avoid a `Label` plus helper nodes per line | Fewer nodes per slide, no Label layout per update |
| A separate process per screen group (game + DMD; PuP videos) isolates freezes but costs a second Vulkan context and 300-500 MB; fix the stalls at their source first | - |
| Power mode: per-core clock beats core count on the main thread (Xavier NX mode 5, 4 x 1.91 GHz, over mode 8, 6 x 1.42 GHz) | Mode 8: same FPS, more hitches |
| Memory: budget the whole board (OS + MPF + Godot + video memory, shared on a Jetson) and soak-test a full hour | Tron: Godot 1.46 GB at start, about 2.0 GB after the first game, then flat for 6 games (2.02 GB peak); board 3.7 GB peak. Owner's target: under 4 GB where it costs no stutter |

## A display drawn from data (Tron, 2026-10-12)

 Tron's display effects went from node scenes to data in two steps,
each switchable for A/B runs; what worked:

- **Pool the slides first** (cheap, safe): override `MPFSlide.remove()` to park the slide out of the tree instead of
  `queue_free()`, and patch GMC's `get_slide_instance()` to take one back. Godot keeps a node's canvas items and
  shaped text while it is out of the tree. Two traps: GMC's `initialize` awaits `ready`, so call `request_ready()`
  on a reused slide; `MPFVariable` updaters unregister in `_exit_tree`, so snapshot each slide's `_updaters` (and its
  nested scenes') before removing and restore them after. Reset every timed node to time 0 with no values, and test
  that a reused slide renders exactly as a new one.
- **Then one picture per screen**: generate each effect as data (rectangles, a frame list naming picture files,
  text lines with their ROM layout) next to its node scene; keep each effect's GMC slide as one node holding time
  and values, so priorities, queues and expiry stay GMC's; draw the top effect's list into a fixed-size
  `SubViewport` with `UPDATE_ONCE`, re-armed only when the list changes. Few canvas items, a fixed set of them, and
  no render when nothing changed: on x86 software rendering the median frame fell from 29.9 to 5.8 ms; on the Xavier
  NX (full game, mode 5) frames over 2 vblanks fell from 139 to 14, over 100 ms from 6 to 1, GPU 60% to 43%, 8.8 to 7.2 W.
- **Keep the content open**: the data names pictures by path (HD twins swap in by path), and a hand-made scene
  at a known path (Tron: `game/dmd_custom/<deff>.tscn`) replaces an effect's data, so videos or redrawn effects
  need no code change. Keep the node scenes generated as the reference: a test renders every effect both ways and
  compares (Tron: all 145 classic effects dot for dot).
- **Memory comes with it**: preload only the pictures the data names (in HD, not the classic ones as well) and point
  identical frames of different effects at one file (Tron: 417 of 4123 frame entries). Godot resident 980 to 890 MB,
  video memory 710 to 609 MB, effects preload 9.5 to 5.3 s on x86; on the Xavier NX video memory 627 to 545 MB,
  board peak 3.61 to 3.50 GB.
- Godot traps met: JSON numbers load as floats (`&` on them fails; convert whole numbers back to `int`); a
  `Font.draw_string` per line uses the font's shaped-text cache, so shaping happens once; ADD-blended glow layers
  need their own canvas item with a `CanvasItemMaterial`; clip a zoomed line with `canvas_item_set_clip` and a
  custom rect on its own layer.
