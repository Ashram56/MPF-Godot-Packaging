# Checking a recreation's DMD against PinMAME frame by frame

For any SAM game: does the recreation's classic 128x32 DMD draw what the ROM draws? Needed whenever something finds frames
by their dots (a Serum colourisation, a PuP trigger by picture), and a good regression measure otherwise. Worked example:
Tron Legacy LE 1.74 (`trn_174h`), Tron-Legacy-MPF `docs/dmd_conformance.md` and `scripts/conform/`.

## Method (observed, Tron, 2026-10-30)

1. **PinMAME dump.** libpinmame's `OnDisplayUpdated` callback, with `PinmameSetDmdMode(PINMAME_DMD_MODE_RAW)`, hands each
   frame of a SAM DMD as 128x32 bytes, `depth` 4: shades 0-15, the same levels as a recorded GIF (a GIF's grey / 17). Log
   `(emulated time, w, h, depth, bytes)` on every change, next to the rules trace of the same run (`tron_ref`; the Tron patch is
   `scripts/conform/tron_ref_dmddump.diff`). Same scenario script, same run: deterministic.
2. **The recreation's dump**: its classic DMD read back every rendered frame with the wall clock; the rules trace gets the wall
   clock too (the two processes share no clock).
3. **Align by the rules trace**: pair the `deff_start` events of both traces (same display effect id, in order, longest common
   subsequence) and compare the frames inside each pair's window with a small time tolerance (-0.2 / +0.6 s).
4. **The right metric is the colouriser's, not the dot count.** libserum identifies a frame by a CRC of the dots its per-frame
   comparison mask keeps (e.g. the status panel left out), sometimes by shape only, not by the whole picture. So measure
   "the Godot frame gets the same Serum frame id as PinMAME's", with the native decoder or libserum as the identifier: on Tron
   99.9 % of PinMAME's frames were known to the file, and the recreation matched 67 % (a whole-dot match was only 10 %).

## Gotchas

- libpinmame changes: the Tron `pinmame_arm_hook.patch` hunk on `libpinmame.cpp` (it appends at the end of the file) stopped
  applying to current PinMAME; apply the other files and append the hunk (Tron-Legacy-MPF `scripts/conform/build_tron_ref.sh`,
  PinMAME pinned at 540bbb1e).
- A ROM that differs from the PinMAME checksum (e.g. a version without music) still runs and gave the same effect trace.
- The ROM's animated transitions between text screens, the status panel and the boot version screen are where recreations
  differ first: a recreation that shows the final text over a static picture never produces the ROM's in-between frames.

## What fixing it taught (Tron, 2026-10-30)

- **Measure each effect on its own first**: render the effect, identify the ROM's reference capture frame and the recreation's
  frame with the colouriser, list the frames the ROM's file knows and the recreation's does not. In isolation most of Tron's
  effects were already right; the weak ones shared one pattern (below). A scenario run only says which effects to look at.
- **Jackpot-style effects play the clip bare, then the text comes with the effect's last sound call** (the last graphics
  frame's start + a few ticks), and the picture often drops to a single level under the text (every lit dot at level 1) or maps
  one level to another. Read the time and the levels off the capture (`timing.json` sounds and graphics frames; a per-level
  histogram of recreation against capture), not from the clip.
- **Random film clips**: when the ROM picks one clip of several at random (or by level), keep all of them and pick at run time.
  A hit-rate that asks for the same colourised frame then under-counts (the two runs pick different clips); watch the share of
  the recreation's frames that are **unknown** to the colouriser instead.
- **Bench gotcha**: regenerating the pictures without re-importing them in Godot leaves the effects' pictures blank in the
  render check (the first result then looks like a regression); always re-import after generating.
- **Take the font spacing and every glyph's x offset from the ROM's font table, never from rules tuned on captures** (Tron,
  2026-11-01). Tron's font generator had a rule "the comma is drawn one dot left in the plain fonts", found on two captures.
  The ROM's table says the outlined fonts do the same, and it gives two other fonts' spacing. A value "3,000,000" in an
  outlined font then sat one dot wide, and its black outline erased one column of the picture under it: 1 of 74 frames of
  the effect matched. With the table's values, 74 of 74 matched. A one-dot text error shows as a picture error when the font
  is outlined.
- **Bench gotcha (2)**: when the scenario's capture goes to a per-effect folder, copy it to the folder the scoring script
  reads before scoring, or the score is the old run's.
