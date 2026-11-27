# Port the decompiled routines; do not iterate compare / modify / compare

**Read this when you rebuild a display effect or a mode's rules.** Owner decision (2026-11-27): write each piece of the game directly from the decompiled
routine, with its ROM address, and use the comparison only to confirm it. Comparing a hand-built or generated version with the ROM and retouching
it frame by frame converges slowly (every fix is a guess at what the routine does) and keeps unexplained misses; a port is exact the first time and a
miss then points at a precise primitive, input or timing.

## Method (worked on the DMD of a Stern SAM game, 2026-11-27)

1. **Port the primitives once**, from their decompile: page clear, image blit (copy / palette / keyed), palette helpers, text (font record, glyph advance, centre /
   right edge, width), rectangle fill. One small module, one ROM address per function in its docstring. Game side only; no emulator output feeds it.
2. **Port an effect's routine as a function of its inputs**: the task arguments and the RAM values it reads (score, counters, tick counter), never of captured
   frames. Keep the routine's own timing (flip every N ticks, the loop counters) and its end sequence.
3. **Check it against the ROM code run in an emulator (Unicorn) for the same inputs**, flip by flip, comparing by tick, not by index. The emulator runs the real code,
   so this is the ROM, not a capture. Put the check in a script (`engine_check`-style) and a test that skips without the ROM.
4. **Make the game draw the port's output** (a list of draw items: image, palette, text, rectangle per flip, sent once per effect start), not a re-implementation in
   the display engine; then a measure of the game's frames against the ports' frames says the transport is exact.
5. **Take every random choice from the ROM's own generator**: port it (a 32-bit LCG and `random_below`) so the game and the emulator make the same draws in the
   same order from the same state; for a clip or reel pick, give the draw to the emulator as input (a log line per pick) rather than matching frames afterwards.
6. **Measure per scenario** the share of the game's distinct frames found among the code run's and the ports' frames. A miss is attributed to an effect by the
   last effect start before the frame: that attribution can be wrong (an overlay effect hides under the effect that was running); look at the frames.

## What it found that tuning had not

- A loop whose counters are decremented before the line is chosen starts its replay line one tick earlier and repeats every `0x138 + 0x4e2` ticks, not on the
  period the captures suggested.
- The score message is `%,02lu`: a zero score shows two digits.
- Text drawn from font images (not the platform's font) is what makes small differences vanish.
- A scenario's remaining misses were value state (scores, counters) and overlays, not drawing.

## A cheaper first step: replay every effect's op list (worked on Transformers, 2026-11-27)

When agent A has lifted every display effect's code in the emulator (one op list per effect: each draw call with its tick,
page, image, palette, text format and call site), the game can drop all prerendered frames before porting any routine:
replay each op list tick by tick on page buffers with the port of the drawing primitives, and give each printf the value the
rules have for its call site now. What it takes:

- **Looping effects** (a background whose code is an endless loop; the lift stopped after N ticks): find, at build time, the
  period of the frames over the second half of the run and the earliest tick it holds from; at play time keep a copy of the
  pages at that tick and go back to it each time the replay passes the end of the run.
- **Effects whose drawing reads RAM** (the player's side, a mode's phase, shots left): one op list per state, lifted with that
  RAM set, picked by the rules at start and switched while the effect runs when the state changes (at the same tick, not from
  the start). A wrong page that nobody notices on frames shows up here: the rules must name the state.
- **Two slides**, one for the mode's background effect and one for the foreground one, so the background keeps its own replay
  under the foreground.
- **Size**: gzip the op lists (about 20:1 on JSON); load each once.

It is not the end state (a branch no op list ran is not drawn); porting the routines that read RAM is.

## For rules

Apply the same order to a mode: read the routine, write its state machine and values with the ROM address, then run the rules test bench and the traces before
and after. A rule that needs a hand-tuned number is a routine not yet read. Departures stay in the game's `docs/rom_differences.md`.

Last updated 2026-11-27 (written from the Tron DMD port; op-list replay step from Transformers).
