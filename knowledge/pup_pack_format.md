# PuP Packs: the format, decoded for a game without PinMAME

A PuP Pack is the media a PinUP Player setup plays around a Visual Pinball table: videos on the backglass, the
topper or a full DMD screen, music, pictures. PinUP Player watches PinMAME (the DMD, the switches, the lamps)
and fires the pack's rows. An MPF recreation has no PinMAME, so to play the same pack at the same moments it
has to know what each row waits for and translate it into the game's own events. This page is that
translation, for any pack; the [PuP Pack agent](../agents/pup_pack.md) uses it, and
[`tools/pup/pup_decode.py`](../tools/pup/pup_decode.py) reads a pack this way. Tron Legacy's pack is the worked
example (its decoded form: [Tron-LE-PuP-Pack `docs/decoding/`](https://github.com/Ashram56/Tron-LE-PuP-Pack/blob/main/docs/decoding/README.md)).
Labels: **observed** (seen in PinUP Player or in a pack), **code** (as a working player implements it),
**inferred**.

## 1. Files

The pack is one folder named after the PinMAME ROM set it was made for (Tron: `trn_174h`, LE 1.74), usually
shipped in a zip under `PUPVideos/<romset>/`:

| File | What it is |
|---|---|
| `screens.pup` | CSV: the PuP screens (layers) the pack uses, their mode and background |
| `playlists.pup` | CSV: one row per media folder (a playlist) |
| `triggers.pup` | CSV: one row per action: when `Trigger` is true, play something on a screen |
| `<playlist>/` | one folder per playlist: mp4 videos, mp3 music, png/jpg pictures |
| `PupCapture/<n>.bmp` | DMD frame captures; `D<n>` in `triggers.pup` refers to `<n>.bmp` |
| `PuP-Pack_Options/*`, `Option *.bat` | alternative `.pup` sets (with or without a topper, a full DMD...): the `.bat` copies one set over the active files |

The CSVs have a header row, UTF-8 (sometimes with a BOM), quoted fields; PinUP Player runs on Windows, so
names are case-insensitive (a row's `PlayList` may differ in case from the folder). Read them as they are and
never edit them: a new release of the pack then needs no code change. (observed, Tron)

## 2. `screens.pup`

Columns: `ScreenNum, ScreenDes, PlayList, PlayFile, Loopit, Active, Priority, CustomPos`.

- `Active` is the screen's mode: `ForceBack` (an underlay: its background shows whenever nothing else plays),
  `ForcePop` / `ForcePopBack` (a top layer: only visible while something plays on it), `Show`, `off` (not
  used by this option set), and music-only screens. (observed, Tron: 2 `ForceBack`, 12 `ForcePopBack`,
  13/14 `off`)
- `PlayList` / `PlayFile` is the screen's background. `CustomPos` (`ref,x,y,w,h`, in percent of screen `ref`)
  places a layer over another one (Transformers: screens 11-15, `ForceBack`, are the text panel, the two crests
  and the two faces boxes of backglass screen 2; each has its own background video and its own trigger rows).
- Two folder names are PinUP Player conventions, not playlists to play like the others: `PuPOverlays` (a
  transparent PNG that stays over the screen's video: Transformers row 246 "Overlay - Default", `D0` on screen 2,
  the backglass frame) and `PuPAlphas` (alpha masks of the backbox art; Transformers' 4:3 one also holds the DMD
  panel art). (inferred from the packs and `Option Selected.jpg`)
- Screen numbers are the pack author's choice; read them, don't assume them. Decide per screen which window of
  the game shows it (Tron: 2 + 12 backglass, 13 + 14 topper, 15 music only).
- A clean still of a screen's art (for a service or status page drawn over it): packs rarely ship one
  (Tron: `PuPFrames` holds a cabinet layout picture, not the backglass). The background loop has it: only the
  inside of the frame and the glow move, so the per-pixel **median** of the loop's frames (ffmpeg at 4 fps, then
  numpy `median(axis=0)`) is a clean still, and the per-pixel standard deviation shows which areas move. Make it
  at install time from the installed pack; never commit it. ffmpeg alone does it, no numpy:
  `-vf fps=F,tmedian=radius=R -frames:v 1` with R = (frames - 1) / 2, at most 127 (255 frames), outputs the one
  median frame. (observed: Tron `Background - Backglass/TronLegacyBG.mp4`, 1920x1080, 61 frames over 15 s;
  Tron-Legacy-MPF `scripts/pup/gen_pup.py` `make_still`)
- Drawing a page over a PuP window in Godot (Tron's service menu on the backglass): draw it once per change at the
  art's own size in a `SubViewport` (`UPDATE_ONCE`) and show its texture fitted as the videos are, so text is
  rasterised at full size and nothing redraws per frame; fade with the node's `modulate`. A Control added to a
  window that already has a size needs `set_anchors_and_offsets_preset(PRESET_FULL_RECT)`: `set_anchors_preset`
  keeps the size it had (the window's first size) as offsets, so it stops following later resizes. Darken the
  art only inside its neon frames (a signed-distance shader on the still) so the frames stay lit. (observed)
- Screens set `off` by the shipped option may be the pack's optional displays (Tron: the topper; the pack's
  `Option Selected.txt` says to set them to `ForceBack` / `ForcePop` when a topper exists). (observed)

## 3. `playlists.pup`

Columns: `ScreenNum, Folder, Des, AlphaSort, RestSeconds, Volume, Priority`. `Folder` is the playlist's name
and folder. `AlphaSort=1`: each fire plays the next file in name order; `0`: a random one. `RestSeconds` and
`Volume` are the playlist's defaults (a trigger row overrides them). (code)

## 4. `triggers.pup`

Columns: `ID, Active, Descript, Trigger, ScreenNum, PlayList, PlayFile, Volume, Priority, Length, Counter,
RestSeconds, Loop, Defaults`. Rows with no `Trigger` (titled `**** ... ****`) are section headers.

| Column | Meaning (code) |
|---|---|
| `Trigger` | the condition: one or more terms joined by commas, all true at once (section 5) |
| `ScreenNum` | where to play |
| `PlayFile` / `PlayList` | that file of the playlist, or (empty file) the playlist's next file |
| `Priority` | a play replaces what runs on that screen when its priority is >= the running one, else it is dropped |
| `RestSeconds` | after firing, the row ignores its trigger for that long |
| `Loop` | empty: once; `Loop`: until replaced or stopped; `SetBG`: becomes the screen's background and plays now when its priority is >= the running video's, a looping one included (inferred from the pack: Transformers ends its looping CHOOSE YOUR SIDE box, priority 3, with SetBG rows at priority 4 when the side is chosen; kept up, the box never left); `StopFile`: stop that file; `StopPlayer`: stop the screen; `SkipSamePrty`: drop the play if the running one has the same priority |
| `Volume`, `Length` | volume override (100 = normal); play time cap in seconds |

When a video ends, the screen's background comes back. (code)

## 5. Trigger codes and their MPF translation

| Code | PinUP Player fires it when | In the MPF game |
|---|---|---|
| `D<n>` | PinMAME's DMD shows capture `<n>` (section 6) | the event the game posts when the display effect that draws that frame takes the DMD (Tron: `tron_deff_<id>`); found by matching the capture against every frame the game can show |
| `D0=1` | PinUP Player starts | an event the game posts when its PuP player is ready |
| `W<n>=1` / `W<n>` | PinMAME switch `n` closes | the switch, **by name**: PinMAME's switch number is the SAM switch number, but a hardware overlay (P-ROC) renumbers switches |
| `L<n>=1` | PinMAME lamp `n` is on | rarely what it looks like on SAM: PinMAME's lamp numbering is not the SAM lamp matrix numbering (Tron: `L35`). Replace the whole row with the game event it means. On WPC it is the lamp matrix number 11-88 (T2 `L44` = EXTRA BALL) |
| `S<n>` | PinMAME solenoid `n` fires | WPC: the solenoid number (T2 `S8` = kickback) |
| several terms (`W11=1,L35=1`) | all are true at once | an override: the row ID mapped to the game event (Tron: row 23, VUK while Flynn's Arcade is lit = the arcade award effect) |
| other letters | other PinMAME outputs or table script events (inferred: none in the Tron pack) | map by hand, per row |

Keep this translation in one data file (a trigger map: `dmd: {n: [events]}`, `switches: {n: name}`,
`override: {row ID: [events]}`), never in the pack and never spread through the code. An event can carry a
condition on its arguments when one effect draws several captures by variant (Tron:
`tron_deff_112{award==1}` for DOUBLE SCORING). (code)

## 6. How a capture is matched

`PupCapture/<n>.bmp` is a 128x32, 24-bit BMP: a screenshot of PinMAME's DMD. Pixels of exactly `RGB(253,0,253)`
(purple) draw a rectangle; only the dots inside it count, each lit (red >= 9) or unlit, and the purple pixels
themselves are ignored. `D<n>` fires when a DMD frame has the same dots inside that rectangle. A capture with
**no purple pixel compares the whole frame** (observed, Transformers `tf_180`: captures 1, 8, 9, 14 and 15 have no
rectangle; 8 and 9 match the BALL SAVED and TILT effects at 100 % as whole frames). (code, checked on all 98 Tron
captures: 83 match a recorded frame at 100 %, 88 at 90 % or more; Transformers: 225 captures, 150 at 100 %)

To translate one, compare it with every frame the game can show (each display effect's recorded animation, its
variants, the ROM's shared library animations credited to the effects that play them) and score each frame
by intersection over union of lit dots inside the rectangle. The effects with a frame within 0.5 % of the best
(2 % when the best is under 97 %) are the candidates. Then judge:

- **Several effects share the frame** (Tron D7: the three skill shots): map all of them.
- **A partial frame** (a score line, "00" in player 1's score: Tron D2): any frame with that text matches; map
  it to the game event that means it (`player_added{num==1}`), not to the best-scoring effect.
- **A frame the game never records** (the boot screen, the attract cycle's logo): the game posts its own event
  (Tron: `pup_power_up` at the first attract, `pup_attract_cycle` on a timer).
- **Captures no row uses** (Tron: 14 of 98): leave them out of the map, note them. Rows with `Active=0` don't count.
- **One effect, several animations** (Transformers: 75 captures score 100 % against a ROM library animation that
  no effect is credited with): the ROM picks the animation by game state (the battle's shot number, the
  player's side, the lock number, the wizard shot), while the ROM extraction recorded one variant per effect.
  Map the capture to that effect **with a condition on the event's arguments or the player's state**
  (`game_deff_102{hit==3, completed==0}`, `game_deff_40{state.side==1}`, `game_deff_140{values.0==2}`), or a
  count since the mode's intro (`counters:`). When the game does not post the argument, add it in the call
  (a one-line hook: Transformers' battle hit effect got `hit` and `completed`). The pack's row order gives the
  order of the shot videos (inferred until checked in play).
- Two captures of one effect firing the same row must send it once.

Re-run the match whenever the game's DMD animations change: an effect renumbered or redrawn breaks only the
lines whose mapped effect no longer draws the capture.

## 7. Music

A pack that replaces the game's music plays it on a music-only screen with `SetBG` rows (Tron: screen 15, the
OST; Transformers: screen 4, `off` in the shipped option, whose ReadMe asks for a muted ROM). In PinUP Player the ROM's own music is muted by the user. In MPF, drop the ROM's music calls only once the
PuP player says it is ready (videos and music in place); otherwise the game keeps its own music. Speech and
effects always stay. (code, Tron)

## 8. A pack and its ROM version

A pack is made against one ROM version: its captures are that version's frames. Another version, or another
release of the pack, can change captures or rows: re-run the match and the decode, and fix the map lines that
change. Record the pack's version and author with the game. (inferred)

Last updated 2026-11-21 (WPC lamp and solenoid terms, T2; before 2026-10-18: median still of a background loop, with ffmpeg tmedian; a page drawn over a PuP window; from the Tron pack's decoding in Tron-LE-PuP-Pack and the Tron-Legacy-MPF-PuP player; whole-frame
captures, effects with several animations, CustomPos boxes and PuPOverlays from the Transformers pack).
