#!/usr/bin/env bash
# Builds PPUC/libzedmd (the ZeDMD client: USB serial, Wi-Fi) as it is, without any change, with the dependencies its own
# platforms/<os>/<arch>/external.sh builds (cargs, libserialport, libframeutil, sockpp). Needs git, cmake, a C++ compiler,
# autoconf/automake/libtool.
#
#   native/libzedmd/build_libzedmd.sh [OUT_DIR]     default OUT_DIR native/bin/libzedmd: lib/ (libzedmd.so and its libraries),
#                                                   include/ (ZeDMD.h); prints OUT_DIR
#
# LIBZEDMD_SHA pins the commit (default: the one PPUC's libdmdutil builds with). PPUC's external.sh downloads GitHub archives with
# curl; on a network that only lets git through (the cloud sandbox's proxy) the curl function below makes the same files with git.
set -euo pipefail
LIBZEDMD_SHA="${LIBZEDMD_SHA:-ed69d499d87d4d328bd328773cc6bbd3dadd64c3}"
here="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$here/../bin/libzedmd}"
case "$(uname -s)" in Linux) os=linux;; Darwin) os=macos;; *) echo "unsupported OS" >&2; exit 1;; esac
case "$(uname -m)" in x86_64|amd64) arch=x64;; aarch64) arch=aarch64;; arm64) arch=arm64;; *) echo "unsupported CPU $(uname -m)" >&2; exit 1;; esac
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
        case "$out" in /*) ;; *) out="$PWD/$out";; esac
        t="$(mktemp -d)"
        git clone -q "https://github.com/$org/$repo.git" "$t/$repo"
        git -C "$t/$repo" checkout -q "$sha"
        git -C "$t/$repo" archive --format=tar.gz --prefix="$repo-$sha/" -o "$out" "$sha"
        rm -rf "$t"
    else
        command curl -sL "$url" -o "$out"
    fi
}
export -f curl

git clone -q https://github.com/PPUC/libzedmd.git "$work/libzedmd"
git -C "$work/libzedmd" checkout -q "$LIBZEDMD_SHA"
cd "$work/libzedmd"
bash "platforms/$os/$arch/external.sh" >&2
cmake -DPLATFORM="$os" -DARCH="$arch" -DBUILD_SHARED=ON -DBUILD_STATIC=OFF -DCMAKE_BUILD_TYPE=Release -B build >&2
cmake --build build -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)" >&2
mkdir -p "$OUT/lib" "$OUT/include"
cp -a build/libzedmd.so* build/libzedmd*.dylib "$OUT/lib/" 2>/dev/null || true
cp -a "third-party/runtime-libs/$os/$arch/"* "$OUT/lib/"
cp src/ZeDMD.h "$OUT/include/"
echo "$OUT"
