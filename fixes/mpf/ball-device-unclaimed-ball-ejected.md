# A lock or scoop sends its ball straight back out before the rules can hold it

| | |
|---|---|
| Id | `mpf/ball-device-unclaimed-ball-ejected` (this file: `fixes/mpf/ball-device-unclaimed-ball-ejected.md`) |
| Component | MPF (documentation; works as designed) |
| Kind | improvement |
| Affected versions | MPF 0.80.1; and later until documented upstream |
| Platforms | all |
| Found on | a Williams WPC recreation (Terminator 2), 2026-11-21 |
| Fact | observed (the gun's ball left at once), cause from MPF 0.80.1 code |
| Our fix | none in this repository: the game's rules claim the ball (below) |
| Applied by | the game's code; nothing to apply |
| Upstream | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, not filed** |

## Problem

A ball device whose ball the game's own code (custom code, not `ball_holds` or `ball_locks`) keeps for a while,
a scoop or a gun that holds the ball for seconds, ejects the ball as soon as it is counted. The rule's own timer
then finds the device empty.

## Cause

`BallDevice._post_enter_event()` (`mpf/devices/ball_device/ball_device.py`) posts the relay event
`balldevice_<name>_ball_enter` with `unclaimed_balls`; `_balls_added_callback()` ejects every ball still unclaimed
after the relay ("Ejecting %s unexpected balls"). Ball holds and locks claim their balls through that relay; code
that only listens to `balldevice_<name>_ball_entered` (a plain event) claims nothing.

## Fix

The game's code registers a relay handler and returns the balls it keeps:

```python
self.machine.events.add_handler('balldevice_bd_gun_ball_enter', self._entered, priority=1)

def _entered(self, unclaimed_balls, **kwargs):
    # the rule decides; it ejects later with device.eject()
    return {'unclaimed_balls': 0}
```

With `entrance_count_delay: 200ms` on the device, the rule reacts at the time the ROM does (the default 500 ms
made every device rule half a second late against the reference traces).

## How to check

Enter a ball into the device on the virtual platform: without the handler the log shows "Ejecting 1 unexpected
balls" at once; with it, the ball stays until the rule ejects it.

## Upstream issue (draft, not filed)

**Title:** Document that custom code must claim balls via the `balldevice_<name>_ball_enter` relay

**Body:**

```markdown
MPF 0.80.1. A ball device whose balls are kept by custom code (not ball_holds / ball_locks) ejects each ball at
once: BallDevice._balls_added_callback() ejects unclaimed balls after the relay event balldevice_<name>_ball_enter.
Custom code that listens to balldevice_<name>_ball_entered does not claim them. Expected: the docs of ball devices
and of custom code say how to claim a ball (a relay handler returning {'unclaimed_balls': 0}).
```
