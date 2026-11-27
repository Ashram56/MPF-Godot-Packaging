# MPF itself: behaviour and quirks (game agnostic)

What every Stern SAM recreation meets in Mission Pinball Framework, independent of the game and of the platform it runs
on. Godot, GoZen, GMC, boards and installers are in this repository
(`fixes/`, `platforms/`). Add MPF findings here, one section each, with the version, a fact tag
(code / observed / inferred) and the game's value as the example.

## `virtual_pinball` answers unlike VPinMAME (MPF 0.80.1)

| | |
|---|---|
| Component | MPF `mpf/platforms/virtual_pinball/virtual_pinball.py` |
| Affected | MPF 0.80.1, and later until fixed upstream |
| Found on | Transformers MPF, table "Transformers Pro (Stern 2011) v.2.4", 2026-10-09; first seen on Tron Legacy MPF |
| Fact | code (`virtual_pinball.py`), observed in the games' tests and `vpx_bridge.py --check` |
| Our fix | none in MPF: the game's custom code patches the platform (Transformers-MPF `game/tf/vpx_hardware.py`, the generic version; Tron-Legacy-MPF `game/tron/vpx_hardware.py`), from `custom_code:` in the VPX overlay |
| Upstream | https://github.com/missionpinball/mpf/issues; status: **draft, not filed** (text below) |

