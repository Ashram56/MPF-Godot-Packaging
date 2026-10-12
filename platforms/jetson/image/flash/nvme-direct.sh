#!/bin/bash
# Re-run only the NVMe write (step 6 of nvme-flash.sh), then the QSPI write, for when the board is already
# in "initrd flashing mode" (0955:7035), e.g. after nvme-flash.sh stopped there.
# WSL's kernel has no rndis_host driver, so NVIDIA's initrd flash can't reach the board over USB network.
# Workaround: in that mode the board exposes its NVMe as a USB disk.
#   Part 1 writes the NVMe through that disk (NVIDIA's --direct mode, README_initrd_flash "Workflow 12").
#   Part 2 writes the QSPI bootloader (same as qspi-flash.sh: offline package, waits and retries).
#   sudo bash nvme-direct.sh
set -uo pipefail
source "$(dirname "$0")/nx-env.sh"
need_root
cd "$L4T" || die "no $L4T: run nvme-flash.sh first (it prepares the BSP and images)"

echo "== Part 1: NVMe through the USB disk exposed by the board"
wait_usb 0955:7035 "initrd flashing mode"
lsblk -o NAME,SIZE,TRAN,MODEL
# The board's disks are the USB ones; mmc0/mmc0boot0/mmc0boot1 are 0 bytes (no SD/eMMC), the NVMe is the only
# non-empty one. Its model string is "0", so match on transport + size.
CANDS=$(lsblk -dbno NAME,SIZE,TRAN | awk '$3=="usb" && $2>1000000000 {print $1}')
[ "$(echo "$CANDS" | grep -c .)" = 1 ] || die "Expected exactly one non-empty USB disk, found: '$CANDS'. Detach other USB drives from WSL and retry."
DEV=$CANDS
echo "Board NVMe is /dev/$DEV ($(lsblk -dno SIZE /dev/$DEV)). It will be ERASED."
read -rp ">>> Type YES to write the NVMe: " ok; [ "$ok" = YES ] || die "aborted"
env $BOARD_ENV ./tools/kernel_flash/l4t_initrd_flash.sh --direct "$DEV" \
  -c ./tools/kernel_flash/flash_l4t_external.xml \
  --external-device nvme0n1p1 \
  jetson-xavier-nx-devkit external 2>&1 | tee "$D/direct-nvme.log" || die "NVMe write failed; see $D/direct-nvme.log"
sync
echo "NVMe written."

echo "== Part 2: QSPI bootloader"
exec bash "$FLASH_DIR/qspi-flash.sh"
