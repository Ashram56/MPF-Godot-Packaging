#!/bin/bash
# usage: run_bench.sh GOZEN_SO CLIPS_DIR [ENV=VALUE ...] -- [bench args]    e.g.  run_bench.sh /data/work/bench/so/base.so /data/work/bench/clips GOZEN_HWDEC=0 -- --n=3 --mode=dup
# Headless Godot, GoZen decoding N clips on worker threads, no display, no GPU. Prints one RESULT line.
set -e
SO="$1"; CLIPS="$2"; shift 2
ENVS=(); while [ $# -gt 0 ] && [ "$1" != "--" ]; do ENVS+=("$1"); shift; done; shift || true
HERE="$(cd "$(dirname "$0")" && pwd)"
GODOT="${GODOT:-$(ls /home/*/MPF-Godot/toolchain/godot/Godot_v4.6.3-stable_linux.arm64 2>/dev/null | head -1)}"
P="$HERE/proj"; rm -rf "$P"; mkdir -p "$P/addons/gde_gozen/bin"
cp "$HERE/project.godot" "$HERE/bench.gd" "$HERE/bench.tscn" "$P/"
cp "$SO" "$P/addons/gde_gozen/bin/gozen.so"; touch "$P/addons/gde_gozen/bin/.gdignore"
cat > "$P/addons/gde_gozen/gozen.gdextension" <<'X'
[configuration]
entry_symbol = "gozen_library_init"
compatibility_minimum = "4.4"
[libraries]
linux.debug.arm64 = "res://addons/gde_gozen/bin/gozen.so"
linux.release.arm64 = "res://addons/gde_gozen/bin/gozen.so"
linux.debug.x86_64 = "res://addons/gde_gozen/bin/gozen.so"
linux.release.x86_64 = "res://addons/gde_gozen/bin/gozen.so"
X
"$GODOT" --headless --path "$P" --import >/dev/null 2>&1 || true
env "${ENVS[@]}" "$GODOT" --headless --path "$P" -- --dir="$CLIPS" "$@" 2>&1 | grep -E "opened|RESULT|ERROR|rror" | head -8
