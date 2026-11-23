# MPF implementation of a decoded Stern SAM game: instructions for Claude

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
