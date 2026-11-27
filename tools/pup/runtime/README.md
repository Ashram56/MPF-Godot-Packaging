# PuP runtime: play a PuP Pack in an MPF + Godot game

The game-agnostic runtime of the [PuP Pack agent](../../../agents/pup_pack.md) (section 5): an MPF mode that
turns the game's events into the pack's trigger rows, and a Godot autoload that plays them on the game's extra
windows as PinUP Player does. A game copies it in and configures it in one file, `game/pup.cfg`; nothing in
here names a game. First built for Tron Legacy (Tron-Legacy-MPF-PuP), made generic for Transformers.

```
python tools/pup/runtime/install.py ../My-Game-MPF      # copies (or updates) the runtime into the game
```

| Copied to the game | What it is |
|---|---|
| `game/pup_runtime/pupfiles.py` | reads `triggers.pup` as PinUP Player does (the pack is never edited) |
| `game/pup_runtime/engine.py` | event (with conditions on its arguments) or switch -> rows; `RestSeconds`; counters; no MPF import |
| `game/pup_runtime/mode.py` | the MPF mode (never started): hooks the events, sends BCP `pup_play`, the music hand-over |
| `game/pup_runtime/settings.py` | reads `game/pup.cfg` + `game/pup.local.cfg` (both sides parse the same INI) |
| `game/pup/pup_player.gd`, `pup_screen.gd` | the Godot autoload `Pup`: windows, PuP screens, playlists, PinUP Player's Loop rules, CustomPos |
| `game/pup/gozen_player.gd`, `dmd_dots.gdshader` | GDE GoZen video playback (Linux), round DMD dots |
| `scripts/pup_setup.py` | the pack from its submodule or the author's zip, video add-on, conversion, the status line |
| `scripts/gen_pup.py` | the pack's videos to Theora (Godot's own format) with ffmpeg, `manifest.json` |
| `scripts/pup_captures.py`, `scripts/pup_decode.py` | match the captures against the game's frames, check the trigger map |

`game/pup_runtime/SOURCE` records the commit it came from. Never edit the copies in a game: change them here,
test (`python -m pytest -q tests`), and run `install.py` again in every game that uses them.

## What the game adds

| File | What |
|---|---|
| `game/pup.cfg` | every setting (below); `game/pup.local.cfg` (git-ignored) for a cabinet's screens |
| `game/<game>_pup/trigger_map.yaml` | what the pack's codes mean in this game (`[pup] trigger_map`) |
| `game/modes/pup/config/pup.yaml` | `mode: {code: pup_runtime.mode.PupMode, priority: 50, game_mode: false}` |
| `game/config/pup.yaml` | `modes: [pup]`, included by `config.yaml` (one line) |
| `game/project.godot` | `Pup="*res://pup/pup_player.gd"` in `[autoload]` (one line) |
| `scripts/setup.py`, `scripts/run.py` | `pup_setup.setup(venv_python, dry)` after the media; `print(pup_setup.status()[1])` before Godot |
| `.gitmodules` | the pack's private copy as a submodule, when the owner keeps one |
| `.gitignore` | `/pup_media/`, `game/pup.local.cfg`, `game/addons/native_video/`, `game/addons/gde_gozen/` |

The scripts need the game's `scripts/toolchain.py` (`ROOT`, `GAME`, `GODOT_VERSION`, `host_os`, `host_arch`,
`venv_python`, `python`) and `scripts/fsutil.py` (`copy_tree`, `remove_dir`, `replace`), as the master plan's
packaging kit has them. Video add-ons ship in `pup_addons/`: GDE GoZen plays the pack's mp4s on Linux and Windows
(FFmpeg, GPU decoding: Direct3D 11 Video / DXVA2 on Windows, the Jetson's decoder with libnvmpi), native_video on
macOS and as Windows' fallback (`[pup] video_player="native"`, Godot 4.6+). Theora conversion only where neither runs.
`python scripts/video_check.py` decodes a few pack videos with GoZen on the GPU and in software and prints the speed.

## `game/pup.cfg`

INI with JSON values (Godot's ConfigFile reads the same file). Transformers-MPF's is a complete example.

| Key | Meaning |
|---|---|
| `[pup] enabled` | false: no PuP at all (the strict game) |
| `[pup] env` | the game's environment prefix: `<env>_PUP=0` off, `<env>_PUP_ZIP=<zip>` the author's zip, `<env>_NATIVE_VIDEO=0`, `<env>_GOZEN=0` |
| `[pup] windows`, `optional`, `third_screen` | the windows in stack order; `optional` ones (a topper) follow `third_screen` |
| `[pup] music_screen`, `ost_music` | the pack's music screen (no window; Tron 15, Transformers 4); false keeps the ROM music |
| `[pup] pack_dir`, `media_dir`, `submodule`, `pack_repo`, `trigger_map` | where things are (repository root; `trigger_map` from `game/`) |
| `[pup] music_rows` | trigger row IDs used even though the pack leaves them inactive (Active 0), only with `ost_music`: a pack that ships its music switched off (Terminator 2: rows 123 / 124 and screen 4 off) |
| `[pup] bridge` | machine attribute path to the game's media bridge (`sound(call, index)`, `music_key`, `data["pools"]`), whose music calls are dropped while the pack's music plays |
| `[pup] state` | machine attribute path to the current player's rule state, given to every event as `state` |
| `[pup] attract_mode`, `attract_cycle_seconds` | `pup_attract_cycle` every so often while attract runs |
| `[pup] video_player` | `gozen` (default where installed) or `native` (Windows' fallback); `<env>_VIDEO_PLAYER` overrides it for one run |
| `[pup] layout`, `title`, `video_volume`, `music_volume` | `stack` (one under the other) or `manual` (per window) |
| `[<window>] layers=[n, ...]` | a window of PuP screens, bottom first; a screen with `CustomPos` in `screens.pup` sits in its box; ForcePop screens show only while playing |
| `[<window>] dmd=true` | the DMD window: `background` = `frame` (`frame_image`, `frame_crop`, `dmd_rect`), `black`, or `res://...gd` (a Control with `set_dmd_rect(Rect2)`); `dots`, `hide_main_window` |
| `[<window>] screen, position, size, fullscreen, borderless, fit, align` | placement; `fit` = `fit`, `fill` or `stretch` |
| `[captures] frames, event_map, event, id_regex` | for `scripts/pup_captures.py` |

## The trigger map

```yaml
counters:                      # the event gets count=1, 2, ... since a reset event
  game_deff_77: [game_deff_75]
dmd:                           # D<n>: the events of the effects that draw capture n
  2: [game_deff_25]
  23: ["game_deff_102{hit==1, completed==0}"]     # all conditions must hold
  10: ["game_deff_40{state.side==1}"]              # the player's rule state ([pup] state)
  158: ["game_deff_140{values.0==1}"]              # item 0 of the list argument `values`
switches: {11: s_center_lane}  # W<n>: the switch, by name
override: {23: [game_deff_112]}  # any row by ID (lamp terms, several terms)
```
