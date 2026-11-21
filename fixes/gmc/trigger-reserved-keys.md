# A trigger argument named `cmd` or `name` never reaches the Godot handler

| | |
|---|---|
| Id | `gmc/trigger-reserved-keys` (this file: `fixes/gmc/trigger-reserved-keys.md`) |
| Component | GMC |
| Kind | pitfall (by design) |
| Affected versions | GMC 1.0.0 |
| Platforms | all |
| Found on | Lord of the Rings (Whitestar) recreation, 2026-11-21 |
| Fact | observed (every sound command arrived as 0), cause from GMC 1.0.0 code |
| Our fix | none in GMC: name the argument something else in the game |
| Applied by | the game |
| Upstream | not filed |

## Problem

A game posts `machine.events.post('lotr_sound', cmd=250)` and a slide handles it with
`MPF.server.add_event_handler("lotr_sound", _on_sound)`: `payload.get("cmd")` is the string `"lotr_sound"`, so
`int(payload.get("cmd", 0))` is 0 and every call looks the same. No error is logged.

## Cause

`scripts/bcp_parse.gd` `parse()` decodes the trigger's arguments into the result dictionary, then sets
`result.cmd = cmd`, where `cmd` is the BCP command, which for a trigger is the event name. `name` is the event name
too (`encode_event_args` and MPF both set it). Any argument called `cmd` or `name` is overwritten.

## Fix

Use other argument names for events a Godot slide reads (`sound=250`, not `cmd=250`). A check for a game: grep the
MPF code for `events.post(` with `cmd=` or `name=` on events that GMC handlers register.
