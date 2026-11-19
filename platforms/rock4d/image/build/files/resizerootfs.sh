#!/usr/bin/env bash
# Grow the root partition (the last one) and its ext4 filesystem to fill the card. Runs once, at first boot.
set -euo pipefail
rootpart="$(findmnt -n -o SOURCE /)"
rootdevice="/dev/$(lsblk -no pkname "$rootpart")"
partnum="${rootpart##*[!0-9]}"
echo ", +" | sfdisk -f -N "$partnum" "$rootdevice"
partprobe "$rootdevice" || true
resize2fs "$rootpart"
systemctl disable resizerootfs.service || true
