# Agent C: strict recreation of the ROM's game in MPF

> **Feed back what you learn.** Whatever game you run this agent on, report every game-agnostic learning to
> Ashram56/MPF-Godot-Packaging (this repository) in the same session, without being asked: a pull request if you
> have write access, otherwise a GitHub issue opened directly. How and what: [CONTRIBUTING.md](../CONTRIBUTING.md).
> **Route it:** MPF implementation learnings (rules, display, sound, VPX bridge, PuP, install kit, Godot, GoZen,
> GMC, MPF, platforms and boards) stay here. Taking a ROM or a VPX table apart (formats, decompile, traces, IO
> tables) goes to [Ashram56/Stern-SAM-Decryption](https://github.com/Ashram56/Stern-SAM-Decryption) instead (its
> CONTRIBUTING.md), with at most a pointer here.

Rebuild a Stern SAM game in MPF + Godot (GMC) **exactly as the ROM plays it**: rules, scoring, display,
sound, lamps, service menu and every operator setting. Nothing here improves on the original; that is the
optional [improvement agent](improvement.md). Part of the [master plan](README.md) (A to G in full: [Stern-SAM-Decryption `agents/README.md`](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/agents/README.md)). Tron Legacy LE 1.74 is
the worked example. File paths in `code` are the Tron game repo's ([Tron-Legacy-MPF](https://github.com/Ashram56/Tron-Legacy-MPF)) unless said otherwise.

## 1. Scope

**In** (all as the ROM does it, from the code: A's functional diagram, specs and `rom_data/`; traces only confirm):

| Area | Includes |
|---|---|
| Rules | every reachable mode, multiball, hurry-up, wizard mode, combo, skill shot, extra ball, ball save, bonus, match, tilt and slam tilt, ball search, playfield validation, multi-player |
| OS semantics | ROM tasks as tick timers, switch hooks in the ROM's order, deff priorities and the show queue, deff/lamp rules, audits, `score_add` gating |
| Display | one slide per display effect with the ROM's frames and timing, the ROM's fonts and text layout with live values, the score display and status panel, attract pages, **classic 128x32 output byte-exact** |
| Sound | one pool per ROM sound call, channel stops, music replacement |
| Lights | lamp states, lamp-matrix effects (captured and code-drawn), flashers, GI, game-specific outputs (Tron: RGB ramp tubes), shaker |
| Service | **service menu reached as on the machine** (coin door buttons BACK, MINUS, PLUS, SELECT), every adjustment with the ROM's labels, defaults and ranges, audits with their formulas, credits and pricing tables, high scores, coin door open / interlock behaviour, tests the menu offers |
| Hardware overlays | virtual (desktop + MPF Monitor), the real machine (Tron: P-ROC on the SAM boards), every model of the game (Tron: Pro default, LE), the ROM's coil drive times |

**Out**: anything that changes what the player sees or hears compared with the ROM (HD display, other fonts,
colour, glow, new modes, rule changes) belongs to the [improvement agent](improvement.md). The VPX bridge is
the [VPX bridge agent](vpx_bridge.md); the MPF Monitor layout comes from the [VPX extraction agent](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/agents/vpx_extraction.md);
installing and starting the game on each platform (`setup.py`, `run.py`, the installers, Docker, CI) is the
[packaging agent](packaging.md). C adds a `run.py` or `setup.py` option for its own features (a hardware
overlay, a model) and tells the packaging agent, which carries it to every installer.

## 2. Read, in this order

0. **Gate (STRICT RULE: DECOMPILE EVERYTHING, owner 2026-11-24).** Before coding a feature, check in the asset repo that `docs/boards_inventory.md`
   shows every board it depends on as `complet`, that A's visual diagram (one ROM address per node) covers it, and that
   `python tools/check_strict_rule.py .` passes there. Otherwise stop and send A one batched request. Never build a rule, image,
   DMD frame or sound table from a PinMAME capture or trace; only the owner can approve that exception, beforehand.

1. [sam_to_mpf_playbook.md](../knowledge/sam_to_mpf_playbook.md): architecture, build order, verification
   loop and every gotcha so far. It is this agent's main manual; this page adds scope and what changed since.
2. The asset repo's `AGENTS.md` section 14 (what it delivers) and `rom_data/README.md` (where each fact is;
   `rom_data/` wins over older files).
3. The game repo's `docs/rom_differences.md` (Tron: [rom_differences.md](https://github.com/Ashram56/Tron-Legacy-MPF/blob/main/docs/rom_differences.md)) before changing any rule: what is meant to differ, and ROM
   behaviour that looks like a bug but is the original.
4. The [knowledge base README](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/knowledge/README.md)'s token rules: grep specs, read module docstrings, `git log --no-merges` for the why.

