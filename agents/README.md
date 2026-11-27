# Master plan, MPF half: from a decoded game to a playable MPF game

**Read this first when you build, improve, bridge, package or add a PuP Pack to a game.** The plan has two halves, one repository each:

| Half | Repository | Agents | What it delivers |
|---|---|---|---|
| **Decryption** | [Stern-SAM-Decryption](https://github.com/Ashram56/Stern-SAM-Decryption) | **A** ROM extraction, **B** VPX extraction | The game taken apart from the ROM and the `.vpx`: Ghidra decompile, reference traces, the functional diagram (code address per node), rules specs, IO tables, sounds, DMD frames, `monitor.yaml`, `script.vbs`. Full plan: its [`agents/README.md`](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/agents/README.md) |
| **MPF implementation** (this repository) | [MPF-Godot-Packaging](https://github.com/Ashram56/MPF-Godot-Packaging) | **C** strict recreation, **D** VPX bridge, **E** improvements, **F** packaging, **G** PuP Pack | A playable MPF game from A's and B's deliverables, on every platform, with the toolchain (MPF, Godot, GMC, their fixes, boards) this repository also carries |

Order: **A and B in parallel, then C, then F, D, E, G** (diagram below). The owner's inputs (ROM, `.vpx`, hardware line, repositories),
getting started, the project set-up and the kickoff message are in the decryption half's plan, sections 0 and 1: they are the same for
every game and are not repeated here. Tron Legacy LE 1.74 is the worked example in every agent file.

```
ROM ──► A ROM extraction ──► C strict recreation ──► E improvements (optional)
        (Stern-SAM-Decryption)     ▲        │  │
.vpx ─► B VPX extraction ──────────┘        │  └──► D VPX bridge ◄── B's table script
        (Stern-SAM-Decryption)              └─────► F packaging ◄── D's and E's options
                                                    G PuP Pack (optional, after C's display)
```

## The agents of this repository

| # | Agent | Instructions | Input | Output |
|---|---|---|---|---|
| C | **Strict recreation** | [recreation.md](recreation.md) | A's repo (as a submodule), B's layout | The game repo: the ROM's game exactly (rules, display, sound, lamps, service menu, settings, audits, credits, hardware overlays), checked against A's traces |
| D | **VPX bridge** (work in progress) | [vpx_bridge.md](vpx_bridge.md) | C's game, B's table script | VPX plays the ball, MPF replaces PinMAME and the ROM |
| E | **Improvements** (optional) | [improvement.md](improvement.md) | C's game | Switchable departures: HD DMD, clean fonts, colour, new modes; the ROM's behaviour stays one option away |
| F | **Packaging** | [packaging.md](packaging.md) | C's game repo, the owner's hardware line, D's and E's options | One line to install and one command to run on Windows, macOS and Linux (installers, `setup.py`, `run.py`, toolchain pins, Docker, CI), with every hardware option (MPF Monitor, P-ROC, VPX), and the game's full README |
| G | **PuP Pack** (optional) | [pup_pack.md](pup_pack.md) | C's game, a PuP Pack zip from its author | The pack's videos and music on the game's extra screens at PinUP Player's moments, installed from the author's zip |

Knowledge they read, in [`../knowledge/`](../knowledge/README.md): [sam_to_mpf_playbook.md](../knowledge/sam_to_mpf_playbook.md) (how C builds),
[mpf.md](../knowledge/mpf.md) (MPF's own quirks), [dmd_hd_upscaling.md](../knowledge/dmd_hd_upscaling.md) (E's HD display),
[dmd_conformance.md](../knowledge/dmd_conformance.md) (checking a DMD against PinMAME), [pup_pack_format.md](../knowledge/pup_pack_format.md) (G).
What they consume from the decryption half: [rom_extraction.md](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/agents/rom_extraction.md)
(especially its section 14, the deliverables), [vpx_extraction.md](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/agents/vpx_extraction.md),
[rom_decomp_feedback.md](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/knowledge/rom_decomp_feedback.md), the SAM hardware pages and, for a 6809 game,
[wpc_6809.md](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/knowledge/wpc_6809.md).

## Order and hand-offs

1. **C** starts when A has delivered the **functional diagram taken from the decompiled code** (one ROM address per node), the IO tables,
   sounds and DMD frames. **Rules come from the code, with the routine's address; traces only confirm** (owner, 2026-11-23). C does not
   ask A questions piecemeal: A decodes all rules in a block (per mode: start, values, end, effects) and C recodes node by node. Missing
   data goes to A as one batched request (Tron: [rom_decomp_feedback.md](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/knowledge/rom_decomp_feedback.md)).
2. **F** as soon as C's repo boots MPF + GMC: it ports the whole install and run kit at once, so the owner can install and test from the first
   playable build. F runs again whenever C, D or E add an option (P-ROC, VPX set-up, display modes).
3. **D** once C boots a game on virtual hardware (needs B's table script). **E** any time after C's display works, always switchable.
   **G** any time after C's display posts its effect events; F then adds the pack's zip option to every installer.
4. Every new ROM version or model: A again (A's section 15), then C's asset sync.

## Starting the agents

In a Claude project the coordinator starts them (one thread per agent). Outside a project, start the agent yourself; each line means the file
in `agents/` of Ashram56/MPF-Godot-Packaging:

| Agent | Message |
|---|---|
| C | "Act as the strict recreation agent (agents/recreation.md in Ashram56/MPF-Godot-Packaging) for `<game>` in `<game repo>` from `<asset repo>`." |
| D | "Act as the VPX bridge agent (agents/vpx_bridge.md) for `<game repo>`; the table is `<table.vpx>`." |
| E | "Act as the improvement agent (agents/improvement.md) for `<game repo>`: `<what to improve>`." |
| F | "Act as the packaging agent (agents/packaging.md) for `<game repo>`: one-line install and run on `<platforms>`, with `<options: MPF Monitor, P-ROC, VPX>`." |
| G | "Act as the PuP Pack agent (agents/pup_pack.md) for `<game repo>`: the pack is `<zip or link>` by `<author>`; screens `<backglass, DMD, topper>`." |

## Rules every agent follows

- **STRICT RULE: DECOMPILE EVERYTHING** (owner, 2026-11-24; full text at the top of `CLAUDE.md`). C refuses to code a feature whose board is not `complet` in the game's `docs/boards_inventory.md`, or before A's visual diagram (one ROM address per node) exists, and never builds assets (DMD images, sounds, lamp shows) from emulator captures without the owner's prior approval. Run `tools/check_strict_rule.py` of the game repository before every push.

- **Feed the knowledge base back, always** ([CONTRIBUTING.md](../CONTRIBUTING.md)): every game-agnostic learning, in the same session, without being
  asked: a pull request with write access, else an issue opened directly. Say in the report which one.
- **Route by topic.** Taking a ROM or a table apart: Stern-SAM-Decryption. Rebuilding it in MPF, Godot, GoZen, GMC, MPF itself, platforms, boards,
  installers: here. Facts of one game only (status, open work, owner decisions, addresses, run values): that game's repositories. A game's name
  appears only in the method documents as a worked example; the toolchain code holds none (`tests/test_no_game_content.py`).
- **Strict first, improvements second.** C reproduces the ROM; anything that differs is E's, is switchable, and gets a row in the game repo's
  `docs/rom_differences.md`.
- **Label facts**: observed (emulator or machine), code (decompile/table, with the ROM address), inferred.
- **Decompile first** (owner directive): every rule cites its routine in the Ghidra decompile; traces and guides only confirm. Trace-only facts stay
  "code open" until cited.
- **Machine-readable first**: tables (CSV/JSON) that code reads, prose second.
- **Never commit the ROM**, and never name or describe third-party colourisation or media work in a public repo beyond a pointer to the private repo.
- **Test locally before pushing**: `pytest -q tests` in the game repo (and the trace and render checks for rules or display work); in this
  repository `python -m unittest discover -s tests`.
- **Owner preferences (Ashram56's games):** go ahead without asking for approval; pick a default, say which, and list what needs the owner's
  judgement as a short numbered list. Small update zips of changed files only. Answer in the owner's language (Vincent often writes in French).

Last updated 2026-11-23 (created when the master plan was split: decryption in Stern-SAM-Decryption, MPF implementation here).
