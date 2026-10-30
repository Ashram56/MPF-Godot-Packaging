#!/usr/bin/env bash
# Builds PPUC/libdmdutil (ZeDMD through libzedmd, PIN2DMD, Serum colour through libserum), as PPUC pins it and without any
# change, together with the pinned libusb, libzedmd, libserum, libpupdmd and libvni that its own platforms/<os>/<arch>/external.sh
# builds. Needs git, cmake, a C++ compiler, autoconf/automake/libtool (libusb).
#
#   native/dmdutil/build_dmdutil.sh [OUT_DIR]       default OUT_DIR native/bin/dmdutil: lib/ (libdmdutil.so and its libraries),
#                                                   include/ (DMDUtil headers); prints OUT_DIR
#
# DMDUTIL_SHA pins libdmdutil (it has no release tags). PPUC's external.sh downloads GitHub archives with curl; a network that
# only lets git through (the cloud sandbox's proxy) gets the same files from git clone + git archive (the curl function below).
set -euo pipefail
DMDUTIL_SHA="${DMDUTIL_SHA:-6a3ed78e53d3d4bf36e5957cb51432fd45d4e70b}"
here="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$here/../bin/dmdutil}"
case "$(uname -s)" in Linux) os=linux;; Darwin) os=macos;; *) echo "unsupported OS" >&2; exit 1;; esac
case "$(uname -m)" in x86_64|amd64) arch=x64;; aarch64|arm64) arch=aarch64;; *) echo "unsupported CPU $(uname -m)" >&2; exit 1;; esac
[ "$os" = macos ] && arch=$([ "$(uname -m)" = arm64 ] && echo arm64 || echo x64)
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# curl -sL https://github.com/ORG/REPO/archive/SHA.tar.gz -o FILE   ->   the same tarball made with git
curl() {
    local url="" out=""
    while [ $# -gt 0 ]; do
        case "$1" in -o) out="$2"; shift 2;; -*) shift;; *) url="$1"; shift;; esac
    done
    if [[ "$url" =~ ^https://github.com/([^/]+)/([^/]+)/archive/([0-9a-f]{40})\.tar\.gz$ ]]; then
        local org="${BASH_REMATCH[1]}" repo="${BASH_REMATCH[2]}" sha="${BASH_REMATCH[3]}" t
        t="$(mktemp -d)"
        case "$out" in /*) ;; *) out="$PWD/$out";; esac
        git clone -q "https://github.com/$org/$repo.git" "$t/$repo"
        git -C "$t/$repo" checkout -q "$sha"
        git -C "$t/$repo" archive --format=tar.gz --prefix="$repo-$sha/" -o "$out" "$sha"
        rm -rf "$t"
    else
        command curl -sL "$url" -o "$out"
    fi
}
export -f curl

git clone -q https://github.com/PPUC/libdmdutil.git "$work/libdmdutil"
git -C "$work/libdmdutil" checkout -q "$DMDUTIL_SHA"
cd "$work/libdmdutil"
bash "platforms/$os/$arch/external.sh" >&2
cmake -DPLATFORM="$os" -DARCH="$arch" -DBUILD_SHARED=ON -DBUILD_STATIC=OFF -DCMAKE_BUILD_TYPE=Release -B build >&2
cmake --build build -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)" >&2
mkdir -p "$OUT/lib" "$OUT/include"
cp -a build/libdmdutil.so* "$OUT/lib/" 2>/dev/null || cp -a build/libdmdutil*.dylib "$OUT/lib/"
cp -a "third-party/runtime-libs/$os/$arch/"* "$OUT/lib/"
cp -a include/DMDUtil "$OUT/include/"
cp -a third-party/include/. "$OUT/include/"
for f in build/dmdserver; do [ -x "$f" ] && cp "$f" "$OUT/"; done
echo "$OUT"
