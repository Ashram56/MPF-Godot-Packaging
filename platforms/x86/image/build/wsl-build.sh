#!/usr/bin/env bash
# One command to build the x86_64 (UEFI) image from a WSL2 or Linux x86_64 host: installs the host packages, then runs
# build-native.sh. No emulation: the image is the same architecture as the host.
#   sudo bash wsl-build.sh            # work folder: ~/x86-build of the user who ran sudo
# Variables of build-native.sh (EXTRAS, WIFI_SSID, ...) pass through.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo bash $0"; exit 1; }
[ "$(uname -m)" = x86_64 ] || { echo "this image is built on an x86_64 host"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)"
export WORK="${WORK:-$HOME_DIR/x86-build}"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq debootstrap debian-archive-keyring gpg curl git \
    e2fsprogs dosfstools mtools fdisk xz-utils grub-efi-amd64-bin grub-common console-setup
exec bash "$HERE/build-native.sh"
