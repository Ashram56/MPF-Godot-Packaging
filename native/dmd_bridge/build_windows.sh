#!/usr/bin/env bash
# Builds dmd_bridge.exe for Windows x64 on Linux (mingw-w64) against the libzedmd of native/libzedmd/build_libzedmd_windows.sh.
#   native/dmd_bridge/build_windows.sh [LIBZEDMD_WIN_DIR] [OUT_DIR]   default native/bin/libzedmd-win64; OUT_DIR gets dmd_bridge.exe
#                                                                     and every DLL it needs beside it (Windows finds DLLs there)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
D="${1:-$here/../bin/libzedmd-win64}"
OUT="${2:-$D/bin}"
mkdir -p "$OUT"
x86_64-w64-mingw32-g++-posix -O2 -Wall -std=c++17 -I"$D/include" -o "$OUT/dmd_bridge.exe" "$here/dmd_bridge.cpp" \
    "$D/lib/zedmd64.dll.a"
cp "$D/lib/"*.dll "$OUT/"
x86_64-w64-mingw32-strip "$OUT/"*.exe "$OUT/"*.dll
echo "$OUT/dmd_bridge.exe"
