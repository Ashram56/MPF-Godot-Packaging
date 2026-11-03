#!/usr/bin/env bash
# Builds libgpiod (libzedmd's Raspberry Pi/Jetson GPIO dependency on aarch64) for the target, into PREFIX (default native/bin/libgpiod).
# On an x86 machine: CC=aarch64-linux-gnu-gcc QEMU_LD_PREFIX=/usr/aarch64-linux-gnu TARGET_ARCH=aarch64 (qemu-user in binfmt_misc, autoconf-archive).
# Then build libzedmd with PKG_CONFIG_PATH=PREFIX/lib/pkgconfig CPATH=PREFIX/include LDFLAGS="-LPREFIX/lib -Wl,-rpath-link,PREFIX/lib"
# and copy PREFIX/lib/libgpiod.so* next to libzedmd.so.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${1:-$here/../bin/libgpiod}"
TAG="${LIBGPIOD_TAG:-v2.2.4}"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
git clone -q https://github.com/brgl/libgpiod.git "$work/gp"
git -C "$work/gp" checkout -q "$TAG"
cd "$work/gp"
if [ -n "${TARGET_ARCH:-}" ] && [ "$TARGET_ARCH" != "$(uname -m)" ]; then export ac_cv_host="$TARGET_ARCH-unknown-linux-gnu"; fi
./autogen.sh --prefix="$PREFIX" --enable-tools=no >&2
make -j"$(nproc)" >&2
make install >&2
echo "$PREFIX"
