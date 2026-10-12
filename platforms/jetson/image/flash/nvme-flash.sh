#!/bin/bash
# Guided flash of the minimal Xavier NX image (L4T 35.6.4) to an NVMe SSD + the module's QSPI bootloader.
# Works from WSL2 (usbipd) and from a native Linux host. No SD card needed.
# Pauses before every point where the Jetson re-enumerates on USB, so you can check it is (re)attached.
#
#   sudo bash nvme-deps.sh                                   # once
#   sudo IMG=/path/to/jetson-xavier-nx-l4t35.6.4-sd.img.xz bash nvme-flash.sh
#
# IMG may also be the first split part (...img.xz.part0) or a raw .img. See nx-env.sh for WORKDIR / BOARD_ENV.
# Logs: $WORKDIR/flash-A.log, flash-B.log (image generation), flash-C.log (initrd boot),
#       direct-nvme.log (NVMe write), qspi-build.log / qspi-flash.log (bootloader).
set -uo pipefail
source "$(dirname "$0")/nx-env.sh"
need_root
mkdir -p "$D"; cd "$D" || die "no $D"

echo "== 0. inputs (image + NVIDIA BSP) in $D"
prepare_image
prepare_bsp

echo "== 1. extract BSP"
[ -d "$L4T" ] || tar xpf "bsp/$BSP_TBZ" || die "BSP extract failed"

echo "== 2. copy our rootfs (APP partition of nx.img) into the BSP"
# No apply_binaries.sh: the L4T debs are already installed in the image's rootfs.
mkdir -p /mnt/nxapp
OFF=$(app_offset)
mountpoint -q /mnt/nxapp || mount -o loop,ro,offset=$((OFF*512)) img/nx.img /mnt/nxapp || die "mount failed (offset $OFF)"
rm -rf "$L4T"/rootfs/*
cp -a /mnt/nxapp/. "$L4T"/rootfs/ || die "rootfs copy failed"
umount /mnt/nxapp
head -1 "$L4T"/rootfs/etc/nv_tegra_release   # expect: R35 (release), REVISION: 6.4

echo "== 3. host fixes"
command -v ssh-keygen >/dev/null || apt-get install -y openssh-client
ssh -V 2>&1 | sed 's/^/   /'
# Newer OpenSSH removed DSA keys; NVIDIA's recovery-image script still makes one (unused) and aborts with
# "command is failed", followed by "bootloader/signed/flash.idx is not found".
sed -i '/ssh-keygen -t dsa/d' "$L4T"/tools/ota_tools/version_upgrade/ota_make_recovery_img_dtb.sh
cd "$L4T"
./tools/l4t_flash_prerequisites.sh >/dev/null 2>&1 || echo "   (prerequisites script reported problems; continuing)"
modprobe -a cdc_ether cdc_ncm rndis_host usb_storage 2>/dev/null || true

echo "== 4. generate images offline (board not needed, no reconnects)"
# NVIDIA README_initrd_flash.txt, "Example 2" (Xavier NX SD module: QSPI + external NVMe). The QSPI config is
# taken from the board conf: there is no flash_t194_qspi_p3668.xml in R35.6.4, so never pass -c for it.
env $BOARD_ENV ./tools/kernel_flash/l4t_initrd_flash.sh --no-flash jetson-xavier-nx-devkit-qspi internal \
  > "$D/flash-A.log" 2>&1 || die "QSPI image generation failed; see $D/flash-A.log"
env $BOARD_ENV ./tools/kernel_flash/l4t_initrd_flash.sh --no-flash \
  --external-device nvme0n1p1 -c ./tools/kernel_flash/flash_l4t_external.xml \
  --external-only --append jetson-xavier-nx-devkit external \
  > "$D/flash-B.log" 2>&1 || die "NVMe image generation failed; see $D/flash-B.log"
echo "   images generated"

echo "== 5. boot the board into initrd flashing mode"
pause "Put the Jetson in RECOVERY mode (jumper FC REC-GND, power on)"
wait_usb 0955:7e19 "recovery mode"
echo "   The board will now boot NVIDIA's flashing initrd and come back as 0955:7035."
echo "   Native Linux: this step flashes the QSPI and the NVMe over USB networking and the script ends here."
echo "   WSL: this step ends with an ssh 'Timeout' (the WSL kernel has no rndis_host). That is expected."
if ./tools/kernel_flash/l4t_initrd_flash.sh --flash-only --showlogs 2>&1 | tee "$D/flash-C.log" \
   && ! grep -q "Timeout" "$D/flash-C.log"; then
  echo
  echo "== DONE (initrd flash completed). Remove the recovery jumper and power-cycle. Login: jetson / jetson"
  exit 0
fi
echo "   step finished ($(tail -1 "$D/flash-C.log")); continuing with the WSL path"

echo "== 6. write the NVMe through the USB disk the board exposes"
pause "The board should now show in Windows as 'Jetson device in initrd flashing mode' (0955:7035). Make sure usbipd attached it to WSL"
wait_usb 0955:7035 "initrd flashing mode"
while :; do
  # The board exposes several USB disks; mmc0/mmc0boot* are 0 bytes, the NVMe is the only non-empty one.
  # (Its model string is just "0", so match on transport + size, not on the name.)
  CANDS=$(lsblk -dbno NAME,SIZE,TRAN | awk '$3=="usb" && $2>1000000000 {print $1}')
  [ "$(echo "$CANDS" | grep -c .)" = 1 ] && break
  lsblk -o NAME,SIZE,TRAN,MODEL
  echo "   Expected exactly one non-empty USB disk (the board's NVMe), found: '$CANDS'."
  pause "Wait a few seconds for the disk to appear (or detach other USB drives), then press Enter"
done
DEV=$CANDS
echo "   Board NVMe is /dev/$DEV ($(lsblk -dno SIZE /dev/$DEV)). It will be ERASED."
read -rp ">>> Type YES to write the NVMe: " ok; [ "$ok" = YES ] || die "aborted"
env $BOARD_ENV ./tools/kernel_flash/l4t_initrd_flash.sh --direct "$DEV" \
  -c ./tools/kernel_flash/flash_l4t_external.xml --external-device nvme0n1p1 \
  jetson-xavier-nx-devkit external 2>&1 | tee "$D/direct-nvme.log" || die "NVMe write failed; see $D/direct-nvme.log"
sync
echo "   NVMe written."

echo "== 7. write the QSPI bootloader over USB recovery"
FUSELEVEL=fuselevel_production env $BOARD_ENV ./flash.sh --no-flash jetson-xavier-nx-devkit-qspi internal \
  > "$D/qspi-build.log" 2>&1
[ -s bootloader/flashcmd.txt ] || die "QSPI package not generated; see $D/qspi-build.log"
pause "Put the Jetson in RECOVERY mode again (power off, jumper on, power on)"
cd bootloader
for attempt in 1 2 3 4 5 6; do
  wait_usb 0955:7e19 "recovery mode"
  echo "   flash attempt $attempt (the board re-enumerates during this; if it stops, re-attach and retry)"
  if bash ./flashcmd.txt 2>&1 | tee -a "$D/qspi-flash.log"; then
    echo
    echo "== DONE. Remove the recovery jumper and power-cycle the Jetson. Login: jetson / jetson"
    exit 0
  fi
  echo "   Attempt $attempt stopped, most likely because the board reconnected and usbipd hasn't re-attached it yet."
  pause "Check usbipd re-attached the board (0955:7e19), then press Enter to resume from where it stopped"
done
die "QSPI flash gave up after 6 attempts; see $D/qspi-flash.log"
