#!/usr/bin/env bash
# Builds zedmd_feed. Without Serum: cc, libc only. With --serum: also libserum (pinned, CMake, a C++ compiler) linked in
# (GPL v2). Build on a build box, not on a Raspberry Pi. Cross compiling: CC=... CXX=... (e.g. "zig cc -target aarch64-linux-gnu").
#   native/zedmd_feed/build.sh OUT [--serum [WORKDIR]]
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$1; shift || true
CC=${CC:-cc}; CXX=${CXX:-c++}
if [ "${1:-}" != "--serum" ]; then $CC -O2 -Wall -o "$OUT" "$HERE/zedmd_feed.c"; exit 0; fi
W=${2:-$HERE/../../.cache/libserum}; mkdir -p "$W"; W=$(cd "$W" && pwd)
LIBSERUM_REF=v2.8.0
FRAMEUTIL_SHA=711ab21dcf9ad33d8db8339dfd3b1548bcc34cdb       # libserum's platforms/config.sh
[ -d "$W/libserum" ] || git clone -q --depth 1 --branch $LIBSERUM_REF https://github.com/PPUC/libserum.git "$W/libserum"
[ -d "$W/libframeutil" ] || { git clone -q https://github.com/PPUC/libframeutil.git "$W/libframeutil"; git -C "$W/libframeutil" checkout -q $FRAMEUTIL_SHA; }
cp "$W/libframeutil/include/FrameUtil.h" "$W/libserum/third-party/include/FrameUtil.h"
case "$(uname -s)" in Darwin) PLAT=macos;; *) PLAT=linux;; esac
case "$(uname -m)" in arm64|aarch64) ARCH=arm64;; *) ARCH=x64;; esac
cmake -S "$W/libserum" -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED=OFF -DBUILD_STATIC=ON -DPLATFORM=$PLAT -DARCH=$ARCH \
      -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" >/dev/null
cmake --build "$W/build" -j "$(nproc 2>/dev/null || echo 2)" --target serum_static 2>/dev/null || cmake --build "$W/build" -j 2
LIB=$(find "$W/build" -name libserum.a | head -1)
$CC -O2 -Wall -DWITH_SERUM -c "$HERE/zedmd_feed.c" -o "$W/zedmd_feed.o"
$CXX -O2 -Wall -std=c++17 -I"$W/libserum/src" -c "$HERE/serum_glue.cpp" -o "$W/serum_glue.o"
$CXX -o "$OUT" "$W/zedmd_feed.o" "$W/serum_glue.o" "$LIB" -lpthread
