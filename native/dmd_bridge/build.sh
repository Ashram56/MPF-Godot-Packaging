#!/usr/bin/env bash
# Builds dmd_bridge against the libdmdutil that native/dmdutil/build_dmdutil.sh made.
#   native/dmd_bridge/build.sh [DMDUTIL_DIR] [OUT_DIR]     DMDUTIL_DIR default native/bin/dmdutil (lib/, include/), OUT_DIR the same
# The program finds the libraries in lib/ next to itself (rpath $ORIGIN/lib).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
D="${1:-$here/../bin/dmdutil}"
OUT="${2:-$D}"
${CXX:-c++} -O2 -Wall -std=c++17 -I"$D/include" -o "$OUT/dmd_bridge" "$here/dmd_bridge.cpp" -L"$D/lib" -ldmdutil \
    -Wl,-rpath,'$ORIGIN/lib' -pthread
echo "$OUT/dmd_bridge"
