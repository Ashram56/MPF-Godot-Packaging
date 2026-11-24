# Agent D: VPX to MPF bridge (work in progress)

> **Feed back what you learn.** Whatever game you run this agent on, report every game-agnostic learning to
> Ashram56/MPF-Godot-Packaging (this repository) in the same session, without being asked: a pull request if you
> have write access, otherwise a GitHub issue opened directly. How and what: [CONTRIBUTING.md](../CONTRIBUTING.md).
> **Route it:** MPF implementation learnings (rules, display, sound, VPX bridge, PuP, install kit, Godot, GoZen,
> GMC, MPF, platforms and boards) stay here. Taking a ROM or a VPX table apart (formats, decompile, traces, IO
> tables) goes to [Ashram56/Stern-SAM-Decryption](https://github.com/Ashram56/Stern-SAM-Decryption) instead (its
> CONTRIBUTING.md), with at most a pointer here.

Make a Visual Pinball X table play with the MPF game instead of PinMAME and the ROM: VPX keeps the ball, the
physics and the mechanical sounds; MPF runs the rules; Godot draws the DMD and plays the ROM's speech and
music. Part of the [master plan](README.md) (A to G in full: [Stern-SAM-Decryption `agents/README.md`](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/agents/README.md)). The player-facing set-up is the game repo's `docs/vpx.md` (Tron:
[vpx.md](https://github.com/Ashram56/Tron-Legacy-MPF/blob/main/docs/vpx.md)); this page is what an agent needs to continue the work, or to start it on another game.
File paths in `code` are the Tron game repo's ([Tron-Legacy-MPF](https://github.com/Ashram56/Tron-Legacy-MPF)) unless said otherwise.
The second game, Transformers Pro 1.80 (`tf_180`, the "Transformers Pro (Stern 2011) v.2.4" VR-Hybrid table), is
the one to copy from for a new game: its bridge files are generic, with every game value in a constants block
([Transformers-MPF](https://github.com/Ashram56/Transformers-MPF), branch `claude/vpx-bridge-d47e04`; section 4). Labels: **verified** (run), **unverified**, **owner test**
(only possible on the owner's Windows PC).

## 1. The pieces (Tron, as built)

| Piece | State |
|---|---|
| Overlay `game/config/hw_vpx.yaml` (LE), `hw_vpx_pro.yaml` (Pro) | built, unit-tested (`tests/test_vpx.py`) |
| MPF side `game/tron/vpx_hardware.py` | built, unit-tested |
| COM bridge `scripts/vpx_bridge.py` (`TronMPF.Controller`) | built; `--check` (its client without COM) verified on Linux against the real game |
| Script override `scripts/vpx_table.py` | verified on the VPW v1.1 table: one loader line changed, one KeyDown line added, the rest byte for byte |
| `run.py --hw vpx`, `setup.py --vpx` | built; the one-line Windows set-up (`-Vpx -Table`) is the [packaging agent](packaging.md)'s, built on Transformers, not yet on Tron |

## 2. Architecture

```
VPX table script --COM--> TronMPF.Controller --BCP 5051--> MPF (hw_vpx, virtual_pinball) --BCP 5050--> Godot
 (core.vbs, sam.vbs)       scripts/vpx_bridge.py            game/tron/vpx_hardware.py
```

- **Never modify the `.vpx`**: VPX refuses a table whose script changed without its MAC being recomputed.
  VPX 10.7+ loads `<table name>.vbs` next to the `.vpx` instead of the embedded script; delete or rename it
  to go back to PinMAME. (verified for the format; the load itself is owner test)
- The only script change: `LoadVPM ... "sam.VBS"` becomes `LoadMPF "sam.VBS"`, which loads the same
  VPinMAME helper scripts (core.vbs, sam.vbs: keys, timers, ball stacks, fast flips) and creates
  `TronMPF.Controller` instead of `VPinMAME.Controller`. Plus one KeyDown line: `End` toggles the coin door.
- **Own bridge, not mpf-vpcom-bridge**: missionpinball/mpf-vpcom-bridge is not on PyPI and breaks on the
  table's `.Run GetPlayerHWnd`. `vpx_bridge.py` speaks the same `vpcom_bridge` BCP commands MPF's
  `virtual_pinball` platform answers, plus what this table needs: `Run(hwnd)`, starting MPF when nothing
  listens (`run.py --hw vpx` in a new console), accepting unknown properties (`Hidden`, `SolMask`,
  `Games().Settings`), returning Empty for "nothing changed" as VPinMAME does, `Stop` quitting a game it started.
- Start order: Godot first (MPF waits for GMC on 5050), then MPF (waits for the table), then the table. If
  the table starts first, the bridge launches `run.py --hw vpx` and VPX looks frozen meanwhile.

## 3. Numbering: what PinMAME's SAM driver and sam.vbs use

Matrix switches 1-64, coils 1-32 and lamps 1-80 are the ROM's own numbers, so every device keeps its MPF
name. The differences are all in the overlay and the adapter:

| Table side (PinMAME) | MPF | Notes |
|---|---|---|
| switches 84 / 82 (`swLLFlip` / `swLRFlip`) | flipper buttons (SAM dedicated 9 / 11) | the upper left flipper follows the left button |
| -7 `swTilt`, -6 `swSlamTilt`, 65 `swCoin1` | plumb bob tilt, slam tilt, coin | coins 2-3 (66, 67) ignored |
| -3, -2, -1, 0 | service BACK, MINUS, PLUS, SELECT | |
| -4 | coin door open | sam.vbs has none; the `End` key line added by vpx_table.py |
| 41 (Tron disc opto) | not inverted | the table closes it while the ball is on the disc |
| solenoids 1-32 | coils/flashers of the same number | reported 0 or 255 (`UseVPMModSol`); a pulse is reported at least once even if it ends between two polls |
| lamps 1-80 | lights of the same number | 0-255 (MPF's brightness) when the table sets `UseVPMModSol = 2`, else 0/1 (section 4a) |
| coins 65-69 | coin slots 1-5 | Transformers maps all five; sam.vbs has keys for 65-67 only |
| solenoid 33 | "flippers enabled" | input of sam.vbs fast flips (`cvpmFFlipsSAM`, `SolCallback(33)`); on while any MPF flipper rule is on; the ticket outputs moved to aux numbers out of its way |
| solenoids 15, 16, 12 | flipper coils | follow their button while the rule is on, as the SAM CPU does |
| lamps 101-103 / 104-106 | Tron ramp tubes (blue, green, red) | PinMAME's SAM_GAME_TRON numbering of strobe 0x10 / 0x20, reported 0-255 for `RGB()`; 0 on a Pro unless fiber optics are enabled |
| GI | none | MPF does not drive the GI relay; Tron's table turns its GI on by itself. A table whose GI follows `GiCallBack2` (Transformers' `GI_PWM`) stays dark unless `ChangedGIStrings` reports a string: report string 0 = 255 once (section 4a) |

Coin door open: every solenoid but 24 reads 0 and solenoid 33 is off, as the ROM masks its outputs while the
interlock is open (IO interrupt 0x12070 writes shadow & mask 0x3b984 while RAM 0x3727c & 3 != 3).

The ball devices count the table's own trough (18-21), shooter lane (23) and VUK (11); MPF's ejects
(solenoids 1, 2, 4) fire the table's kickers; the table's `bsTrough` starts with 4 balls.

## 4. Doing this for another table

1. Run the [VPX extraction agent](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/agents/vpx_extraction.md) first: `script.vbs` and the numbered CSVs are the input.
2. Read the script: which controller calls it makes (`Switch`, `Solenoid`/`ChangedSolenoids`,
   `ChangedLamps`, `ChangedGIStrings`, `Lamp`, `Run`, properties), which helper script it loads (sam.vbs,
   wpc.vbs ...), whether it uses modulated solenoids, fast flips, ball stacks or `cvpmTrough`.
3. Map every switch, coil, flasher, lamp and GI string to the MPF config's numbers and names; renumber only
   what PinMAME numbers differently (dedicated switches, extra outputs above the ROM's range).
4. Copy Transformers' files, not Tron's: `scripts/vpx_bridge.py` (constants `GAME`, `PROGID`, a new `CLSID`
   from `uuid4()` so both bridges can stay registered, `ENV` for the environment variable prefix, `ROM_NAME`),
   `game/tf/vpx_hardware.py` (constants `FLIPPER_COILS`, `FLIPPERS_ON_SOLENOID`, `MAX_SOLENOID`,
   `POWERED_WITH_DOOR_OPEN`, `GI_STRINGS`), `scripts/vpx_table.py` (`REPO`, `MARKER`), `game/config/hw_vpx.yaml`
   and `tests/test_vpx.py` + `tests/machine_vpx.yaml`. Then change only the constants and the overlay's numbers.
   On Transformers that took the whole bridge with no other code change (verified: 36 tests, `--check` live).
5. Check the MPF config repo is reachable before mapping (a stale local copy maps wrong numbers).
6. Hand the set-up steps (bridge packages, COM registration, the table's `.vbs`) to the
   [packaging agent](packaging.md), which puts them in the Windows installer's `-Vpx` option.

## 4a. What bit on Transformers (true of any SAM table)

Why the adapter (`vpx_hardware.py`) exists at all, MPF 0.80.1's `virtual_pinball` answering unlike VPinMAME, is
documented, with a draft upstream issue, in [`knowledge/mpf.md`](../knowledge/mpf.md), "`virtual_pinball` answers unlike VPinMAME".

- **`UseVPMModSol = 2`** (physical outputs, common in recent VPW and VR tables): core.vbs then sets
  `Controller.SolMask(2) = 2` and divides solenoids, lamps **and** GI by 255. The bridge must report lamps 0-255
  and GI 0-255 in that mode, and 0/1 lamps and 0-8 GI otherwise; it keeps the `SolMask(2)` the table wrote and
  converts (Transformers `vpx_bridge.py` `physical()`). A bridge that always sends 0/1 lamps leaves them at
  1/255: dark. (code: core.vbs, VPX tag v10.8.1; verified in `tests/test_vpx.py`)
- **GI**: grep the script for `GiCallBack`/`GiCallBack2`. If it has one, the adapter reports a GI string (MPF has
  no GI output on SAM). (code: Transformers v2.4 `GI_PWM`)
- **Animation-only solenoid callbacks**: Transformers' `solLSling` / `solRSling` and the bumper callbacks only move
  the arms and play the sounds; the table's own objects kick the ball. MPF fires nothing on a sling unless told,
  so the overlay adds `autofire_coils` for slings and pops, disabled at ball end, tilt and in the service menu,
  and the adapter pulses an autofire rule's coil when its switch closes. Tron had none of this. (code: v2.4 script)
- **DMD**: with `UseVPMDMD` the table reads `RawDmdPixels` every frame; return Empty (None), with
  `RawDmdWidth` 128 / `RawDmdHeight` 32, and the table's DMD stays empty without errors; Godot's window is the DMD.
- **Trough jam**: `SolTrough` pulses the jam switch (22) on every eject; MPF's trough takes it in its stride
  (verified in a test that pulses it).
- **Scoops and VUKs as `cvpmBallStack`** (Tron `bsRHole`, `InitSw 0, 11, ...`): the stack holds any number of
  balls behind its one switch, so a second ball entering while one is held gives no switch edge. The ROM
  rules never see that scoop entry (no scoop award), and MPF's one-switch device counts 1. When MPF ejects, the
  switch stays on, MPF retries the eject, and the second ball comes out. `game.balls_in_play` stays right
  (drains are counted in the trough), but the second ball's scoop shot is lost. A real scoop rejects the
  second ball. (code: Tron VPW Mod v1.1 table script; reproduced in Tron `tests/test_ball_tracking.py`)
  A stack in **saucer mode** does not have the problem: `InitSaucer` (Transformers v2.4 `bsSaucer.InitSaucer sw3, 3, ...`)
  disables its kicker in `AddBall` while it holds the ball, so a second ball rolls over it as on a real saucer.
  Grep the script for `InitSw 0, <one switch>` to find the stacks that do. (code: core.vbs `cvpmBallStack.AddBall`)
- **Stuck balls**: VPX strands balls where a real machine would not. After the ROM's lost ball recovery
  (PINBALL MISSING) serves a replacement, a stuck ball that comes free ends the ball early. That is the ROM's
  behaviour ([playbook](../knowledge/sam_to_mpf_playbook.md), "SAM ball counting"), so ask the owner about it
  before adding a departure.
- **Coin door key**: VPinMAME's `keyCoinDoor` is End (DIK 207); `keyFront` is key 2 (tournament start on SAM).
  vpx_table.py's KeyDown line uses 207 and runs before `vpmKeyDown`.
- **pywin32 property put**: `Controller.Switch(n) = v` calls `SetSwitch(n, v)`; every indexed property the table
  writes (`Switch`, `SolMask`, `Dip`, `Mech`) needs a `Set<Name>(args, value)` method.
- **VPX's core scripts** (core.vbs, sam.vbs, controller.vbs) to read in the cloud: fetch them from a vpinball
  release tag (`github.com/vpinball/vpinball/raw/v10.8.1-5436-af26b2d93/scripts/core.vbs`); `master/scripts/`
  answers 404.

### Testing in the cloud (no Windows)

- `vpx_bridge.py --check` is the bridge's client without COM: it starts `run.py --hw vpx`, loads the trough, starts
  a game and reads back the outputs. Headless, MPF waits forever at reset unless a GMC answers: MPF's
  `machine_reset_phase_1` waits for `reset_complete` from every display BCP client. Run Godot (`run.py` does,
  under Xvfb), or a 20-line fake GMC on 5050 that answers `hello` with `hello` and `reset` with
  `reset_complete`. (verified on Transformers)
- Stop the game by PID: `pkill -f "mpf game"` matches the shell running it too and kills the session's command.
- Unit tests: drive the platform's `vpx_*` methods the way the `vpcom_bridge` BCP handler does, and poll
  `changed_solenoids` between steps as the table does every frame, or a pulse that ended is counted twice.

## 4b. A WPC table (Terminator 2, g5k 1.25, `t2_l8`)

Built 2026-11-21 in Ashram56/Terminator-2-Decryption (private; `game/t2/vpx_hardware.py`, `scripts/vpx_bridge.py`,
`docs/vpx.md`), from Transformers' files. What changes for a Williams WPC 6809 table (code: wpc.vbs and core.vbs
v10.8.1, PinMAME `src/wpc/mech.c`, `sims/wpc/full/t2.c`; verified in 11 unit tests and `--check` over BCP; VPX itself
is owner test):

- **Keep the game's IO numbers, translate in the adapter.** A game whose `io.yaml` numbers devices `S11`, `SD1`, `C01`,
  `L11` (read by its rules code) needs no overlay renumbering: the adapter maps PinMAME's numbers (matrix 11-88 =
  `S<n>`, coin door 1-8 = `SD<n>`, solenoid n = `C<nn>`, lamp n = `L<n>`).
- **Flippers without Fliptronics** (pre-1992 WPC: T2, Gilligan's Island, Party Zone): wpc.vbs sends `swLLFlip` 114 /
  `swLRFlip` 112; PinMAME maps them to the game's matrix flipper switches (`FLIP_SWNO(12,11)` in the sim file). The
  fast-flip input is `GameOnSolenoid = 31` (the flipper relay), and PinMAME reports the flipper coils as `sLLFlipper`
  48 / `sLRFlipper` 46. Fliptronics games use the same 112-118 keys but ROM-driven flipper solenoids (wpc.vbs notes).
- **Coin door**: matrix switch 22, toggled by wpc.vbs's `keyCoinDoor` itself; no KeyDown line in the table script
  (SAM's -4 needs one). The table sets 22 and 24 (always closed) in `Table1_Init`.
- **`cvpmMech` is the controller's job.** A table with `HandleMechanics = 0` and a `cvpmMech` (T2's gun: Sol1 11,
  Length 240, Steps 240, Reverse + NonLinear, switches 33 home / 32 mark) writes `Controller.Mech(1..7, 10..)`, then
  `Mech(0) = n`, and reads `GetMech(n)` / `GetMech(-n)` every frame; PinMAME moves it and closes its switches. MPF
  0.80.1's `vpx_set_mech` / `vpx_get_mech` only log a warning, so the gun never moves and its switches never close.
  Port `mech.c`'s `mech_update` (60 Hz, MECH_STEP 60, ~60 lines) into the adapter and forward `SetMech`/`GetMech`
  from the COM bridge. Grep the script for `cvpmMech` and `HandleMechanics`.
- **GI**: WPC tables call `GICallback2` with strings 0-4; report all five at 255 when the game has no GI output.
- `LoadVPM` names `WPC.VBS`: `vpx_table.py`'s loader regex takes any `<name>.vbs`.

## 5. Open items per game

On each game's page (Tron: [Tron-Legacy-MPF `docs/agents/README.md`](https://github.com/Ashram56/Tron-Legacy-MPF/blob/main/docs/agents/README.md), "D, VPX bridge"),
starting with the owner's Windows test.

Keep this file current with every generic fix; owner test results go on the game page. Last updated 2026-10-10
(moved to Stern-SAM-Decryption; Tron status and open items to the Tron game page; Transformers: generic bridge,
physical outputs, GI, autofire, cloud testing; Tron: scoop ball stacks, stuck balls; 2026-10-28: saucer mode, pointer to the MPF fix doc; 2026-11-21: section 4b, WPC tables and cvpmMech).
