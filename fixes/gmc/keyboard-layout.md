# Number keys and "/" do nothing in GMC on an AZERTY keyboard

| | |
|---|---|
| Id | `gmc/keyboard-layout` (this file: `fixes/gmc/keyboard-layout.md`) |
| Component | GMC |
| Kind | bug |
| Affected versions | GMC 1.0.0; a note in the game's patch says mpf-gmc `main` had the same change in 2026-10 (not re-checked here) |
| Platforms | all (any non-US layout: AZERTY seen; QWERTZ and others likely, inferred) |
| Found on | a Stern SAM recreation, 2026-10-03, French keyboard |
| Fact | observed |
| Our fix | [`mpf_godot/gmc_patch.py`](../../mpf_godot/gmc_patch.py) (edit `keyboard-layout`, `mpf_gmc.gd`) |
| Applied by | `python -m mpf_godot setup`, `python -m mpf_godot patch-gmc [GMC_DIR]`; idempotent |
| Upstream | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draft, not filed** |

## Problem

The switches a game maps to keys in `gmc.cfg` `[keyboard]` (for example `1` = start, `5` = coin, `/` = a
flipper) do nothing on an AZERTY keyboard.

## Cause

GMC's key handler in `mpf_gmc.gd` builds the key's name from the event's layout-dependent keycode (its label)
and looks it up with `if keycode in keyboard:`. On AZERTY the number row gives `&`, `é`, `"`, `'`, `(` without
Shift, and `/` needs Shift, so the names in `[keyboard]` never match.

## Fix

When the label has no entry, look the key up by its physical position on a US keyboard:

```diff
+	if not keycode in keyboard:
+		var physical = OS.get_keycode_string(event.get_physical_keycode_with_modifiers()).to_upper()
+		if physical in keyboard:
+			keycode = physical
 	if keycode in keyboard:
```

A key the layout labels the same as `[keyboard]` still matches first, so US keyboards behave as before.

## How to check

On a French layout, press the key with `5` on it (labelled `(`): the switch mapped to `5` in `[keyboard]` changes.
Before the patch nothing happens.

## Upstream issue (draft, not filed)

**Title:** gmc.cfg [keyboard] matches by key label only; number row and symbols fail on AZERTY and other layouts

**Body:**

```markdown
**Environment**
- GMC 1.0.0, Godot 4.5.x / 4.6.x, Windows / Linux with a French (AZERTY) layout

**Steps to reproduce**
1. In `gmc.cfg`: `[keyboard]` with `5 = ["switch", "s_coin"]` (or `1`, `/`).
2. Press that key on an AZERTY keyboard.

**Expected:** the switch changes.

**Actual:** nothing. The key handler in `mpf_gmc.gd` looks up the keycode string from the layout (`(` for the
key that is `5` on QWERTY; digits need Shift on AZERTY), so it never matches.

**Proposed fix** (we run this on GMC 1.0.0): fall back to the physical key, named as on a US keyboard:

    if not keycode in keyboard:
        var physical = OS.get_keycode_string(event.get_physical_keycode_with_modifiers()).to_upper()
        if physical in keyboard:
            keycode = physical
    if keycode in keyboard:
        ...

Labels still win, so nothing changes on US layouts. If `main` already has this, a 1.0.x release would help.
```
