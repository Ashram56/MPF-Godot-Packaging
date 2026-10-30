#!/usr/bin/env bash
# Builds dmd_bridge against the libzedmd that native/libzedmd/build_libzedmd.sh made (libserum is loaded at run time with
# dlopen: --serum-lib, native/serum/build_libserum.sh).
#   native/dmd_bridge/build.sh [LIBZEDMD_DIR] [OUT_DIR]     LIBZEDMD_DIR default native/bin/libzedmd (lib/, include/), OUT_DIR the same
# The program finds the libraries in lib/ next to itself (rpath $ORIGIN/lib).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
D="${1:-$here/../bin/libzedmd}"
OUT="${2:-$D}"
${CXX:-c++} -O2 -Wall -std=c++17 -I"$D/include" -o "$OUT/dmd_bridge" "$here/dmd_bridge.cpp" -L"$D/lib" -lzedmd -ldl \
    -Wl,-rpath,'$ORIGIN/lib' -pthread
echo "$OUT/dmd_bridge"
