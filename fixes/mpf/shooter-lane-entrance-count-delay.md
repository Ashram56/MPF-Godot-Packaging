# A ball plunged at once is never counted, and its drain is ignored for 10 seconds

| | |
|---|---|
| Id | `mpf/shooter-lane-entrance-count-delay` (this file: `fixes/mpf/shooter-lane-entrance-count-delay.md`) |
| Component | MPF (ball devices; works as designed, the default does not suit a plunger lane) |
| Kind | improvement |
| Affected versions | MPF 0.80.1; and later while the default is 500 ms |
| Platforms | all |
| Found on | a Stern SAM recreation, 2026-11-15, by a test bench with a physical table model |
| Fact | observed (bench on the `virtual` platform), cause from MPF 0.80.1 code |
| Our fix | none in this repository: the game's machine config sets `entrance_count_delay` on its shooter lane (below) |
| Applied by | the game's config; nothing to apply |
| Upstream | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, not filed** |

## Problem

The shooter lane is a ball device with one ball switch and a manual plunger (`mechanical_eject: true`). A player who
plunges as soon as the ball arrives (under 0.5 s after the lane switch closes) gets a ball MPF does not know:
`playfield.balls` stays 0, the lane stays `waiting_for_ball` and the trough `ball_left`. If that ball drains in the next
10 seconds, nothing happens (no ball save, no end of ball); at the trough's eject timeout MPF reports `failed_confirm`
and serves a ball to the lane again. A ball that stays in play longer than 10 s is picked up as an unexpected
playfield ball.

## Cause

`ball_devices: entrance_count_delay` defaults to 500 ms: a ball switch must stay active that long before the device
counts the ball (`mpf/devices/ball_device/switch_counter.py`). The lane switch opened before that, so the device never
had a ball, the trough's eject to it was never confirmed, and the game's ball stayed in transit until the trough's
`eject_timeouts` (10 s default).

## Fix

In the game's machine config, count the shooter lane's ball quickly. The original game's own code is the guide: the
Stern SAM OS takes a ball as "in the lane" after 6 ticks (98 ms).

```yaml
ball_devices:
  bd_shooter_lane:
    ball_switches: s_shooter_lane
    entrance_count_delay: 100ms
    mechanical_eject: true
```

Side effect to plan for: MPF fires an auto-launch (`player_controlled: false`) as soon as the lane counts its ball, so
every auto-launched ball leaves 0.4 s earlier than with the default. A game whose waits were measured against reference
recordings must add the 0.4 s to the waits that precede an auto-launched ball (ball save, multiball launches), or its
timing checks fail.

## How to check

On the `virtual` platform (not `smart_virtual`, which moves the balls itself): close the trough switches, start a game,
close the lane switch when the trough coil pulses, open it 150 ms later, then close a trough switch (the drain) 3 s
later. Without the fix `playfield.balls` is 0 after the plunge and the drain posts no `ball_drain` for the game; with it
`playfield.balls` is 1 and the drain is handled at once.

## Upstream issue (draft, not filed)

**Title:** Plunger lane: a ball plunged within `entrance_count_delay` (500 ms default) is lost for the trough's eject timeout

**Body:**

```markdown
MPF 0.80.1. Machine: trough (4 ball switches, eject to the plunger lane), plunger lane ball device with one ball
switch, `mechanical_eject: true`, default `entrance_count_delay`.

Steps: start a game; when the ball reaches the plunger lane, plunge within 500 ms; let the ball drain within 10 s.

Expected: the ball is in play; its drain ends the ball (or is saved).

Actual: the lane never counts the ball (its switch was active for less than `entrance_count_delay`), the trough's
eject stays unconfirmed (`ball_left`), `playfield.balls` is 0 and the drain is not handled. After the trough's
eject timeout (10 s) the eject is `failed_confirm` and a ball is served again.

Proposal: document a short `entrance_count_delay` (about 100 ms) for plunger lanes in the ball device docs and the
plunger examples, or treat "target's ball switch went active then inactive" as a confirmed eject for a device with
`mechanical_eject: true`.
```
