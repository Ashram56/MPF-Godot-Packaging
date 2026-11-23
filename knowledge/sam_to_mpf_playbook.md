# Stern SAM game to MPF: the playbook

Game agnostic. Everything here was learned rebuilding Tron Legacy LE v1.74 (the "Tron instance",
[Tron-Legacy-MPF](https://github.com/Ashram56/Tron-Legacy-MPF);
file paths in `code` are that repo's, use them as templates). Facts are tagged where it matters:
**[SAM]** true of every Stern SAM game, **[MPF]** / **[GMC]** / **[Godot]** toolchain behaviour,
**[Tron]** specific to that game.

## 1. Inputs and target

Inputs, from a ROM-decompilation repo (see [rom_extraction.md section 14](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/agents/rom_extraction.md#14-deliverables-checklist-for-the-next-sam-game) for what it should contain):
rules specs per mode, annotated decompiled C, an MPF config package (switches, coils, lights, settings,
shows, sounds), DMD media (frames, timing, reference captures, `rom_images_all.zip`), IO tables,
sound-call tables, and **reference traces**: scenario scripts replayed in an instrumented PinMAME,
logging every score, deff, sound, leff, audit, lamp and coil event as JSONL.

Target toolchain (pinned in one file, `scripts/toolchain.py`):

| Piece | Version | Note |
|---|---|---|
| Python | 3.11 (3.10-3.14 work) | stdlib-only setup script, per-OS venv paths |
| MPF | 0.80.1 (PyPI) | pin `ruamel.yaml.clib==0.2.14`: 0.2.15 breaks `mpf` once mpf-monitor is installed |
| Godot | 4.5.2 stable | download from GitHub releases (tuxfamily mirror may be blocked) |
| GMC (mpf-gmc) | 1.0.0 | not on PyPI: zip/git from github.com/missionpinball/mpf-gmc; needs a patch (section 6) |
| MPF Monitor | 1.0.0 (optional) | PyPI release lacks `core/ui/*.ui`; fetch them from the v1.0.0 tag |
| fontTools, Pillow | any recent | build-time media only |

## 2. Repository layout

- New **game repo**; the asset repo is a **shallow git submodule at `assets/`**. Never copy files out of
  it: generate from it, so an upstream fix reaches the game on the next sync.
- `game/` is both the MPF machine folder and the Godot project, kept apart from `assets/` so Godot does
  not import thousands of asset files (`.gdignore` in folders Godot must skip).
- Everything OS- or CPU-specific (venv, Godot binary, GMC add-on) and everything generated (config with
  MPF headers, slides, sounds, fonts, media data) is **git-ignored** and rebuilt by `scripts/setup.py`.
- Root `.gitignore` uses `/tools/`, not `tools/`, or `game/tools/` (Godot scripts) is ignored too.
- A scheduled sync job bumps the submodule and opens a PR listing changed areas when the asset repo moves.
- Hardware is an **overlay**: `config.yaml` is platform neutral (no `hardware:` section, ROM numbering);
  launch with `-c config,hw_virtual` / `hw_proc` / `hw_vpx`.

## 3. Architecture: model the SAM OS, let MPF own the hardware

MPF owns switches, coils, ball devices, trough, players and turn order. On top, a Python layer reproduces
what the ROM's OS does; most of the game's logic depends on these OS semantics, so build them first.

| Layer | Models | Tron file |
|---|---|---|
| OS layer | ROM **tasks** as tick timers keyed by ROM task id (1 tick = 16.26 ms in play [SAM]); game flags; audits; adjustments by ROM number; `score_add` (nothing while tilted or out of game); playfield validation; ball save; tilt; extra ball; end of ball, bonus, game over; multiball as one task; ball search | `game/tron/os_layer.py` |
| Switch layer | One handler per switch: repeat guard, then feature **hooks in the ROM's fixed order** (`os.hook(name)`), then base score | `game/tron/switches.py` |
| Features | One module per mode spec, registering under ROM hook names; per-player state reset on first ball; auto-discovered | `game/tron/features/*.py` |
| Display manager | Deff priorities, background deffs, foreground run length, 10-tick hold at low priority, **show queue** (show tasks wait for lower priority and oldest-first), **deff rules** that re-assert the background deff, music rules | `game/tron/display.py` |
| Lamp model | Game lamp image + flash mask, override layers by priority (leffs), lamp groups, list-5 "lamp rules" redrawn on every refresh, flashers as coil events | `game/tron/lamps.py` |
| Media bridge | Deff → GMC slide, sound call → one sample of its pool on its track, deff text formatting with live values, over BCP | `game/tron/media_bridge.py` |
| Settings / service | Adjustments as MPF settings, persisted audits, ROM service menu tree, credits/pricing, high scores | `settings.py`, `service.py`, `credits.py` |
| Trace logger | Same JSONL format as the reference traces, so the comparison tool works unchanged | `game/tron/trace.py` |

Keep ROM identifiers (task ids, deff/leff/sound numbers, function addresses) in names and comments.
They make every spec, trace and decompiled-code lookup a grep.

Effects are posted as MPF events (`tron_deff_<id>`, `tron_sound_<call>`, `tron_leff_<id>`,
`tron_tube_<id>`) and written to the trace at the same time.

## 4. Build order

Each step was a stacked branch/PR (next one based on the previous), tested before push, without waiting
for merges.

1. **Toolchain**: MPF + GMC boot, headless DMD capture (`render_check`).
2. **Machine + OS layer + switch layer + scenario harness**, then features mode by mode, each checked
   against its reference trace before the next.
3. **Media**: one GMC slide per deff (frames + ROM timing), sounds, BCP bridge; then ROM fonts and
   ROM text layout; then the score display (deff 19 on Tron) and status panel drawn as the ROM does.
4. **Lamps**: lamp model, leff layers from captured shows, code-drawn leffs, lamp/coil trace comparison.
5. **Service**: adjustments, audits, service menu, credits and pricing, high scores, attract pages.
6. **Hardware overlays**: smart_virtual + MPF Monitor, P-ROC (`driverboards: sternSAM`), VPX bridge.
7. **Portability**: one setup script for Windows/macOS/Linux, CI on all three, installers, Docker: the
   packaging agent ([`agents/packaging.md`](../agents/packaging.md)), started as soon as step 1 works.
8. **Optional HD display**: see `dmd_hd_upscaling.md`.

## 5. Verification loop (the part that makes it faithful)

- `tests/scenario.py <name>`: replays `assets/rules/traces/<name>.txt` (`start`, `hit N`, `wait s`,
  `mark`, `adj N v`) on smart_virtual; the runner plays the player (plunge, drain, trough switches).
- `scripts/trace_check.py <name> [--events kinds]`: compares the rebuild's JSONL with the reference
  (wraps the asset repo's `trace_compare.py`, aligned on a `ready` event, tolerance 0.25 s). It drops
  non-rule noise: OS bookkeeping audits, sounds played from inside a deff (checked with the media), and
  background deff re-asserts (`rule: 1`) unless `--strict`. Kinds: score, deff_start, sound, leff_start,
  tube_show_start, audit, multiball_start, mark, plus `lamp` (steady states) and `coil` (flasher/shaker bursts).
- `tests/test_traces.py` holds a **TRACES table: scenario → kinds that match today**. It is the regression
  net: add a kind when it matches, never remove one to get green.
- `scripts/render_diff.py`: renders slides in Godot at the reference capture's frame times and compares
  dot by dot; text must be pixel-exact. `tests/test_dmd_text.py` fails on blank printf lines, fallback
  fonts and empty DMD time during play.
- `scripts/render_check.py`: boots Godot + MPF and fails on a blank DMD.
- Unit tests cover paths no reference scenario reaches; seed the RNG in tests, never in live play.
- Tron result: score matches in 26/30 scenarios, audits 28/30, deffs 27/30 at the end of the rules phase;
  the remaining gaps were features built later.

## 6. Gotchas (each one cost a debugging session)

### MPF 0.80 [MPF]
- Generated YAML needs `#config_version=6` as the first line; the asset package's files lack it.
- Without a terminal start `mpf game . -t` (no curses UI). Don't pass `-b`: it stops MPF's connection to GMC (no display or sound). In MPF 0.80.1 the BCP servers, MPF Monitor's on 5051 among them, start whatever `-b` says (code, `mpf/core/bcp/bcp.py`; corrected 2026-10-12, it was written that `-b` stops the monitor's server too).
- MPF always serves BCP on 127.0.0.1:5051 (MPF Monitor's port) and **waits for GMC on 5050**: start Godot first.
- `bcp_trigger()` only reaches clients that registered the event name; GMC registers none for sounds,
  so every sound was dropped. Use `bcp_trigger_client()` addressed to `local_display`.
- Duplicate YAML keys: MPF's own loader (ruamel, `typ='safe'`) refuses them with `DuplicateKeyError`, but a generator writing YAML through PyYAML merges them silently (it keeps the last): an early asset package lost 8 switches and 8 lamps in that step, before MPF saw the file. Check generated YAML for duplicates (observed on ruamel.yaml 0.18.6, 2026-10-12).
- An autofire device marks the playfield active itself; remove `playfield_active` from those switches.
- `driverboards: sternSAM` goes under `hardware:`; under `p_roc:` MPF lowercases it and pypinproc rejects it.
- Platform classes use `__slots__`: patch at class level, not per instance.
- smart_virtual needs help: start with a full trough, make ejects move balls, shift trough switches
  toward the eject end (`virtual_hardware.py`).
- MPF waits for an empty playfield before the next ball; the ROM starts it (and the score display) as
  soon as the bonus ends. Restart the background deff at `ball_will_start`.

### GMC 1.0 + Godot 4.5 [GMC] [Godot]
New GMC / Godot gotchas go to [`fixes/`](../fixes/README.md), not here; the ones below stay because the recreation agent hits them first.
- GMC parses each socket read as whole lines; MPF's big `settings` message splits across reads and kills
  GMC's BCP thread (no sound after that). `scripts/gmc_patch.py` keeps the unfinished tail; apply it
  idempotently after every GMC install.
- GMC maps `gmc.cfg [keyboard]` by key label only (AZERTY breaks); the same patch adds a US-position lookup.
- When the last slide ends GMC falls back to its base slide. The ROM never clears the DMD: keep the last
  frame until the next effect.
- `--headless` draws nothing: render under Xvfb with `--rendering-driver opengl3`.
- A project never opened in the editor (no `.godot/` class cache, e.g. fresh from git) fails at start: `Could not find type "MPFDisplay"`, the MPF autoload does not load, GMC never listens. Import it first, twice: `godot --headless --path GAME --import` (observed, Godot 4.6.3 + GMC 1.0.0).
- `--write-movie` runs faster than real time, MPF never connects: capture with a real-time autoload
  (`game/tools/dmd_capture.gd`, inert without `--capture-dir=`).
- Probing port 5050 with a connection makes GMC quit: probe by trying to bind, and probe IPv6 too
  (Windows Godot listens on IPv6 only).
- Regenerating media deletes Godot's `.import` files; reimport after. Generated media is git-ignored, so
  after any pull it is stale: stamp the inputs and regenerate automatically on launch.
- **A colour LED DMD (PIN2DMD) needs no new platform code** [code, MPF 0.80.1]: MPF ships `mpf/platforms/pin2dmd.py`
  (pyusb, USB `0314:e457`, "virtual pinball" bit-plane packets `81 C3 E9 12`) and an `rgb_dmds` device that takes
  12288-byte RGB frames (128x32, row by row) over BCP as `rgb_dmd_frame` (name must be `default`). With GMC the game
  only reads back its own 128x32 picture (`get_viewport().get_texture().get_image()`, same as a P-ROC `dmd_frame`
  feeder) and sends it; GMC needs no screen for that. Overlay: `hardware: rgb_dmd: pin2dmd`, `pin2dmd: resolution:
  128x32`. Unit-test with `usb.core.find` mocked and call the device's `_send_frame` (the feeder runs in an executor
  thread the test loop does not run). Tron: `game/tools/pin2dmd.gd`, `game/config/pin2dmd.yaml` (Tron-Legacy-MPF
  PR #56); not yet tried on a real PIN2DMD (colour order, firmware).
- **A ZeDMD: MPF's own platform is fragile, write the serial client** [code, MPF 0.80.1; protocol from libzedmd, not
  captured]: `mpf/platforms/zedmd.py` needs libzedmd's compiled pybind11 extension, built for one Python each (it did
  not import on Python 3.13: `undefined symbol _PyThreadState_UncheckedGet`), and picks the library with
  `platform.machine in (...)` (the function, never called), so a Raspberry Pi loads the x64 one. A platform of your own
  (`mpf: platforms: name: module.Class`, pyserial only) works everywhere: handshake `FRAME` `ZeDMD` 0x0c, 64-byte reply
  (`ZeDM`, width/height u16 LE at 4/6, write size at 11, byte 57 'R'), the changed 8x4 zones as RGB888
  (`FRAME` `ZeDMD` 0x04 size-hi size-lo 0, per zone its index then 96 bytes, black zone = index + 128), `ZeDMD` 0x06
  render, 0x0a clear, every write-size block answered `ZeDMD` `A`; 921600 baud (115200 on the ESP32-S3's own USB).
  For less CPU, a small C feeder reading raw RGB frames on stdin (Godot starts it with `OS.execute_with_pipe`) skips
  BCP, MPF and Python; cross-compile it with `python -m ziglang cc -target aarch64-linux-gnu` (pip `ziglang`).
  Tests: a fake device (pty for the C one). Tron: `game/tron/zedmd_native.py`, `game/native/zedmd_feed/`
  (Tron-Legacy-MPF PR #56), also in MPF-Godot-Packaging PR #5; not yet tried on a real ZeDMD.
- **Run the real setup in a clean venv before telling a player to try a branch** [observed]: an optional dependency
  installed on your own machine (here `lz4`, imported by a new script) hides a missing requirement, and the player's
  setup then stops with `ModuleNotFoundError`. Also, MPF's event handlers must declare `**kwargs` by that name (a lambda
  with `**kw` is refused at `add_handler`).

### GMC + Godot performance on a slow target [GMC] [Godot]
Moved to [MPF-Godot-Packaging `platforms/godot-performance.md`](https://github.com/Ashram56/MPF-Godot-Packaging/blob/main/platforms/godot-performance.md) on 2026-10-27
(Godot / GMC findings are kept there; the display method is in [agents/improvement.md](../agents/improvement.md), section 2a).

### Portability
- utf-8 and LF for every generated file, `/` in `res://` paths, long paths on Windows.
- OneDrive folders: deletes/renames fail transiently; wrap them in retries (`scripts/fsutil.py`), and in
  shared caches keep the existing file when a replace races another worker, and treat a cache entry that
  cannot be opened (another worker is replacing it: PermissionError on Windows) as a miss, not a failure.

### SAM hardware [SAM]
- Dedicated switches use SAM numbering D1-D24 (PinMAME `sam.c`): coin 3, flippers/EOS 9-12, upper EOS 14,
  tilt 17, slam 18, spare 20, service 21-24. PinMAME's comment swaps Plus/Minus; its input port (what
  runs) has Minus on 22, Plus on 23.
- P-ROC numbers (libpinproc `PRDecode`, SternSAM): matrix n → `32 + 8*((n-1)/8) + 7-((n-1)%8)` when
  `(n-1)%16 < 8`, else `32 + n-1`; dedicated n → `n+7`; coil n → `n+31`; lamp n →
  `80 + 16*(7-((n-1)%8)) + (n-1)/8`. Generate the address file, never hand-write it.
- libpinproc to build (code, checked 2026-10-13 on Tron): `preble/libpinproc` branch `dev` (v2.1, last commit
  286c566, 2020-08, Multimorphic) is the newest; `missionpinball/libpinproc` is an older snapshot (34 commits
  behind, one warning fix ahead) with the same SAM code. Pair it with `missionpinball/pypinproc` (Python 3).
- `PRDecode` strings must be exactly 2 digits: `S05`, `C05`, `L05`, `SD3` or `SD03`. `S5`, `C5`, `L5` silently
  decode to 0 (atoi), a bare integer is taken as a raw P-ROC number, `S100` decodes to 40. Test the generated
  addresses against a port of `PRDecode` (Tron: `tests/test_proc.py`, identical to the compiled C on 351 strings).
- libpinproc safety on SAM (code): it refuses to open when the board's Stern/WPC setting disagrees with the
  machine type (`PRDevice::Create`; the comment in `PRHardwareOpen` saying there is no check is stale), it
  rejects a driver polarity that differs from the Stern default (active high), it tickles the IO board's
  watchdog and arms the P-ROC's own (1 s, MPF `use_watchdog`). Only driver groups 4-7 (coils 1-32) and 10-25
  (lamp matrix) are enabled: a `C33`+ address decodes to an inactive driver, never to an aux-bus output.
- Dimming on a P-ROC with SAM boards (code, Tron 2026-10-13): libpinproc's only PWM is the FPGA's patter, whole
  milliseconds on and off (pulse up to 255 ms; `schedule` is a 32-slot blink pattern, not PWM). Its LED colour
  and fade calls are for Multimorphic PD-LED boards only. The lamp matrix scan is set per driver group by
  `slowTime`, in microseconds (libpinproc's `pinproctest/drivers.cpp`: `startStrobeTime` is obsolete, the
  matrix loops as fast as the groups' slow times add up). libpinproc's Stern defaults: 16 lamp groups (10-25)
  of 400 us, two groups per strobe line, so a lamp gets 400 us in a ~6.4 ms loop (inferred from the config;
  stock SAM is 10 lines of 1 ms). `slowTime` can be changed after start with pypinproc
  `driver_update_group_config` (custom code; MPF's `lamp_matrix_strobe_time` only reaches PDB boards); the
  FPGA's lower limit is not documented. MPF dims a matrix lamp with a patter of at most 20 ms period (0.5 = 1 on
  / 1 off). Inferred: a whole-millisecond patter against that loop gives uneven duty,
  so dimmed matrix LEDs flicker or snap to full/off; keep matrix lamps on/off as the ROM does, and do any LED
  fading in a show at full steps or on hardware built for it (the RGB tubes: aux-bus bit planes, as the ROM).
- MPF's p_roc platform treats `SD0`-`SD7` as "first eight direct inputs" (PDB meaning); harmless on SAM,
  whose numbers never use the `x/y` matrix form that conflicts with it.
- Flippers: 40 ms pulse, hold 1 ms every 12 ms (`default_hold_power: 0.083`). Slings and pops are fired
  by CPU software on SAM; on a P-ROC make them hardware rules.
- Coil pulse widths live in the ROM's coil table and hardware rules (decoded for Tron: generate the MPF
  times from the asset repo's `rom_data/io/coils.csv`, as `scripts/gen_config.py` does); trace timings are
  16 ms samples, not widths.
- Pro and LE models of one title can share rules but not IO numbers. Keep the config in one model's ROM
  numbers, generate the other model's numbers as an overlay (unmatched devices on the virtual platform), and
  have the rules look devices up by name, never by the configured number (`tron/hw_numbers.py`).
- Aux-bus outputs (latched coils 33+, RGB tubes, GI relay bit) are not P-ROC drivers. A wrong aux address
  can fire a coil bank: keep such code off until checked with a logic analyzer.
- Coin door open comes from the IO board interlock status, which a P-ROC cannot read; wire a spare input.
- The sound system is on the CPU board; a CPU replacement means PC audio.
- PinMAME numbering for VPX differs from the P-ROC: tube lamps 101-106, sol 33 = fast-flip toggle,
  negative dedicated switch numbers. VPX loads `<table>.vbs` beside the `.vpx` as a script override;
  never rewrite the `.vpx` (VPX checks its MAC).

### SAM ball counting (multiball, lost balls) [SAM]
- **Balls in play = installed - balls in devices**, recomputed on demand (`balls_in_play`, Tron 0x0001e4a8). A
  ball held in a scoop or VUK is not in play. While the multiball task runs, it returns the task's requested
  count instead. MPF's `game.balls_in_play` is event-driven (it counts launches and drains), so port the ROM
  value as its own function (Tron `rom_balls_in_play`) and feed every `multiball_start(balls_in_play + n)` and
  `multiball_add_balls` from it, never from MPF's count. Tron's End of Line add-a-ball used MPF's count and
  asked for one ball too many while a ball sat in the scoop. (code: Tron LE 1.74 `multiball_add_balls`
  0x0001eeb0)
- **`multiball_start(n)` brings balls in play up to n; it does not add n.** The launch count is worked out
  when the task runs, after the devices have released their balls (`FUN_0001e738` on Tron). So a "balls in
  play + 1" request made while a ball is held in the scoop adds nothing once that ball is back in play. On
  Tron, starting a second multiball at a later scoop shot (Quorra during Light Cycle) adds no ball, but
  starting both on the same shot gives 3, because the task is still running. Log it as a ROM quirk; don't
  "fix" it in the strict build. (code: Tron LE 1.74; the same-shot case observed in the
  `light_cycle_multiball_repeat_and_stack` trace)
- **Lost ball recovery** (Tron adj 63, after the 5th failed ball search): the missing balls come off the
  installed count and new ones are served. The count goes back up only when the trough holds more balls than
  expected (`trough_drain_check`). If the stuck ball comes free and drains first, the ball ends with a served
  ball still on the playfield. That is the ROM's behaviour, but simulators (VPX) strand balls far more often
  than a real machine. (code: Tron `ball_search_start` 0x0001f79c, `trough_drain_check` 0x0001dd90)
- **Test ball counts on a simulated table**, not only on `smart_virtual`, which moves one ball per device
  and per eject. In an MPF test on the plain `virtual` platform, replace the eject coils' `hw_driver.pulse`
  with a small table model (trough stack, shooter lane, scoop stack, playfield). Then drive drains, scoop
  entries and stuck balls, and compare `game.balls_in_play` with the balls the model holds. (Tron
  `tests/test_ball_tracking.py`)

### ROM display semantics (where the first build looked wrong) [SAM]
- **Never an empty DMD in play**: after any foreground deff ends with nothing behind it, the deff rules
  restart the background deff (score display or the mode's).
- **Text arguments follow the ROM format string order**, not your call order. `%P` (plural) is not an
  argument; a non-number in a numeric spec prints nothing; `%,02lu` of 0 is `00`.
- **Values come from RAM, live**: status screens reprint timers/scores every refresh (`os.deff_live`).
  A printf line left blank is a bug; make the test fail on it.
- **One deff, several screens**: many deffs pick a screen by argument or phase; show only the selected one.
- **Reference captures are one run**: random choices (mystery awards, clip picks) and the status panel
  (score 00) are frozen in them. Build those deffs from the rules' arguments and draw the live panel over.
  Some captures hold two runs (sounds play twice); use the ROM run length.
- **State frozen in a capture shows as a dead input**: a deff that draws per-player state (Transformers deff 40
  draws the chosen side's logo, deff 41 its name) was captured in one state only, so the flippers changed the
  side and the music but the DMD never moved and the owner reported the buttons as doing nothing. Read the
  deff's draw calls for the other state's image or message and build that slide from the capture with it in
  place; and a deff that redraws in place on input (no new start in the ROM trace) must still re-post its
  `tf_deff_<id>` event, or a PuP Pack keyed on it never sees the change (Transformers-MPF PR #3).
- Fonts: the font table and glyph offsets are code data, not in the images; the font index is the image
  group index. Text drawn in Godot's default font anywhere is a bug (test for it).
- Sound calls `0x01-0x08` are channel stops; music calls replace the running music.
- When the sound calls are not decompiled yet, derive them from the reference traces: for each display object (and
  its variant byte) and each switch, the sound commands sent within 0.2-0.25 s in at least ~80 % of its showings or
  hits; bumpers and slingshots play one sound from a set each hit (pick at random from the observed set). Play the
  table's sound unless the feature already sent it (dedup by command, 0.25 s), and compare per scenario window
  (`--kinds sound`). On LOTR (Whitestar) this took sound recall from 7 % to 41 % at 79 % precision
  (`game/scripts/gen_obj_sounds.py` there). Also from the traces: the main music at the start, a launch sound per plunge.
- Credits: MPF's credits mode applies its own `free_play` setting when it starts; calling `enable_credit_play()` again
  registers the coin handlers twice (one coin counts double). Map the ROM's FREE PLAY adjustment onto it only when the
  two differ.

## 7. Working rules

- Spec conflicts: the rules spec wins on rules, the MPF package wins on media and names, the annotated
  decompiled C settles disputes. Mark anything inferred as `(inferred)` in code.
- Do not build code the ROM cannot reach (dead modes in the shipped version).
- Classic output must stay exact: any optional display mode (HD, colour) is a switch, and pixel-hash
  tests guard the classic frames. Re-take a hash only after rendering the same frames on the base branch.
- Stack branches, run `pytest` + the trace checks + `render_check` before every push; CI on 3 OSes.
- Write what a successor needs into memory or these docs; commit messages explain each fix.
