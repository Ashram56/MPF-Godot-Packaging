#!/bin/bash
# Bootloader (QSPI) only, for when the NVMe is already written (step 7 of nvme-flash.sh).
# The board re-enumerates during the flash and usbipd re-attaches it a few seconds late, which shows as
# "USB communication failed" / "Cannot Open USB". So: build the flash package offline once, then run NVIDIA's
# saved flash command, waiting for the board to reappear and retrying (tegraflash resumes from the board's state).
#   sudo bash qspi-flash.sh
set -uo pipefail
source "$(dirname "$0")/nx-env.sh"
need_root
cd "$L4T" || die "no $L4T: run nvme-flash.sh first"

echo "== NVMe step result (last lines of direct-nvme.log)"
tail -5 "$D/direct-nvme.log" 2>/dev/null || echo "(no direct-nvme.log)"

echo "== 1. build the QSPI flash package offline (no board access needed)"
FUSELEVEL=fuselevel_production env $BOARD_ENV ./flash.sh --no-flash jetson-xavier-nx-devkit-qspi internal \
  2>&1 | tee "$D/qspi-build.log"
[ -s bootloader/flashcmd.txt ] || die "flashcmd.txt was not generated; see $D/qspi-build.log"
echo "flash command:"; cat bootloader/flashcmd.txt

pause "Put the Jetson in RECOVERY mode now (under WSL keep: usbipd attach --wsl --hardware-id 0955:7e19 --auto-attach)"
cd bootloader
for attempt in 1 2 3 4 5 6; do
  echo "== 2. flash attempt $attempt"
  wait_usb 0955:7e19 "recovery mode"
  sleep 2
  if bash ./flashcmd.txt 2>&1 | tee -a "$D/qspi-flash.log"; then
    echo "== DONE (tegraflash exited OK). Remove the recovery jumper and power-cycle the Jetson; it should boot from NVMe."
    exit 0
  fi
  echo "Attempt $attempt did not finish (board probably re-enumerated)."
  pause "Check usbipd re-attached the board (0955:7e19), then press Enter to resume"
done
die "Gave up after 6 attempts; see $D/qspi-flash.log"