## 3. Definition of done

- `tests/test_traces.py` (scenario → event kinds that match the reference trace) only ever gains kinds; a
  feature is accepted when every rule cites its ROM routine (from A's functional diagram) **and** its scenario's
  trace matches (`scripts/trace_check.py <scenario>`). A trace match alone does not accept a feature.
- Before coding a routine A names, check that it has a caller (a jsr, a far call with its bank, or a table entry
  holding its address). A routine with no caller is dead code: leave it out and say so. LOTR example: the Balrog
  "right VUK hits to light 3, 7, 21, 55, 99" routine 59:503D has no caller. The Balrog really starts from Gollum's
  cave consolation (59:6F59) and from a Mystery award.
- Look for silent counters at the end of the shot chains. A hook at the end of a chain may count something with no
  score and no display. LOTR's ring spotting (58:50C4 / 50F7 / 5122) is one: it shows up only in the end-of-ball bonus.
- `pytest -q tests` green; `scripts/render_check.py` (no blank DMD); `scripts/render_diff.py` for display work
  (text pixel-exact against the reference captures); classic frames unchanged (pixel-hash tests).
- Unit tests for paths no reference scenario reaches; RNG seeded in tests only.
- The rules test bench (section 4b) green: modes one by one, adjustments in play, random games.
- No unreachable ROM code built (the asset repo lists dead code).
- Where MPF cannot do what the ROM does, the smallest departure that keeps the player's experience, logged in
  `rom_differences.md` with the ROM's behaviour and its address, and said to the owner.

## 4. Learned since the playbook (2026-10-04 to 2026-10-08)

- **Attract, credits, parametric screens and lamps before the first owner test** (missed on three games; the
  owner's first test finds them at once). Before handing over a playable build, check each:
  1. **Attract is the ROM's own loop**, not one MPF slide: find the attract task's step table (each step: a
     display object or deff, a wait in ticks, a condition such as an adjustment or "a game was played"), build it
     step for step with its durations and conditions, and let the flippers step it as the ROM does. A test
     asserts the order over two full cycles. LOTR: 22 steps at 61:42A1, 16.4 ms ticks, $027D stepped by the
     flippers (`game/lotr/attract.py`).
  2. **A coin must change what the player sees.** Find what the ROM shows after a coin (LOTR: INSERT COINS, then
     the cycle restarts on the score screen 4.0 s after the last coin, which shows the credits) and test it: coin,
     wait, the credit count is on the display. A credits screen captured once shows one credit count forever.
  3. **A display object with parameters is not one capture.** If the DMD replays one capture per object, every
     object whose look depends on its parameters (names picked by an index, values, ranks, credits) is wrong in
     play (LOTR: the member award always showed ARAGORN, so the owner read it as "Aragorn is always collected"
     although the rules collected the right member). List these objects from the parameter table, then ask A
     for one render per discrete value and two renders per numeric object (or the field table: x, y, font,
     alignment per parameter) in one request, and log the rest as a departure.
  4. **Lamps from the code, not only the mode inserts.** Ask A for the lamp logic of every lamp (state by RAM
     flag, the redraw routine, attract and event lamp shows) together with the rules; until then light each lamp
     from the features' state and label it inferred. Drive lamps from a clock interval, not the game's delay
     timers: an extra repeating game timer shifted the order of same-instant DMD objects in two trace windows
     (LOTR).
  Lamp traces read from the emulator's lamp matrix while it strobes see only part of the columns per sample (LOTR:
     alternating 0x5 / 0xA nibbles): replayed raw they flicker at random. OR the samples over a window longer than
     one strobe cycle (LOTR: 70 ms) before replaying or measuring a flash, and turn every lamp off when a game
     starts so the attract show's lamps do not stay lit where no rule redraws them.
  5. **Captures by injection start with the previous object's frames**: trim them (LOTR `gen_media.py
     trim_carryover`: leading frames within 400 ms that match the previous object better than the object's own).

- **Coin door open** (deff 4, priority 247, never ends by itself): "50V / 20V DISABLED" covers the display
  while the door is open, dims after 30 s; BACK takes it away (sound 0x009) instead of a service credit; the
  interlock cuts every coil but the optional coil 24. Model the power handler, not a timer
  (`os_layer._power_off_warning`, `tests/test_coin_door.py`). [SAM]
- **Service menu during a game**: the ROM suspends the game task (`task_suspend(0, 0x800)`) and resumes it on
  exit. MPF's timers cannot be suspended, so the game asks "END GAME?" and a second SELECT ends it into the
  menu (logged as a departure). [MPF]
  Every effect that hangs off the normal game over (music, PuP/OST, lamps, audits, high scores) is skipped on
  that route: for each game end that is not the ROM's own (service menu, slam, reset), list those effects and
  redo them explicitly. Tron: the PuP OST of the cancelled game kept looping into attract, which sounded
  quieter; `tron_service_entered` now stops it (observed, 2026-10-27; the Godot side is
  MPF-Godot-Packaging `fixes/godot/audio-only-screen-keeps-playing.md`). [MPF]
- **Pro and LE**: one config in one model's ROM numbers, the other model as an overlay; rules look devices up
  by name (`tron/hw_numbers.py`). Pro decompile: outputs the Pro lacks are reused as flashers (Tron Pro ramp
  flashers 19/25, lower flashers 22/23 fired with them). docs/hardware.md "Pro or LE". [SAM]
- **Asset sync**: a scheduled job opens "Sync assets to <sha>" PRs; run setup, the render check and the tests
  on it, then the owner merges. [Tron]
- **OneDrive**: deletes and renames fail transiently; every build-time file operation (generators included)
  goes through `scripts/fsutil.py`. Installer lessons (private repositories, PowerShell 5.1) are in
  [packaging.md](packaging.md).
- **CI runs only on pushes to `main`**: test locally before pushing a branch, don't wait on CI there.
- **Answers that matched the ROM** (check before "fixing"): Disc Multiball "JACKPOT" screen on every blue
  shot; Sea of Simulation stages played by their shots pay the shot value, not the stage million. Both are
  in `rom_differences.md`; future owner reports may be the same kind.

## 4b. The rules test bench (from Tron, 2026-11-15)

Trace tests prove the game against what the ROM was recorded doing; unit tests prove one function. Neither
plays the game. Build a **bench** once the modes exist and run it before and after every rules change (Tron:
`tests/bench/`, `scripts/bench.py`, [test_bench.md](https://github.com/Ashram56/Tron-Legacy-MPF/blob/main/docs/test_bench.md)).
On Tron it found five bugs that 440 tests and 30 trace scenarios had not.

| Piece | What it is | Why |
|---|---|---|
| A physical table model | The machine's real balls, each in one place (trough, shooter lane, VUK, playfield), moved only by a coil or the player. MPF on its plain `virtual` platform, coils patched to move the balls. | MPF's `smart_virtual` moves balls by itself and hides every ball-count bug: a ball the rules count must be one the table holds. |
| A player robot | START, plunger, flippers, tilt bob, and the ball sent to a shot, the scoop or the drain; it cannot close a switch with no ball on the playfield. `start_<mode>()` helpers reach each mode through the switches. | Tests written as a player plays read like the spec and reach the states a player reaches. |
| Invariants after every action | Ball count on the table, scores never down, nothing scored while tilted, which modes may run together, value ranges, rules' balls in play = balls out of the trough once still, nothing of the last ball left at a new ball, all balls home at game over. | A corner case shows as a broken invariant long before anyone writes the test that names it. |
| Mode by mode | One test file per group of modes, each test written from the spec's trigger / condition / score / display / sound table. | The exhaustive review: every line of the spec is either asserted or found wrong. |
| Adjustments in play | Each adjustment set through the service menu with the door buttons, then a game played to see its effect; a table lists every adjustment as played or why not. | Writing `adj[n]` and calling the rule's function does not prove the menu's value reaches the game. |
| Stress | A seeded random player (shots, dirty shots, drains, tilts, extra players, waits) over whole games, the modes started in every order, each multiball after and before the others, all balls draining at once, a tilt in every multiball. A failure prints its seed and last actions. | Finds the interleavings nobody thinks of. Run hundreds of seeds once ("soak"), a few in the normal run. |

Lessons:

- **Check a "bug" against the decompile before fixing it.** About ten of the bench's first failures were the
  ROM's own behaviour (Tron: `task_kill(0, 0x100)` at the end of ball *keeps* the tasks with flag 0x100, so the
  combo windows survive it; two modes starting on one scoop entry; a hit that only resumes a multiball). The
  mask argument of `task_kill` is a keep mask. [SAM, code]
- **Specs have arithmetic and wording slips**: when the spec and the game disagree, read the address the
  spec cites (Tron: a weight total of 352 whose own table adds up to 327; two specs disagreeing on which
  switches validate the playfield). Report them to the asset repo. [observed]
- **The robot must not do what no ball does**: draining a ball before MPF has counted it on the playfield
  (MPF takes it for a failed eject and ejects again, for ever), or draining every ball while the multiball
  task still launches. Both look like game hangs and are bench bugs. [observed]
- **Fixes move trace times**: run the trace tests after every fix the bench suggests (Tron: a shorter
  shooter lane count delay made every auto-launch 0.4 s early; the waits before it took the 0.4 s). [observed]
- **Game states the traces never visit** are where the bugs were: a tilt between a multiball's start and the
  launch of its balls, a ball plunged at once, a game restarted with a ball in play (the ROM's "game
  starting" state 0x20 was missing, so switches ran on a player with no data), the match with its
  adjustment OFF. Play each OS adjustment at its extreme values. [observed]

## 5. Starting a second game (from Transformers Pro 1.80)

What the second game showed (Transformers-MPF, ROM tf_180, 2026-10-04 to 2026-10-10); read before porting a third.
Each line has the Transformers value as the example.

**Setting up**

- **Start from the previous game's OS, not from scratch.** Compare the new ROM's OS tables with the old one's
  first (A's `rom_map.json` table registry): on tf_180, deffs 1-39, leffs 1-19, sound calls 0x001-0x019,
  adjustments 1-64 and the audit counter ids have Tron's numbers, priorities and flags. Copy `game/tron` as
  `game/<tag>` with a rename (`tron` -> tag, `TronOS`, event prefix, env vars), keep the OS modules, and isolate
  every game value (start/shoot-again lamps, music and speech calls, game-over leff) in one `GAME` dict set to
  `None` until A's specs say otherwise. The machine boots and plays a full game on virtual hardware in a few
  hours that way; the boot test is the first test to write. [code]
- **One repository** works: A in `rom/`, B in `game/monitor/` + `docs/vpx/`, C everywhere else. Merge A's and
  B's branches into C's (the first merge needs `--allow-unrelated-histories`); re-merge as they push.
- **Read what A has not packaged yet from the ROM yourself**, as interim files under `game/config/interim/`
  with a generator that needs the ROM path (adjustments, audits, deff and leff tables, the font table), and let
  the build prefer A's files when they land. It keeps C unblocked without guessing.
- **Dedicated switches** come numbered 129-160 in A's package (128 + n): `gen_config.py` turns them into "D<n>".
- **Fonts are ROM data**: the font table gives every glyph's image and x/y offsets, so `gen_fonts.py` builds
  BMFonts straight from `fonts.json` (Tron had to rebuild offsets from captures).
- **A's per-deff `timing.json` carries every text draw** (`pages[].texts`: string, font, x, y, flags, return
  address) and image draw. Layouts come from there, not from guesses; the status panel is found by its draw
  call's return address (`216cc` on tf_180). A page whose texts are all panel calls is not a value page.
- **Music loops**: A exports intro + looped body as one WAV with `loop_start_at`; write a RIFF `smpl` loop into
  the copied WAV and Godot's importer loops only the body.
- **Godot imports CSVs as translations**: put a `.gdignore` in `game/config/` when CSVs live there.
- **Leff tables can move between A's releases** (Transformers: `rom_data/io/lamp_effects.csv`, `loops` = yes for
  until stopped, `tag` = code for leffs drawn from game state). When the traces log coil drivers raw (3-17 ms
  slices), drop Tron's 0.24 s coil hold (`COIL_OFF_DELAY`).

**Matching the traces**

- **Drive scenarios on the reference's input times** (each hit, drain and button waits until the reference
  input's time after "ready"); otherwise timing drifts up to 0.4 s across a long trace and every timed rule looks
  wrong. Replace the old game's switch numbers in the runners with the new game's ball device holes. Forced
  random picks come from watched variables, or, when none is traced, from the scores and audits they cause
  (Transformers: mode-start relight picks from the mode-start score caller and shot audits). Ignore values that
  are uninitialised RAM (0xffff before the game starts).
- **Pin every random pick in the trace replays, or the floor is noise.** A pick the reference never shows (no
  mode started) still needs a fixed value in the runner; otherwise the regression floor moves from run to run
  (LOTR: the first ring mode left to `random` swung one scenario's DMD matches between 2 and 3). When a rule's
  random draws cannot be recovered from the trace (LOTR's ring type refill, fix 0xEE95), build the code's rule for
  play and let the replay use a fixed, observed model behind a module flag; say so in rom_differences.md.
- **Check a spec's condition polarity before coding it.** A condition read from a disassembled table can come out
  inverted: LOTR's Palantir award 3 (ball saver, 58:5342) was specced "no multiball", but the branch after the
  multiball test is `bcc` to the failure, so it needs one; the trace (a single ball gave award 8) settled it. When a
  table of conditions is first-match, run the trace's case through it by hand and confirm the award it shows.
- **Read the gate, not its name.** A decompile name can say the opposite of the code: `any_timed_mode_running`
  [0x01006704] tests the six multiball flags; the timed modes are [0x010067bc]. Ask A for the flag list behind
  every "multiball / timed mode" condition and check it against a trace where only one of them runs.
- **Switch flags matter.** The captive ball (flags 0x1fff0000) runs its handler on both edges, 3 ticks after each.
- **A captured deff starts its own leffs and sounds.** Calling `leff_start` too doubles them in the trace; start
  the rule's leff and first sound only when the capture lacks them. Passing `sounds=` replaces the capture's
  sounds, so use it only for deffs with none. A deff with no capture length never ends and blocks every lower
  one: give each such deff a length from the traces.
- **Show tasks**: a show ends when another effect replaces its deff; queueing a show task that is already
  playing replaces it; a multiball intro waits on its own priority, not on the show below it.
- **Sound channels decide some rules.** A sound call is refused while a higher priority sample holds its channel
  (sample `mask` in samples.csv, low byte of the call's flags); a rule that retries until it plays then acts at
  once (Transformers' eject warning: 937 retries, logged). Track the playing samples to know.
- **The shaker** belongs to the deff, not the rule: run it when the deff gets the display (A's `shaker.csv`),
  never when the rule requests it; a new run never cuts a longer one short.
- **Ball search timing is a reload hunt.** Each search at the wrong time is a missing or extra reload: look 10 s
  before the ROM's search for the event that reloaded it, then grep the decompile for the reload function's
  callers (tf_180: score, playfield switches, each show task at queue, start and end, the mode totals, the deffs
  of FUN_01006350; flipper buttons pause it; a scoop eject does not reload). Once scores match, compare one
  kicker's coil on-times per trace: they show every search (Transformers: all searches matched).
- **Ball end clears the display, the ROM does not always.** A mode total on screen at the drain plays out before
  the ball-end total shows again (tf_180 deff 137); time it from its start.
- **A multiball's end waits for a lock kick in progress**: the drain check defers while a device is kicking.
- **Timers that pause**: the combo window does not count while the eject holds a ball ([0x0103a4f0(3)]).

**MPF and Python**

- **MPF ball devices**: a ball that comes back while an eject is unconfirmed is a failed eject to MPF and goes
  straight out again; keep `eject_timeouts` under the scenario's shortest return (1 s on the left eject, with the
  ROM's 2 s device task kept in the rules) and lower `exit_count_delay` / `entrance_count_delay` to let a lock
  release four balls 0.4 s apart. A ball hold must cover every ball the rules keep. Log the eject coil yourself
  if the trace check compares it (MPF's pulse is not in the trace).
- **Mechs on virtual platforms**: model them as the reference emulator does, not as the machine (the Optimus
  figure's position switches never move in the simulator, so every move runs to its 7.65 s time limit).
- Do not give a feature an attribute and a method of the same name: Python replaces the method silently and
  the hook dies with "int is not callable" deep in a scenario.

## 5a. The rules test bench on Transformers Pro 1.80 (see 4b for the Tron bench)

Build a bench early and make it the gate for every rules change (Transformers-MPF: `tests/bench/`, `scripts/bench.py`,
`docs/test_bench.md`). What worked:

- **Layers.** Per mode, from the rules spec, each with its ROM address in the docstring; game flow and several
  players; a register of every operator adjustment where each one has a test or an explicit reason
  (ROM-unused, not modelled, machine); the reference traces against a stored baseline (they must not match the
  ROM less than today); seeded random games ("stress") with invariants checked after every action. Stress found
  more bugs than the hand written tests (137 games: the last two failures were ball-count races).
- **Run on MPF's `smart_virtual` platform**, no ROM, no Godot: the bench plays the ball (drain, plunge, lock,
  shoot a switch) and checks a census (balls in the trough, shooter lane, devices, playfield) against
  `game.balls_in_play` once nothing is in transit. A failing seed prints its last actions and replays.
- **Per-player state.** Stern keeps a per-player game flag table (Transformers [0x040cf458], saved and restored at
  each player change); read it from the ROM instead of guessing which flags belong to the player.
- **Ball counting.** MPF caps `game.balls_in_play` at `ball_controller.num_balls_known`: an increment made while
  every ball is already in play is silently lost (a "capped by num_balls_known" warning), so a replacement ball
  that cannot be served yet (outlane save with all balls rolling) must be counted when it is served, not when it
  is announced. A ball a device keeps (a lock) leaves the count at once when no ball can be served after it.
- **Game-agnostic MPF pitfalls hit** (details belong in MPF-Godot-Packaging): BallHold default reset events,
  `add_ball` queued until the next drain, `balls_in_play = 1` set after `ball_starting`, ball start waiting for an
  empty playfield.

## 5b. A WPC 6809 game (from Terminator 2 L-8)

What the first Williams WPC game showed (Terminator 2 L-8, in its private game repository, 2026-11-21). The OS facts are in
[knowledge/wpc_6809.md](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/knowledge/wpc_6809.md) where present; these are the build lessons. T2 values as examples.

- **Compare window by window, not event by event.** The trace check cuts the reference and the rebuild at the
  scenario's marks and compares per window the score delta (from the marks' player score), the set of sound
  commands, lamp effects, display effects and coils. Sets survive the 10-50 ms jitter of an emulator; keep a
  per-scenario floor (`tests/trace_floor.json`) that only goes up. T2: 192 windows, 182 scores matching.
- **Replay the reference's random outcomes.** Jets and slings pick a random score and sound; the runner reads
  each hit's `score_idx` and sound from the reference and hands them to the rule in order, so the windows compare.
  Strict play keeps the ROM's random draw.
- **The emulator has phantom switches.** PinMAME's ball simulation closes switches the host never logged (T2: 72
  TARGET 2 about 0.73 s after every plunger pulse; a "10,000 + leff 2e" after each multiball launch looked like a
  rule for a day). When a score has no switch behind it, ask A to log the simulator's switch changes
  (`sim_switch` in t2_ref12) and replay them; never build them into the rules. Replay by pulse, not by clock:
  for the k-th coil pulse of the reference, close the same switches at the same delays after the rebuild's k-th
  pulse, and skip the pulses the player caused (a gun shot: the rule scores its own target). Only playfield
  switches: the simulator also logs trough, gun motor and drop target resets the rebuild models itself.
- **A screen that shows up in odd places may be an award you have not built.** T2's deff 14 + leff 36 + coil 7
  was put in a lock rule, then appeared in the bonus count: it was the replay (knocker), the score crossing
  REPLAY AT. Before coding an effect into a rule, check whether the score crossed a threshold (replay, extra
  ball, high score) in that window.
- **Host key presses can be lost by the emulator.** PinMAME's keyboard handling releases host-set flipper and
  START switches about 20 ms later; whole high score entries stalled in the reference. Ask A to press PinMAME's
  own keys for button scenarios (T2: `ex_hsk`, `ex_hs2k`) and treat the lossy runs as non-references.
- **Line up power-on.** The reference starts at power-on (T2: attract 3.11 s, `ready` 8.0 s); let the rebuild
  boot the same distance before `ready` and re-stamp the events already logged, or the power-on sequence lands
  in the first scenario window.
- **Keep generated runtime data out of MPF's `data/` folder.** That folder holds machine variables and audits per
  cabinet; packagers refuse it. Put generated tables (lamp effects replayed from traces, fonts) with the media.
- **Time the end of ball from the outhole switch.** MPF ends the ball about 0.5 s after the drain switch (device
  confirm); the ROM's bonus count, ball start and game over are timed from the drain. Record the drain time on
  the outhole switch and shift the end-of-ball timeline back by the difference.
- **Rules hold balls by claiming them.** A ball that enters a device no rule claims is ejected by MPF at once; the
  rules answer the relay event `balldevice_<device>_ball_enter` with `unclaimed_balls: 0` and kick it themselves
  (MPF detail: MPF-Godot-Packaging). With `entrance_count_delay` at 200 ms the rule reacts at the ROM's time.
- **Sounds are dropped by the OS's priority test, not queued.** WPC's `sound_call` (T2 fix:bdfb) reads a 5-byte
  record per call from the sound call table (T2 3d:4e38): command, length in IRQ ticks, priority, unused, flags
  (bit 1 sent as `7a` + command, bit 3 the second channel, bit 5 an equal priority may replace it, bit 6 nothing
  may). While a channel's sound runs, a call of lower priority is dropped (fix:beb0). Export the table and run the
  same test in the game for the rules' own calls; the sounds that lamp and display effects send are not calls and
  bypass it. On T2 it explained every "missing" sound in the traces at once (an extra ball speech eating the drop
  target speech, a combo sound lost after a hurry up collect) and replaced the special cases built for each.
- **Have the rules reviewed against the decompile once they pass the traces.** Traces only cover what a scenario
  reached. On T2 three independent read-only reviewers, each given one scope (playfield, gun and multiball, OS and
  game flow), the decompiled listings and the game code, found 37 code-proven gaps that no trace showed (a second
  ramp counter, a jackpot timer, the gun target count per multiball, the high score champion kept apart). Fix each
  from the code, keep the trace floor as the guard (it rose on T2: sounds 224 to 230, displays 247 to 253 of 263
  windows), and put what stays open in `rom_differences.md`.
- **A QA pass for a game built before the strict rule** (Transformers Pro 1.80, 2026-11-25). Run the review above
  in QA mode: three read-only reviewers (OS and game flow, modes and multiballs, playfield scoring), each with the
  decompile, the ROM and the game's test harness, each finding proved by the decompile and, where it can be, a probe
  test that prints the game's value next to the ROM's; the reviewers fix nothing. Keep the reports and probes in the
  game repository (`docs/qa/<date>/`), fix the high ones from them with one regression test each, and list the rest
  as open with one row in `rom_differences.md`. On Transformers they found 53 differences in a game whose 24 trace
  scenarios passed (none of the 8 fixed ones changed a trace comparison). For the strict rule's files, write
  them honestly rather than to pass the check: the boards inventory with the real state, the functional diagram
  from A's specs with a test that every address is a routine of the decompile, and the captures still in use as a
  waiver register waiting for the owner.
- **Re-cite an OS layer copied from the worked example.** The SAM OS is the same on every game but its addresses
  are not: Transformers copied Tron's OS layer with Tron's addresses, and most of them land inside unrelated tf_180
  functions. Check every OS citation against the new decompile's function heads (find the function each address
  falls in) when the layer is copied, not at the end.
- **A multiball's rules outlive its flag.** On Transformers every multiball's shot gate is "flag set or end task
  running" (156 + 62 ticks after the drop to one ball), so jackpots still score after the drain; the add-a-ball
  award is offered only in the first part of that window. Read the gate routine the shot handler calls, not the
  flag the spec names.
- **Look for the OS's per-player play time.** WPC keeps each player's seconds of play (T2: record word +34 at
  38:4c7b, +2 per 122 ticks from the ball's first switch until 915 ticks after the last one, fix:d1a1). Rules
  read it: the ball save length (5 / 3 / 2 units) and the consolation extra ball (30 s or less) on T2. A rule
  that "depends on the number of players" in the traces may be this.
- **Settle times come from the traces when the code reading disagrees.** T2 tilt: the code read 14 ticks, but a
  second closure 2.15 s after a warning was ignored and 3.76 s counted; the traces win, the gap goes to A.
- **Graphic glyph sets are font records of height 0.** WPC's font table also holds picture sets (T2: 8 records,
  letters N, O and `\` to `a`). Each glyph carries its own frame: `00, dy, dx, height, width`, then the rows as in
  the letter fonts (least significant bit leftmost), drawn with the left edge at x + dx and the bottom row at
  y + dy (fix:d57f on T2). Rows can be wider than 64 px: keep them as bytes, not as one integer (an int64
  overflowed in Godot). With them, an animated screen such as the match can be drawn live from its draw routine,
  pixel-exact against the capture, instead of replaying frames that show the captured values.
- **The coin and launch buttons may be on the gun.** On T2 the grip trigger (34) launches the ball from the
  shooter lane with coil 9 (31:5d0a); there is no manual plunger. A launch by the player counts as a plunge (ball
  save, plunge sound); a coil 9 launch by the ROM (multiball, ball search) does not.
- **Map a PinSound pack to ROM sound commands by name, from an altsound template.** An altsound pack's
  `altsound.csv` lists each sound board command (ID `0x00xx`, `0x7Axx` for the second page) with the PinSound
  name of its sound (NAME) and a group (1 music, 2 sfx, 3 voice, 4 jingle, 5 single = the PinSound sub-folders).
  PinSound folders are `<number>-<name>`: join on the name inside the group's sub-folder (the "sorter" method of
  necro-nemesis/Altsound-converter). Where several folders share a name, pick the one closest in audio to the
  altsound's own file. On T2 this mapped all 195 commands and agreed with every audio fingerprint and 23 of 24
  speech alignments, while half of the guesses from game context were wrong (music numbers above all). Prefer it
  to context. An altsound pack can also be played directly: its csv is the map.
- **Match a replacement sound pack's speech without speech recognition.** When no ASR model is reachable, align
  each ROM speech sample with each of the pack's voice lines (MFCC, 19 coefficients normalised per sample, DTW
  with cosine distance, the mean cost along the path) and keep a match only when the best line is clearly ahead
  (T2: cost at most 0.62 and 0.04 ahead of the next line: 24 of 82 speech calls, every one plausible against the
  code; known lines checked first). Two ROM calls on one line: keep the better match, the other falls back to
  the code's context.
- **The PuP Pack's lamp and solenoid terms are direct on WPC**: PinMAME's `L<n>` is the lamp matrix number 11-88
  and `S<n>` the solenoid, so the game posts `<game>_lamp_<n>` when a rule lights a lamp (not on the ball start
  redraw) and `<game>_coil_<n>` on a pulse ([pup_pack.md](pup_pack.md)).

## 6. A board other than SAM (from Lord of the Rings, Stern Whitestar 6809, 2026-11-21)

What changed when C ran on a 6809 Whitestar game (Lord-of-the-rings-Decryption, `game/`), with no SAM OS to copy.
Each line has the LOTR value as the example.

- **Two switch numberings meet**: the emulator and the VPX table number switches by the 0-based position in the
  ROM's name table (`Controller.Switch(28)` = BALROG HIT), A's scenarios by matrix number 10*column+row (45). Number
  MPF switches as the VPX does and convert A's scenario numbers in the runner; write the rule once
  (`lotr/hw.py`). Before believing a "the names are shifted" note, check the conversion (on LOTR the names were right).
- **Rules come from the code, never from the traces.** Every rule C builds cites the ROM routine (bank:address) that
  A decoded; a trace or a rulesheet only confirms it or gives a timing. If A has not decoded a feature yet, ask A for
  it (one batched request) instead of rebuilding it from traces; a stopgap built from traces is labelled
  provisional in the code and in `docs/rom_differences.md`, and replaced as soon as A delivers. When A's decompile
  lands, audit every feature: list each rule still marked observed / inferred and get its routine. Before delivery,
  decode the whole switch handler table and check that every switch and lamp rule is used (coverage test). On LOTR,
  C built from traces first: the ORC lanes, the skill shot and the mystery weights were missed or guessed, and the
  owner found them.
- **Comparing with A's traces** (a check, not the source). Compare **per mark
  window** (score total, DMD objects in order of first appearance, coils), not event by event: the ROM credits awards
  up to 0.5-6 s after the switch and logs the switch up to 30 ms after scoring it, so open each window 0.1 s early
  (`game/scripts/trace_check.py`). Replay A's scenario files with A's own time base (start at 30 s, commands from
  40 s, hits 1 s apart) so both traces share the clock; prefer the latest `_runN` of a scenario.
- **The display is objects with parameters, not deffs**: the game CPU sends `9B <id> <params>` and the DMD CPU draws.
  A mode's running display is re-sent by the game: every 0.115 s while its value counts down, once after each
  foreground object when static, and a foreground object holds the display ~2.35 s (observed on LOTR). Model it as
  background providers ranked by priority, re-sent when the display is free (`LotrOS._bg_tick`).
- **Read awards off the first switch of every trace.** A one-off award on the first switch of a ball showed in every
  trace (LOTR: +100,000 when it is a scoop) and explained most single-window score gaps once removed from the shot values.
- **Let the rules kick the scoops**: `auto_fire_on_unexpected_ball: false` on VUKs, saucers and locks, and the OS
  layer ejects them after the ROM's hold time (from the coil time in the trace), so intros can hold the ball.
- **Ball search timing feeds the mode timers**: measure "last switch -> search display" in every trace (LOTR 20-26 s,
  not the 8 s first guessed) and let a held ball postpone it.
- **Media before fonts**: A's per-object GIF captures (frames with their timing) give a playable DMD at once; the live
  values wait for the fonts and the x/y of each text, logged as a departure until then.
- **Read each mode's shots from the per-shot hook chains, not the rule sheet.** Every shot handler calls a fixed
  list of far hooks, one per feature; the hooks that fall in a mode's handler range (from the mode table) are the
  shots that mode uses, and a mode with one hook has one shot (LOTR: War of the Ents has only an eject hook, the
  rule sheet's orbit values do not exist in 5.0 code; map in the game's `docs/rules/README.md`). Find the chains by
  searching the ROM for far calls (`jsr far; addr; bank`) to the mode's addresses.
- **Effect ids carry the DMD object.** Mode code rarely sends DMD or sound commands itself: it queues an effect id
  whose table entry starts with the DMD object (LOTR: 61:75FE, 5 bytes: object, priority, flags, script). Reading the
  first byte gives every mode display at once; the sounds then come from the traces by DMD object. A value passed
  to that queue is not a sound command: check it against the traces before playing it.
- Godot imports every CSV it finds as a translation, in MPF folders too (`monitor/`): `.gdignore` in every non-Godot
  folder of the machine folder.

## 7. Status and open work per game

On each game's page (Tron: [Tron-Legacy-MPF `docs/agents/README.md`](https://github.com/Ashram56/Tron-Legacy-MPF/blob/main/docs/agents/README.md), "C, strict recreation"; Transformers: [Transformers-MPF](https://github.com/Ashram56/Transformers-MPF) `README.md`).

Last updated 2026-11-25 (section 5b: a QA pass for a game built before the strict rule, re-citing a copied OS layer, multiball end windows, from Transformers); earlier 2026-11-23 (sections 4b and 5a: the rules test benches of Tron and Transformers; section 5b: the WPC sound_call priority test, a decompile review once the traces pass, the per-player play time, from Terminator 2; section 6: a Whitestar 6809 game, Lord of the Rings; mode shots from hook chains, effect ids; before: section 5b, the first WPC 6809 game, Terminator 2; section 5, what porting Transformers Pro 1.80 showed).
