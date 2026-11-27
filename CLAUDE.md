# MPF implementation of a decoded Stern SAM game: instructions for Claude

> **STRICT RULE: DECOMPILE EVERYTHING (owner, 2026-11-24), and working rules 6-7 (owner, 2026-11-24). Binding on every agent, every game.**
> 1. Agent A decompiles **all**: the main ROM **and the firmware of every independent board** (any board with its own CPU, MCU, ROM or firmware: DMD, sound, others).
> 2. **Step zero, before anything else**: `docs/boards_inventory.md` lists every such board (board, CPU, ROM, decompile state `complet` / `partiel` / `absent`). A board that is not `complet` blocks the rules that depend on it.
> 3. The decompiled code is the source of every rule, value and behaviour, with the **ROM address cited**. It must cover scores, displays, inserts, coils and sounds. Every datum sent that is not understood is traced in the code (destination, function).
> 4. **Never code from an emulator capture** (PinMAME frames, renders, traces), images and DMD renders included. Last resort only, after a dead end, and **ask Vincent first**; record it in `docs/pinmame_waivers.md`.
> 5. Agent C codes nothing until A has delivered the **visual diagram taken from the code, one ROM address per node** (`docs/functional_diagram.md` or `docs/flow/`).
> 6. **Never end a turn by announcing "I continue" or "next step".** A finished turn stops the work. Chain on while doable work remains; stop only when everything is done, or on a blocker, which you name (what, and what you need).
> 7. **Post a factual progress report at least every 15 minutes** (done, running, blocked). The coordinator checks every active session every 15 minutes; a session that shows no progress is chased.
> 8. Enforced by `python tools/check_strict_rule.py .` (canonical copy: `tools/strict_rule/` in Stern-SAM-Decryption). Run it before every push; it must pass.

This repository holds the MPF half of the master plan for rebuilding a Stern SAM (and WPC / Whitestar) pinball game in MPF:
the agents C to G (`agents/`), the knowledge they read (`knowledge/`), the PuP tools (`tools/pup/`), and the game-agnostic MPF +
Godot + GMC toolchain with its fixes (`fixes/`), platforms and boards (`platforms/`), installers (`install/`).
Start from [agents/README.md](agents/README.md): it says which agent file covers the task at hand. Read only that agent file and the
knowledge docs it names; update it in the same session when you learn something it should say.

The decryption half (agent A, ROM extraction, the Ghidra decompile, traces, the functional diagram; agent B, VPX extraction) is in
Ashram56/Stern-SAM-Decryption: read its `agents/README.md` for the full plan. Rule of this plan (owner, 2026-11-23): every rule an
agent writes comes from the decompiled code, with its ROM address; traces and guides only confirm. Agent A delivers a functional
diagram from the code before agent C codes. Never ask A questions piecemeal: take what its deliverables say.

Game facts (addresses, status, owner decisions) belong in that game's repositories, not here (`tests/test_no_game_content.py`;
CONTRIBUTING.md). Every game-agnostic learning comes back here in the same session, without asking the user: a PR with write access,
otherwise a GitHub issue (CONTRIBUTING.md). Findings about taking a ROM or a table apart go to Stern-SAM-Decryption instead.

@agents/README.md
