# Knowledge base: rebuilding a decoded Stern game in MPF

The plan is [../agents/README.md](../agents/README.md). The files below are the reference docs agents C to G read; each is short, dense and
self-contained: read only the one your task needs. The decryption half's knowledge (SAM hardware, OS API, 6809 / WPC notes, rules templates,
decompile feedback) is in [Stern-SAM-Decryption `knowledge/`](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/knowledge/README.md).

| File | Read it when | Size |
|---|---|---|
| [sam_to_mpf_playbook.md](sam_to_mpf_playbook.md) | You build or maintain an MPF recreation of **any** game from ROM-derived specs. Architecture, build order, verification loop and every gotcha that cost real time. Game agnostic; Tron is only the worked example. | ~15 min |
| [mpf.md](mpf.md) | You work on how a game talks to MPF itself: its `virtual_pinball` platform and the VPX bridge, quirks of MPF 0.80.1. | ~4 min |
| [dmd_hd_upscaling.md](dmd_hd_upscaling.md) | You work on the optional HD display (128x32 DMD drawn at any window size). Separate from the rules work on purpose. | ~5 min |
| [dmd_conformance.md](dmd_conformance.md) | You check a recreation's DMD against PinMAME frame by frame (needed for a colourisation, which finds frames by their dots). | ~3 min |
| [pup_pack_format.md](pup_pack_format.md) | You play a PinUP Player pack with the MPF game: the pack's files, trigger codes, how each maps to a game event, how a DMD capture is matched. Tool: [../tools/pup/](../tools/pup/pup_decode.py); agent: [../agents/pup_pack.md](../agents/pup_pack.md). | ~6 min |

Not here, in [Stern-SAM-Decryption](https://github.com/Ashram56/Stern-SAM-Decryption): the SAM boards and bus, the OS API, the DMD display-effect engine rules read
from the ROM ([dmd_deff_engine_rules.md](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/knowledge/dmd_deff_engine_rules.md)), the rules spec templates, WPC / Whitestar notes.

New learnings come back as [../CONTRIBUTING.md](../CONTRIBUTING.md) says. What stays in each game's repositories: the game's own facts (addresses, status,
open work, owner decisions, departures from the ROM, player docs).

## Token rules for an agent taking over a game

1. Read this README, then one doc above. Do not read the whole game repo: every doc names the exact file to open.
2. Grep the specs, never read them whole. Spec files are long; the rules you need are a section.
3. Trust the code's module docstrings: each `game/<game>/*.py` and `scripts/*.py` opens with what it models and which ROM addresses it follows. `sed -n '1,/^"""$/p' FILE` reads only that.
4. Commit messages carry the "why" of each fix: `git log --no-merges --format='%h %s%n%b'` is cheaper than rediscovering a bug.
5. Run the checks instead of reasoning about them: `pytest -q tests` and `scripts/trace_check.py <scenario>` answer "does it match the ROM" faster than reading the trace.

Last updated 2026-11-23 (moved here from Stern-SAM-Decryption `knowledge/`: playbook, HD DMD, DMD conformance, PuP Pack format; MPF quirks page from Stern-SAM-Decryption PR #56).
