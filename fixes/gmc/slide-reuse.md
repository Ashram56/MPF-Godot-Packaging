# Every slide show rebuilds the slide's nodes: hitches on slow hardware

| | |
|---|---|
| Id | `gmc/slide-reuse` (this file: `fixes/gmc/slide-reuse.md`) |
| Component | GMC |
| Kind | improvement |
| Affected versions | GMC 1.0.0 (`scripts/media.gd`, `MPFSlide`); and later until changed upstream |
| Platforms | all; it matters on slow targets (measured on a Jetson Xavier NX) |
| Found on | a Stern SAM recreation (Tron Legacy MPF), 2026-10-12 |
| Fact | observed and measured on the game (figures below); the upstream API is a proposal |
| Our fix | none in this repository. The game pools its own slides: a GMC patch in `media.gd` `get_slide_instance()` plus a slide class that overrides `MPFSlide.remove()` |
| Applied by | **not applied by this repository's installer**: it needs game code (which slides to keep, how to reset them). A game that wants it does what is described below |
| Upstream | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draft, not filed** |

## Problem

On a slow board every slide shown during play costs a visible hitch. On a Jetson Xavier NX (4 x 1.9 GHz), a
display effect's slide took about 12 ms to build and about 25 ms more in its first drawn frame; every window of
the Godot process (DMD, videos) froze with it. 67 of 68 hitches measured in one game were slide shows.

## Cause

GMC caches each slide's `PackedScene` but instantiates a new node tree at every show (`media.gd`
`get_slide_instance()`), and frees it when it is removed (`MPFSlide.remove()` ends in `queue_free()`). Each show
pays for new nodes, new canvas items and text shaped again.

## Fix

What the game did (2026-10-12), opt-in per slide:

1. A slide script extending `MPFSlide` overrides `remove()`: after GMC's removal animation, it takes the slide
   out of the tree (`get_parent().remove_child(self)`) and puts it in a pool (two per slide name) instead of
   `queue_free()`. Godot keeps a node's canvas items and shaped text while it is out of the tree.
2. A patch at the top of `media.gd` `get_slide_instance()` (when not `preload_only`) asks the pool for a slide
   of that name first and builds one only when there is none.
3. A reused slide is reset to the state of a new one: every timed node to time 0 with no values, animations at
   frame 0 (and autoplay restarted).
4. Two traps: GMC's `initialize()` awaits `ready`, so a reused slide calls `request_ready()`; `MPFVariable`
   updaters unregister in `_exit_tree` and register only in `_ready`, so the slide saves each `MPFSceneBase`'s
   `_updaters` (its own and nested scenes') before leaving the tree and restores them after.
5. A test renders every pooled slide new and reused and compares them dot for dot.

Measured (Xavier NX, full game, 449 s of play): 221 shows reused a slide, 60 built one; frames over 2 vblanks
139 to about 121 per 612 s, frames over 100 ms 6 to 5, 58.3 FPS.

## How to check

In a game that pools: a replay logs `DMD: slide pool: N shows reused a slide, M built one` at exit; frame-time
probes show fewer late frames. Turning the pool off (the game's setting) brings the hitches back.

## Upstream issue (draft, not filed)

**Title:** Optional slide reuse: keep removed slides and show them again instead of rebuilding from the scene

**Body:**

```markdown
**Environment**
- GMC 1.0.0, Godot 4.5.x / 4.6.x; measured on an NVIDIA Jetson Xavier NX (4 x 1.9 GHz ARM)

**Problem**
`media.gd` `get_slide_instance()` instantiates a new node tree from the cached PackedScene at every show, and
`MPFSlide.remove()` frees it. On a slow board each show costs about 12 ms to build plus about 25 ms more in its
first frame (new canvas items, text shaped again), a hitch in every window of the process. In a full game,
67 of 68 measured hitches were slide shows.

**What we did (as a game-side patch)**
- `remove()` override: after the removal animation, `get_parent().remove_child(self)` and keep the slide in a
  pool (2 per slide name) instead of `queue_free()`.
- `get_slide_instance()`: take a pooled slide of that name first (not for `preload_only`).
- Reset on reuse: timed nodes to time 0, animations to frame 0; call `request_ready()` because `initialize()`
  awaits `ready`; save and restore each `MPFSceneBase._updaters`, since MPFVariable updaters unregister in
  `_exit_tree` and register only in `_ready`.
Result on the Xavier NX: 221 of 281 shows reused a slide; frames over 2 vblanks 139 -> ~121 per 612 s.

**Proposed API**
1. A per-slide option, e.g. `MPFSlide.reusable: bool` (export) or a slide_player setting `reuse: true`, and
   a pool size in `gmc.cfg` (`[media] slide_pool_size = 2`).
2. GMC pools reusable slides itself: `remove()` detaches instead of freeing, `get_slide_instance()` takes from
   the pool, and GMC handles `request_ready()` and the updaters.
3. A virtual `_reset_for_reuse()` on MPFSlide (and a `reset()` on MPFVariable, MPFAnimation...) called before
   a pooled slide is shown, so game nodes can return to their start state.
4. `get_slide_instance()` documented as the single place slides come from, so games can extend it.

Default off: slides that keep state between shows would behave differently.
```