**Problem.** A VPX table written for PinMAME (its script loads VPinMAME's `core.vbs` and the machine helper, `sam.vbs`
for Stern SAM) talks to MPF through a COM bridge that forwards each controller call as a `vpcom_bridge` BCP command
(the protocol of the `virtual_pinball` platform and [mpf-vpcom-bridge](https://github.com/missionpinball/mpf-vpcom-bridge)).
With the platform as it is:

- the table's script stops with an error the first time it sets a switch MPF has no device for (sam.vbs sends the
  upper flipper buttons, 86 and 88, on every game);
- slingshot kicks, trough ejects and other short pulses are often never seen by the table;
- every lamp of a table that sets `UseVPMModSol = 2` stays dark, and so does its GI;
- flippers, slings and pop bumpers driven by MPF hardware rules never fire their coils.

**Cause.** MPF's platform answers differently from VPinMAME, which the tables were written against.

- `vpx_set_switch`, `vpx_get_switch`, `vpx_pulsesw` index `self._switches[str(number)]`: an unknown number raises
  `KeyError`, which comes back to the table as a COM error and stops its script.
- `vpx_changed_solenoids` compares `driver.state` now with the last poll. A pulse that starts and ends between two polls
  (the table polls once a frame, MPF's pulses are 10 to 40 ms) is never reported. Values are `True`/`False`.
- `vpx_changed_lamps` returns `bool(brightness > 0.5)`. With `UseVPMModSol = 2` (physical outputs, common in recent VPW
  tables) core.vbs sets `Controller.SolMask(2) = 2` and divides lamps, solenoids and GI by 255, so a lamp at `True` (1)
  reads 1/255.
- `vpx_changed_gi_strings` reports lights of subtype `gi`; a machine whose GI is not an MPF light (Stern SAM: a relay the
  ROM never switches) reports nothing, and a table whose GI follows `GiCallBack2` stays dark.
- The rule methods (`set_pulse_on_hit_rule` and the others) only store the rule in `self.rules`; `vpx_get_hardwarerules`
  hands them to a client that emulates them. A VPinMAME table never asks, so a rule's coil never fires. Tables that use
  VPinMAME's fast flips (`cvpmFFlipsSAM`) move the flippers themselves once solenoid 33 ("flippers enabled") is on, which
  the platform has no notion of.

**Fix** (the game patches the platform's methods from its custom code; the platform classes have `__slots__`, so the
methods are replaced on the classes and fall back to MPF's code for any other platform):

- unknown switch numbers are ignored (logged once) and read as open;
- every pulse is remembered until the next `vpx_changed_solenoids`, so it is reported at least once; values are 0 or 255;
- lamps are reported 0 to 255 (`current_brightness * 255`); the bridge converts to 0/1 when the table has not set
  `SolMask(2) = 2`;
- a constant GI string (`[[0, 255]]` once) for a machine without a GI output;
- the switch handler applies the rules itself, as the machine's CPU would: a hold rule's coil follows its switch, a pulse
  rule's coil pulses; solenoid 33 reads on while any flipper rule exists.

**How to check.** Transformers-MPF `tests/test_vpx.py` drives the platform's `vpx_*` methods the way the `vpcom_bridge`
handler does: set switch 86 (no error), start a game and see the trough kicker reported once though its pulse is over,
lamps at 255 and 128, GI `[[0, 255]]`, the left flipper coil following its button, the sling coil on its switch. Without
the patches the same calls raise `KeyError`, miss the pulse and report `True`. Headless, MPF waits at reset until every
display BCP client answers `reset` with `reset_complete` (`machine_reset_phase_1`), so a live check without Godot needs a
stand-in GMC that does. The bridge side is [agents/vpx_bridge.md](../agents/vpx_bridge.md), section 4a.

**Upstream issue (draft, not filed).** Title: *virtual_pinball: answer like VPinMAME (unknown switches, short pulses, lamp
brightness, hardware rules)*.

```markdown
**Environment**
- MPF 0.80.1, `hardware: platform: virtual_pinball`, a VPX table written for VPinMAME (Stern SAM, core.vbs and
  sam.vbs), driven through vpcom_bridge BCP commands.

**What happened**
1. The table's script stops at the first `Controller.Switch(n) = v` for a switch MPF has no device for
   (`KeyError` in `vpx_set_switch`).
2. Short pulses (slings, trough eject) are often not reported by `vpx_changed_solenoids`: the pulse starts and
   ends between two polls.
3. With `UseVPMModSol = 2` every lamp is dark: `vpx_changed_lamps` returns booleans, core.vbs divides by 255.
4. Coils of hardware rules (flippers, autofire) never fire unless the client emulates `vpx_get_hardwarerules`,
   which VPinMAME tables do not.

**Expected**
VPinMAME's answers: unknown switches ignored, every pulse reported at least once, lamp and solenoid levels 0-255
when the table asks for physical outputs, the rules applied by the platform when their switch changes.

**Proposed change**
- `vpx_set_switch` / `vpx_get_switch` / `vpx_pulsesw`: ignore and log unknown numbers.
- Keep a set of drivers pulsed since the last `vpx_changed_solenoids` and report them on.
- A `vpx_changed_lamps` mode (or a new command) returning `int(brightness * 255)`.
- Apply `self.rules` in `vpx_set_switch` (hold: follow the switch; pulse: pulse the driver).
A working implementation as custom code: Transformers-MPF `game/tf/vpx_hardware.py`.
```

## Holding the game over sequence of the ROM

A ROM runs a long sequence after the last ball (bonus, high score entry, match, awards, GAME OVER) before attract
returns. Register a handler on `game_ending` (and on `ball_ending` for the bonus) with the queue argument, call
`queue.wait()` and step the sequence with delays; call `queue.clear()` at its end. MPF keeps the game object (and
the players' scores) until then, and attract starts only after the clear. A coroutine-style generator that yields
tick counts (`next()` from a `delay.reset` callback) reproduces a ROM task's sleeps one to one. Switch handlers
(flippers, START) read the entry while the queue waits. LOTR: `game/lotr/game_over.py` and `os_layer._bonus_script`
(private repository).

Last updated 2026-11-24 (holding the game over sequence in the game_ending queue); earlier 2026-10-29 (moved here from MPF-Godot-Packaging `fixes/mpf/virtual-pinball-vpinmame-answers.md`, PR #17; routing: MPF knowledge here, platform and packaging there).
