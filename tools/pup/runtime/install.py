#!/usr/bin/env python3
"""Copy the PuP runtime into a game repository (or update the copy there).

    python tools/pup/runtime/install.py ../My-Game-MPF

Writes game/pup_runtime/ (MPF side), game/pup/ (Godot side), scripts/pup_setup.py, scripts/gen_pup.py,
scripts/pup_captures.py, scripts/pup_decode.py and pup_addons/ (the mp4 players: GDE GoZen, native_video),
scripts/video_check.py with game/tools/gozen_check.gd (GoZen's GPU decoding without the game), and records the source commit in game/pup_runtime/SOURCE.
The game keeps its own files: game/pup.cfg, its trigger map, game/modes/pup/config/pup.yaml and the one-line
hooks (README.md here lists them). Never edit the copies in the game: change them here and install again.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
FILES = {
    "game/pup_runtime": os.path.join(HERE, "game", "pup_runtime"),
    "game/pup": os.path.join(HERE, "game", "pup"),
    "game/tools/gozen_check.gd": os.path.join(HERE, "game", "tools", "gozen_check.gd"),
    "scripts/video_check.py": os.path.join(HERE, "scripts", "video_check.py"),
    "scripts/pup_setup.py": os.path.join(HERE, "scripts", "pup_setup.py"),
    "scripts/gen_pup.py": os.path.join(HERE, "scripts", "gen_pup.py"),
    "scripts/pup_captures.py": os.path.join(HERE, "scripts", "pup_captures.py"),
    "scripts/pup_decode.py": os.path.join(TOOLS, "pup_decode.py"),
    "pup_addons": os.path.join(HERE, "pup_addons"),
}


def install(game_repo):
    for dst_rel, src in FILES.items():
        dst = os.path.join(game_repo, *dst_rel.split("/"))
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
        print("  " + dst_rel)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, capture_output=True, text=True)
    with open(os.path.join(game_repo, "game", "pup_runtime", "SOURCE"), "w", encoding="utf-8", newline="\n") as f:
        f.write("Ashram56/Stern-SAM-Decryption tools/pup/runtime @ {}\n".format(head.stdout.strip() or "?"))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isdir(os.path.join(sys.argv[1], "game")):
        sys.exit(__doc__)
    sys.exit(install(sys.argv[1]))
