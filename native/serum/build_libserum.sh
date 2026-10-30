#!/usr/bin/env bash
# Builds PPUC/libserum (a Serum colourisation player, GPL-2.0) as it is, without any change, for native/zedmd_feed
# (--serum LIB DIR ROM), which loads it with dlopen. Needs git, cmake and a C++ compiler.
#
#   native/serum/build_libserum.sh [OUT_DIR]      prints the path of the library, default OUT_DIR native/bin
#
# SERUM_VERSION (default v2.8.2, the stable line) and FRAMEUTIL_VERSION (default main, a header only) pin what is fetched.
set -euo pipefail
OUT="${1:-$(cd "$(dirname "$0")/.." && pwd)/bin}"
SERUM_VERSION="${SERUM_VERSION:-v2.8.2}"
FRAMEUTIL_VERSION="${FRAMEUTIL_VERSION:-main}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git clone -q --depth 1 --branch "$SERUM_VERSION" https://github.com/PPUC/libserum.git "$work/libserum"
git clone -q --depth 1 --branch "$FRAMEUTIL_VERSION" https://github.com/PPUC/libframeutil.git "$work/libframeutil"
mkdir -p "$work/libserum/third-party/include"
cp "$work/libframeutil/include/FrameUtil.h" "$work/libserum/third-party/include/"
cmake -S "$work/libserum" -B "$work/build" -DCMAKE_BUILD_TYPE=Release >&2
cmake --build "$work/build" -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)" --target serum >&2 || cmake --build "$work/build" -j4 >&2
mkdir -p "$OUT"
lib="$(find "$work/build" -maxdepth 1 \( -name 'libserum*.so' -o -name 'libserum*.dylib' \) | head -1)"
[ -n "$lib" ] || { echo "libserum was not built" >&2; exit 1; }
cp -L "$lib" "$OUT/"
echo "$OUT/$(basename "$lib")"
