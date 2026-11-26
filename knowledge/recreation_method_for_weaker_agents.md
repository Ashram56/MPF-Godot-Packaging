# Recreating a decoded game in MPF with less capable agents: method, improvements, escalation

Companion of `knowledge/decode_tricks_and_method.md` in Stern-SAM-Decryption (the decoding half: Unicorn runs, recipes, proofs). This is the MPF
half (agents C to F): what to do with the decoded code. Game-agnostic. Written from the Tron base-game audit (2026-11).

## 1. Method for the strict recreation (agent C)

1. **Start from the diagram, not from the game's behaviour.** One MPF unit (feature, mode, display effect) per diagram node, with its ROM address in the
   code comment and in the test's name. No node, no code.
2. **Take values from the generated data** (tables in the asset repo: coils, adjustments, text ids, timings in OS ticks), never typed from a trace or a
   capture. The test reads the same table.
3. **Display = the code's frames.** The classic DMD is built only from the frames the ROM code run produced (asset repo `dmd_code`); no capture is
   a source (not even as a fallback when a file is missing: fail the build, or mark the effect "no render" with the code reason).
4. **Verify mode by mode with the bench** (player robot on a physical table, modes one by one, adjustments, random games): before the change, after the change,
   and again after every asset sync. Every difference between the bench and the ROM is either fixed or logged in `rom_differences.md` with its address.
5. **Test names the address.** A test that states a ROM routine is a specification; a test copied from a trace only confirms.
6. **Adjustments are rules too**: each adjustment the ROM reads must change the MPF behaviour (the bench's adjustments-in-play module lists the ones that do not).
7. **Check pass**: `check_strict_rule.py` before every push, the full tests, and a regeneration of the generated media (it must be reproducible from the asset repo alone).

## 2. Method when improvements exist (agent E)

* Every improvement is **switchable** and the switch's off state is the ROM's behaviour; the base game with all improvements off must pass the same
  bench and the same DMD comparison as before the improvement existed.
* Each improvement gets: a row in `rom_differences.md`, an owner decision with date, a setting (option, service-menu entry), and a test of both states.
* Departures that are only presentation (HD, colour, glow) never touch the rules path; departures to rules (extended modes, new menus) hook in through
  new events, not by editing the ROM-derived feature.
* After a rules change, rerun the bench; after a display change, rerun the media generation and the conformance comparison with improvements off.
* An asset sync (new decoded data) is merged only after the above passes; improvements are re-checked, not assumed.

## 3. Escalation rule

An agent blocked on a task (two failed attempts at the same step, a ROM behaviour it cannot place in the diagram, a bench difference it cannot explain,
a Godot/MPF/platform fault outside its competence) **defers the task to a more capable agent** and writes the hand-over: the node and ROM addresses,
what was tried and measured, the failing test or bench output, and the exact question. It does not paper over the gap with an approximation or a capture,
and it carries on with the unblocked work. Only the owner can grant a PinMAME waiver (`docs/pinmame_waivers.md`).
