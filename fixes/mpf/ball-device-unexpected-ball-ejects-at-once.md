# A scoop ejects its ball at once although `auto_fire_on_unexpected_ball: false`

| | |
|---|---|
| Id | `mpf/ball-device-unexpected-ball-ejects-at-once` (this file: `fixes/mpf/ball-device-unexpected-ball-ejects-at-once.md`) |
| Component | MPF |
| Kind | bug |
| Affected versions | MPF 0.80.1; and later until fixed upstream |
| Platforms | all |
| Found on | a Stern Whitestar recreation (Lord of the Rings), 2026-11-21 |
| Fact | observed (virtual and smart_virtual platforms), cause from MPF 0.80.1 code |
| Our fix | none in this repository: the game gives each scoop a `player_controlled_eject_event` and posts it to let the ball go |
| Applied by | the game's config; nothing to apply |
| Upstream | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, not filed** |

## Problem

A scoop (VUK, saucer) set to `auto_fire_on_unexpected_ball: false`, so that the game's rules decide when to kick,
fires its eject coil as soon as the ball is counted (the `entrance_count_delay`, 500 ms by default). The rules'
own kick a few seconds later finds the device empty. Nothing is logged as an error. A rule that holds the ball
(a mode start, a multiball intro) cannot hold it.

## Cause

`BallDevice._balls_added_callback()` (`mpf/devices/ball_device/ball_device.py`) sets up the eject of an
unexpected ball with `setup_eject_chain(path, not self.config['auto_fire_on_unexpected_ball'])`: with `false` the
eject is *player controlled*. `OutgoingBallsHandler._eject_ball()` (`outgoing_balls_handler.py`) waits for the
player only when the device has a `player_controlled_eject_event` (or `mechanical_eject`); otherwise it calls
`ejector.eject_one_ball()` at once. So `auto_fire_on_unexpected_ball: false` alone changes nothing for a device
with an eject coil.

## Fix

Give each scoop a `player_controlled_eject_event` and post that event when the rules release the ball:

```yaml
ball_devices:
  bd_top_saucer:
    ball_switches: s_top_saucer
    eject_coil: c_top_saucer
    auto_fire_on_unexpected_ball: false
    player_controlled_eject_event: game_kick_bd_top_saucer   # the game posts it to let the ball go
```

A tilt still ejects it (MPF waits for `tilt` too). **Not for a device that holds several balls** (a physical
lock): while the first ball's eject waits for the event, the device does not count the next ball entering
(observed: the second lock switch closed and no `ball_entered` came), so a lock needs another setup (MPF's
`ball_holds` or a device that is told to keep its balls).

## How to check

On the virtual platform: put a ball in the device (`add_ball_to_device`), advance the clock 2 s. Without the event
the eject coil has pulsed and the device is empty; with it the ball is still there until the event is posted.

## Upstream issue (draft, not filed)

**Title:** `auto_fire_on_unexpected_ball: false` still ejects at once unless `player_controlled_eject_event` is set

**Body:**

```markdown
MPF 0.80.1. A ball device with an eject coil and `auto_fire_on_unexpected_ball: false` ejects an unexpected ball as
soon as it is counted. `_balls_added_callback()` makes the eject player controlled, but `OutgoingBallsHandler`
only waits when `player_controlled_eject_event` or `mechanical_eject` is set; otherwise it fires
`eject_one_ball()` immediately. Expected: the ball stays until something asks for an eject (as the documentation
of `auto_fire_on_unexpected_ball` suggests), or a config error saying the option needs
`player_controlled_eject_event`. Also: while such an eject waits, a second ball entering the device is not counted.
```
