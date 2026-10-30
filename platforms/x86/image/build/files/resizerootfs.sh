#!/usr/bin/env bash
# Grow the root partition (the last one) and its ext4 filesystem to fill the disk. Runs once, at first boot.
# The image is written to a bigger disk than it was made for, so the GPT backup header is still in the middle of
# the disk: move it to the end first (sfdisk --relocate), or the partition cannot grow.
set -euo pipefail
rootpart="$(findmnt -n -o SOURCE /)"
rootdevice="/dev/$(lsblk -no pkname "$rootpart")"
partnum="${rootpart##*[!0-9]}"
sfdisk --relocate gpt-bak-std "$rootdevice" || true
echo ", +" | sfdisk -f -N "$partnum" "$rootdevice"
partprobe "$rootdevice" || true
resize2fs "$rootpart"
systemctl disable resizerootfs.service || true
