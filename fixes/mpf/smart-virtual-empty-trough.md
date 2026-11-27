# The desktop game never starts: "Not enough balls", or the first ball stays in the shooter lane

| | |
|---|---|
| Id | `mpf/smart-virtual-empty-trough` (this file: `fixes/mpf/smart-virtual-empty-trough.md`) |
| Component | MPF |
| Kind | packaging |
| Affected versions | MPF 0.80.1 |
| Platforms | all |
| Found on | a Stern Whitestar recreation (Lord of the Rings), 2026-11-22 |
| Fact | observed |
| Our fix | the game's desktop overlay (e.g. `config/hw_virtual.yaml`) and its GMC keyboard map (`gmc.cfg`) |
| Applied by | the game's own config |
| Upstream | none: configuration, not an MPF bug |

## Problem

With `platform: smart_virtual` and no hardware, pressing start after inserting coins does nothing. The MPF log says
`BallController denies game start. Not enough balls. 0 found. 1 required`. Unit tests pass because the test case
sets the trough switches itself. Once that is fixed, a game with a manual shooter lane (`mechanical_eject: true`,
`player_controlled_eject_event`) waits for a launch that no key sends.

## Cause

smart_virtual starts with every switch open, so the trough holds no ball. A player-controlled eject waits for its
event, and the GMC keyboard map has no key for it unless the game adds one.

## Fix

In the desktop overlay, list the trough's ball switches under `virtual_platform_start_active_switches`. In
`gmc.cfg`, add a launch key (`enter=["event", "<the eject event>"]`, `space=...`).

## How to check

Run the game under Xvfb with GMC, then send the coin, start and launch keys through XTEST (python-xlib). The log
should show `ball_started` and then `playfield_ball_count_change` with `balls: 1`.
