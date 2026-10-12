#!/bin/bash
# Write the delivered image to an SD card from Linux (native, or WSL with the card reader attached via usbipd).
#   sudo bash sd-flash.sh /path/to/jetson-xavier-nx-l4t35.6.4-sd.img.xz /dev/sdX
# The .img.xz can also be the first split part (...img.xz.part0); parts are streamed in order.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
SRC=${1:?image (.img.xz or .part0)}; DEV=${2:?target disk, e.g. /dev/sdX}
[ -b "$DEV" ] || { echo "$DEV is not a block device"; exit 1; }
case "$SRC" in
  *.part0) mapfile -t PARTS < <(ls -1 "${SRC%.part0}".part* | sort -V); BASE="${SRC%.part0}" ;;
  *) PARTS=("$SRC"); BASE="$SRC" ;;
esac
if [ -e "$BASE.sha256" ]; then
  echo "== checking sha256"
  [ "$(cat "${PARTS[@]}" | sha256sum | cut -d' ' -f1)" = "$(cut -d' ' -f1 "$BASE.sha256")" ] || { echo "sha256 mismatch"; exit 1; }
fi
lsblk -o NAME,SIZE,TRAN,MODEL "$DEV"
read -rp ">>> $DEV ($(lsblk -dno SIZE "$DEV")) will be ERASED. Type YES: " ok; [ "$ok" = YES ] || exit 1
for p in $(lsblk -lno NAME "$DEV" | tail -n +2); do umount "/dev/$p" 2>/dev/null || true; done
cat "${PARTS[@]}" | xz -dc | dd of="$DEV" bs=4M conv=fsync status=progress
sync
echo "== DONE. Put the card in the Jetson and power on. Login: jetson / jetson (the root partition grows on first boot)"
