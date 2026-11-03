#!/usr/bin/env bash
# libzedmd (PPUC, unmodified) + libserum (PPUC, unmodified) + dmd_bridge into one folder, native/bin/dmd_bridge by default: the
# folder mpf_dmd.bridge_dir() (common/netconfig) looks for. Used by the images' build (platforms/*/image) and by hand.
#   native/dmd_bridge/build_all.sh [OUT_DIR]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$here/../bin/dmd_bridge}"
mkdir -p "$OUT"
bash "$here/../libzedmd/build_libzedmd.sh" "$OUT" >&2
bash "$here/../serum/build_libserum.sh" "$OUT/lib" >&2
ln -sf lib/libserum64.so "$OUT/libserum64.so"
rm -rf "$OUT/lib/include" "$OUT/lib/libserum.a"
bash "$here/build.sh" "$OUT" "$OUT" >&2
echo "$OUT"
