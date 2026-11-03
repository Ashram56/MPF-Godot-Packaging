#!/usr/bin/env bash
# Builds PPUC/libzedmd for Windows x64 on Linux with mingw-w64, as it is, without any change: the same pinned commit and the same
# dependencies as build_libzedmd.sh (libzedmd's platforms/config.sh pins them; its win-mingw/x64/external.sh builds them under MSYS2,
# this script does the same steps cross). Needs git, cmake, autoconf/automake/libtool and the mingw-w64 package (posix threads).
#
#   native/libzedmd/build_libzedmd_windows.sh [OUT_DIR]   default native/bin/libzedmd-win64: lib/ (zedmd64.dll, its DLLs and the
#                                                         mingw runtime DLLs), include/ (ZeDMD.h); prints OUT_DIR
set -euo pipefail
LIBZEDMD_SHA="${LIBZEDMD_SHA:-ed69d499d87d4d328bd328773cc6bbd3dadd64c3}"
here="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$here/../bin/libzedmd-win64}"
TC="$here/../cross/mingw-w64-x86_64.cmake"
HOST=x86_64-w64-mingw32
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
fetch() {   # fetch ORG/REPO SHA DIR: a pinned commit with git (networks that let only git through)
    git clone -q "https://github.com/$1.git" "$3"
    git -C "$3" checkout -q "$2"
}
fetch PPUC/libzedmd "$LIBZEDMD_SHA" "$work/libzedmd"
src="$work/libzedmd"
# shellcheck disable=SC1091
eval "$(grep -E '^(CARGS|LIBSERIALPORT|LIBFRAMEUTIL|SOCKPP)_SHA=' "$src/platforms/config.sh")"
inc="$src/third-party/include" bl="$src/third-party/build-libs/win-mingw/x64" rl="$src/third-party/runtime-libs/win-mingw/x64"
mkdir -p "$inc" "$bl" "$rl"
j="$(nproc)"

# cargs (libzedmd's test tools), named cargs64 as in PPUC's script
fetch likle/cargs "$CARGS_SHA" "$work/cargs"
sed -i 's/set_target_properties(cargs PROPERTIES DEFINE_SYMBOL CAG_EXPORTS)/&\nset_target_properties(cargs PROPERTIES OUTPUT_NAME cargs64)/' "$work/cargs/CMakeLists.txt"
cmake -S "$work/cargs" -B "$work/cargs/build" -DCMAKE_TOOLCHAIN_FILE="$TC" -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release >&2
cmake --build "$work/cargs/build" -j"$j" >&2
cp "$work/cargs/include/cargs.h" "$inc/"
cp "$work/cargs/build/libcargs64.dll.a" "$bl/"; cp "$work/cargs/build/libcargs64.dll" "$rl/"

# libserialport, named serialport64
fetch sigrokproject/libserialport "$LIBSERIALPORT_SHA" "$work/libserialport"
( cd "$work/libserialport"
  sed -i 's/libserialport\.la/libserialport64.la/g; s/libserialport_la/libserialport64_la/g' Makefile.am
  ./autogen.sh >&2 && ./configure --host="$HOST" >&2 && make -j"$j" >&2 )
cp "$work/libserialport/libserialport.h" "$inc/"
cp "$work/libserialport/.libs/libserialport64.dll.a" "$bl/"; cp "$work/libserialport/.libs/libserialport64-0.dll" "$rl/"

# libframeutil (headers)
fetch ppuc/libframeutil "$LIBFRAMEUTIL_SHA" "$work/libframeutil"
cp "$work/libframeutil/include/"* "$inc/"

# sockpp, named sockpp64
fetch fpagliughi/sockpp "$SOCKPP_SHA" "$work/sockpp"
sed -i 's/set(SOCKPP_SHARED_LIBRARY sockpp)/set(SOCKPP_SHARED_LIBRARY sockpp64)/' "$work/sockpp/CMakeLists.txt"
cmake -S "$work/sockpp" -B "$work/sockpp/build" -DCMAKE_TOOLCHAIN_FILE="$TC" -DCMAKE_BUILD_TYPE=Release >&2
cmake --build "$work/sockpp/build" -j"$j" >&2
cp -r "$work/sockpp/include/sockpp" "$inc/"
cp "$work/sockpp/build/libsockpp64.dll.a" "$bl/"; cp "$work/sockpp/build/libsockpp64.dll" "$rl/"

# the mingw runtime DLLs (posix threads flavour)
for d in libgcc_s_seh-1.dll libstdc++-6.dll libwinpthread-1.dll; do
    f="$(x86_64-w64-mingw32-g++-posix -print-file-name="$d")"
    [ -f "$f" ] || f="$(find /usr/lib/gcc/$HOST /usr/$HOST -name "$d" -path '*posix*' 2>/dev/null | head -1)"
    [ -f "$f" ] || f="$(find /usr/lib/gcc/$HOST /usr/$HOST -name "$d" 2>/dev/null | head -1)"
    cp "$f" "$rl/"
done

cmake -S "$src" -B "$src/build" -DCMAKE_TOOLCHAIN_FILE="$TC" -DPLATFORM=win-mingw -DARCH=x64 -DBUILD_SHARED=ON -DBUILD_STATIC=OFF \
      -DPOST_BUILD_COPY_EXT_LIBS=OFF -DCMAKE_BUILD_TYPE=Release >&2
cmake --build "$src/build" --target zedmd_shared -j"$j" >&2
mkdir -p "$OUT/lib" "$OUT/include"
cp "$src/build/zedmd64.dll" "$OUT/lib/"
cp "$src/build/"zedmd64.dll.a "$OUT/lib/" 2>/dev/null || cp "$src/build/"*.dll.a "$OUT/lib/"
cp "$rl/"*.dll "$OUT/lib/"
cp "$src/src/ZeDMD.h" "$OUT/include/"
echo "$OUT"
