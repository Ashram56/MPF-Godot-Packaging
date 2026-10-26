#!/usr/bin/env bash
# Copy the running system (booted from a USB stick) to an internal disk and make that disk bootable.
#   sudo mpf-install-to-disk /dev/sda              # asks before erasing; lsblk shows the disks
#   sudo mpf-install-to-disk /dev/nvme0n1 --yes
# The whole disk is erased (Windows included). The root partition fills the disk. UEFI only: the firmware boot entry is
# added with efibootmgr when it can; the removable-media path (EFI/BOOT/BOOTX64.EFI) always works.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root: sudo $0 DISK"; exit 1; }
DISK="${1:-}"; YES="${2:-}"
[ -b "$DISK" ] || { echo "usage: $0 DISK [--yes]   (DISK: a whole disk such as /dev/sda or /dev/nvme0n1)"; lsblk -dpno NAME,SIZE,MODEL,TRAN; exit 1; }
[ "$(lsblk -dno TYPE "$DISK")" = disk ] || { echo "$DISK is not a whole disk"; exit 1; }
SRC_ROOT="$(findmnt -n -o SOURCE /)"; SRC_DISK="/dev/$(lsblk -no pkname "$SRC_ROOT")"
[ "$DISK" != "$SRC_DISK" ] || { echo "$DISK is the disk this system runs from"; exit 1; }
ESP_MB=256
echo "This ERASES $DISK:"; lsblk -po NAME,SIZE,FSTYPE,LABEL,MODEL "$DISK"
if [ "$YES" != --yes ]; then read -r -p "Type the disk name again to continue: " a; [ "$a" = "$DISK" ] || { echo "cancelled"; exit 1; }; fi
p() { case "$DISK" in *[0-9]) echo "${DISK}p$1";; *) echo "${DISK}$1";; esac; }
for m in $(lsblk -lnpo NAME,MOUNTPOINT "$DISK" | awk '$2 {print $2}'); do umount "$m"; done
wipefs -a "$DISK" >/dev/null
printf 'label: gpt\n\nsize=%sMiB, type=U, name="firmware"\ntype=L, name="rootfs"\n' "$ESP_MB" | sfdisk -q "$DISK"
partprobe "$DISK"; udevadm settle; sleep 1
mkfs.vfat -F 32 -n mpfesp "$(p 1)" >/dev/null   # labels differ from the stick's (firmware, rootfs): never two of a kind
mkfs.ext4 -q -F -L mpfroot "$(p 2)"   # not "rootfs": the USB stick keeps that label, and two disks must not share one
T="$(mktemp -d)"; mount "$(p 2)" "$T"; mkdir -p "$T/boot/efi"; mount "$(p 1)" "$T/boot/efi"
echo "Copying the system (a few minutes)..."
rsync -aHAX --info=progress2 --exclude='/proc/*' --exclude='/sys/*' --exclude='/dev/*' --exclude='/run/*' --exclude='/tmp/*' \
    --exclude='/mnt/*' --exclude='/media/*' --exclude='/boot/efi/*' --exclude='/lost+found' / "$T/"
rsync -rt /boot/efi/ "$T/boot/efi/"        # bootloader (EFI/BOOT/BOOTX64.EFI), mpf-network.txt
mkdir -p "$T"/{proc,sys,dev,run,tmp,mnt,media}; chmod 1777 "$T/tmp"
# the copy boots from its own label (the loader reads EFI/BOOT/mpf-boot.cfg on its ESP), and grows its root partition
sed -i -e 's/^LABEL=rootfs /LABEL=mpfroot /' -e 's/^LABEL=firmware /LABEL=mpfesp /' "$T/etc/fstab"
echo 'set rootlabel=mpfroot' > "$T/boot/efi/EFI/BOOT/mpf-boot.cfg"
mkdir -p "$T/etc/systemd/system/multi-user.target.wants"
ln -sf /etc/systemd/system/resizerootfs.service "$T/etc/systemd/system/multi-user.target.wants/resizerootfs.service"
if command -v efibootmgr >/dev/null && [ -d /sys/firmware/efi ]; then
    efibootmgr -c -d "$DISK" -p 1 -L "MPF" -l '\EFI\BOOT\BOOTX64.EFI' >/dev/null 2>&1 || true
fi
sync; umount "$T/boot/efi" "$T"; rmdir "$T"
echo "Done. Shut down, remove the USB stick, power on: the system starts from $DISK."
echo "The disk's root partition grows to fill it at the first boot."
