#!/usr/bin/env bash
# Builds PPUC/libserum (GPL-2.0) for Windows x64 on Linux with mingw-w64, as it is, without any change: serum64.dll, loaded by
# dmd_bridge.exe with LoadLibrary (--serum-lib). Needs git, cmake and the mingw-w64 package (posix threads); its runtime DLLs are the
# ones native/libzedmd/build_libzedmd_windows.sh copies.
#   native/serum/build_libserum_windows.sh [OUT_DIR]     default native/bin/libzedmd-win64/bin; prints the path of serum64.dll
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$here/../bin/libzedmd-win64/bin}"
SERUM_VERSION="${SERUM_VERSION:-v2.8.2}"
FRAMEUTIL_VERSION="${FRAMEUTIL_VERSION:-main}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git clone -q --depth 1 --branch "$SERUM_VERSION" https://github.com/PPUC/libserum.git "$work/libserum" 2>/dev/null
git clone -q --depth 1 --branch "$FRAMEUTIL_VERSION" https://github.com/PPUC/libframeutil.git "$work/libframeutil"
mkdir -p "$work/libserum/third-party/include"
cp "$work/libframeutil/include/FrameUtil.h" "$work/libserum/third-party/include/"
cmake -S "$work/libserum" -B "$work/build" -DCMAKE_TOOLCHAIN_FILE="$here/../cross/mingw-w64-x86_64.cmake" -DPLATFORM=win-mingw \
      -DARCH=x64 -DBUILD_STATIC=OFF -DCMAKE_BUILD_TYPE=Release >&2
cmake --build "$work/build" --target serum_shared -j"$(nproc)" >&2
mkdir -p "$OUT"
cp "$work/build/serum64.dll" "$OUT/"
x86_64-w64-mingw32-strip "$OUT/serum64.dll"
echo "$OUT/serum64.dll"
