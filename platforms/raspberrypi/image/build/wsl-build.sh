#!/usr/bin/env bash
# One command to build the Raspberry Pi 4 image from a WSL2 or Linux host: installs the host packages
# (debootstrap and arm64 emulation, qemu-user-static or qemu-user-binfmt), then runs build-native.sh.
#   sudo bash wsl-build.sh            # work folder: ~/pi4-build of the user who ran sudo
# Variables of build-native.sh (EXTRAS, WIFI_SSID, ...) pass through.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo bash $0"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)"
export WORK="${WORK:-$HOME_DIR/pi4-build}"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq debootstrap debian-archive-keyring gpg curl
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq qemu-user-static binfmt-support 2>/dev/null \
    || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq qemu-user qemu-user-binfmt
ls /proc/sys/fs/binfmt_misc/ | grep -q aarch64 || { echo "qemu-aarch64 is not registered in binfmt_misc"; exit 1; }
exec bash "$HERE/build-native.sh"
