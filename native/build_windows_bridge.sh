#!/usr/bin/env bash
# The ZeDMD bridge for the local platform on Windows (mpf_godot/local.py), built on Linux with mingw-w64:
# libzedmd (PPUC, pinned commit), libserum (PPUC, v2.8.2), both unmodified, and dmd_bridge.exe, into
# native/prebuilt/windows-x86_64/dmd_bridge/ with a SHA256SUMS. Needs git, cmake, autoconf/automake/libtool, mingw-w64.
#   native/build_windows_bridge.sh [OUT_DIR]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$here/prebuilt/windows-x86_64/dmd_bridge}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
bash "$here/libzedmd/build_libzedmd_windows.sh" "$work/libzedmd" >/dev/null
rm -rf "$OUT"
bash "$here/dmd_bridge/build_windows.sh" "$work/libzedmd" "$OUT" >/dev/null
bash "$here/serum/build_libserum_windows.sh" "$OUT" >/dev/null
rm -f "$OUT/libcargs64.dll"              # only libzedmd's own test tools use it
( cd "$OUT" && sha256sum -- *.exe *.dll > SHA256SUMS )
cat > "$OUT/SOURCES.txt" <<TXT
dmd_bridge.exe: native/dmd_bridge/dmd_bridge.cpp of MPF-Godot-Packaging, built with mingw-w64 (native/dmd_bridge/build_windows.sh).
zedmd64.dll: PPUC/libzedmd ${LIBZEDMD_SHA:-ed69d499d87d4d328bd328773cc6bbd3dadd64c3}, unmodified (https://github.com/PPUC/libzedmd).
libserialport64-0.dll, libsockpp64.dll: the commits pinned by that libzedmd's platforms/config.sh (sigrokproject/libserialport,
  fpagliughi/sockpp), unmodified.
serum64.dll: PPUC/libserum ${SERUM_VERSION:-v2.8.2}, unmodified (https://github.com/PPUC/libserum), GPL-2.0.
libstdc++-6.dll, libgcc_s_seh-1.dll, libwinpthread-1.dll: the mingw-w64 GCC runtime (GPL with the GCC runtime library exception).
Each library's licence is in its source repository; rebuild everything with native/build_windows_bridge.sh.
TXT
echo "$OUT"
