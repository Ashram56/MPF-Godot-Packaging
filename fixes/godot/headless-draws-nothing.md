# Screenshots from a headless run are blank, and Movie Maker runs too fast for a live client

| | |
|---|---|
| Id | `godot/headless-draws-nothing` (this file: `fixes/godot/headless-draws-nothing.md`) |
| Component | Godot |
| Kind | improvement |
| Affected versions | Godot 4.5.2-stable (seen); 4.6.3-stable works the same way (the launcher's Xvfb path is used with it) |
| Platforms | all for `--headless` and `--write-movie`; the Xvfb workaround is Linux only |
| Found on | a Stern SAM recreation, 2026-10-02 |
| Fact | code (`--headless` uses the dummy rendering driver) and observed (blank captures; the BCP client never connected under `--write-movie`) |
| Our fix | `mpf_godot/launcher.py` `godot_command()`: on Linux without a display, Godot runs under `xvfb-run` with a real window; with the opengl3 renderer it adds `--render-thread safe` |
| Applied by | the launcher (`python -m mpf_godot run`, `--xvfb` to force it) |
| Upstream | Godot docs, https://github.com/godotengine/godot-docs/issues; status: **draft, not filed** (a docs improvement) |

## Problem

Two ways to capture a game's display on a machine without a screen (CI, a server) fail:

1. `godot --headless` runs the game, but every viewport texture read back is empty: nothing is drawn.
2. Movie Maker (`--write-movie out.png`) draws frames, but runs faster than real time. An external process that drives
   the game over a socket in real time (here MPF, through BCP) never gets to connect before the run is over, or sees
   time pass at the wrong speed.

## Cause

- `--headless` selects the dummy display server and the dummy rendering driver: it renders nothing by design
  (code).
- Movie Maker uses a fixed time step and does not wait for real time between frames (documented), so the app's
  clock no longer matches the outside world's.

## Fix

- On Linux without a display, run Godot with a real window under Xvfb: `xvfb-run -a -s "-screen 0 1280x720x24" godot
  --rendering-driver opengl3 ...` (Mesa llvmpipe draws it). The launcher does this by itself when `DISPLAY` and
  `WAYLAND_DISPLAY` are unset.
- Capture with a small real-time autoload that saves the viewport's image every N frames, inert unless a command-line
  flag is given, instead of Movie Maker.
- With the opengl3 renderer, run with `--render-thread safe`: captures under Xvfb wrote no frames with the separate
  render thread ([render-thread-setting.md](render-thread-setting.md)).

## How to check

1. `godot --headless --path GAME` with an autoload that saves `get_viewport().get_texture().get_image()`: a blank
   image.
2. The same under `xvfb-run` without `--headless`, with `--rendering-driver opengl3`: the real picture.

## Upstream issue (draft, not filed)

**Title:** Docs: say that `--headless` renders nothing, and how to render without a display (Xvfb), and that Movie Maker does not run in real time

**Body:**

```markdown
### Your Godot version

4.5.2-stable and 4.6.3-stable.

### Issue description

Two things that cost us time when capturing an app's display in CI, on a machine without a screen:

1. `--headless` uses the dummy rendering driver, so viewport textures read back are empty. The command line
   tutorial says it is for servers, but not that nothing is drawn, nor what to use instead.
2. Movie Maker (`--write-movie`) runs faster than real time (fixed time step). An app that talks to an external
   process in real time (a socket client that connects after a delay, a hardware simulator) never sees that
   process, or sees time pass at the wrong speed. The Movie Maker page mentions the fixed time step but not this
   consequence.

What worked for us on Linux: a real window under Xvfb, with the Compatibility renderer drawn by Mesa llvmpipe:

    xvfb-run -a -s "-screen 0 1280x720x24" godot --rendering-driver opengl3 --path PROJECT

and a small autoload that saves the viewport's image in real time instead of Movie Maker.

### URL to the documentation page

- https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html (`--headless`)
- https://docs.godotengine.org/en/stable/tutorials/animation/creating_movies.html (Movie Maker)

### Suggested change

- Command line tutorial, `--headless`: "Nothing is rendered: viewport textures are empty. To render without a
  display on Linux, run under Xvfb (`xvfb-run`) without `--headless`."
- Movie Maker page: "The app does not run in real time; anything that depends on wall-clock time or on another
  process (network, IPC) will not behave as in a normal run."
```
