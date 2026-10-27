# Platform limits

Some things a platform cannot run: measured, not guessed. The deployment infrastructure carries them, so a person
using the settings page, a hand edit or an old setting never ends up with a configuration the board cannot play.

## How a game declares them

A game's bundle has board profiles (`scripts/package/profiles.json`, picked from the device tree). A profile's
`limits` name, per option, the only choices the board allows and why:

```json
"limits": {"dmd.mode": {"choices": ["classic", "color256"], "why": "HD costs 45 points of CPU and a 50 s preload"}}
```

What each layer does with them:

| Layer | Behaviour |
|---|---|
| Settings tool (`bundle_options.py list`) | the schema's choices are narrowed to the allowed ones, `limited` carries the reason; `set` refuses the others |
| Setup page (`common/netconfig`, `settings_schema()`) | the form shows only the allowed choices and the reason, because it reads the schema through the tool |
| Install (`board_profile.py apply`, run by the setup page) | a value outside the limits (stored or the game's default) goes back to the profile's value, every install |
| Each start (`start.py`) | the same check, so a hand edit of the saved options cannot start an unplayable setup |
| A flag typed on `start.py`'s command line | not checked: for tests on the bench |

Anything else a profile sets stays a default the operator may change (set once at install). Only limits are enforced.

## Limits by platform

| Platform | Limits | Why (measured) |
|---|---|---|
| Raspberry Pi 4 | DMD: a real panel (PIN2DMD, ZeDMD) or dots drawn in the backglass window; no HD DMD; no DMD window of its own; no 3D light cycle background | HD DMD +45 points of CPU and a 50 s preload; own window 21 instead of 29.6 FPS; light cycles 10 FPS. See [raspberrypi.md](raspberrypi.md) |
| Jetson, Windows, macOS, Linux PC | none declared | |

The Pi's DMD options in order of fidelity: external panel (classic 128x32, any colour source the panel's driver takes),
or the overlay at 128x32 or, with a colour pack, 256x64 dots (2x exact, nearest filter, no glow).

A new platform's limits are added to its profile with the measurement in `why`, and a row here.
