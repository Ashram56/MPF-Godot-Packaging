#!/usr/bin/env bash
# Copy the running system (booted from a USB stick) to an internal disk and make that disk bootable.
#   sudo mpf-install-to-disk /dev/sda              # asks before erasing; lsblk shows the disks
#   sudo mpf-install-to-disk /dev/nvme0n1 --yes
# The whole disk is erased (Windows included). Read-only image (/etc/mpf-readonly.conf): the root partition is the size of
# the system plus room for a maintenance session, and the rest of the disk is the read/write data partition (settings,
# scores, games); an ordinary image: the root partition fills the disk. UEFI only: the firmware boot entry is
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
READONLY=0; [ -f /etc/mpf-readonly.conf ] && READONLY=1
if [ "$READONLY" = 1 ]; then
    [ -r /etc/mpf-readonly.conf ] && . /etc/mpf-readonly.conf
    # the system as it is (the lower layer: the data partition's binds hide nothing that matters) plus room to work in maintenance mode
    USED_MB=$(df -BM --output=used / | tail -1 | tr -dc 0-9)
    ROOT_MB=$(( USED_MB + 1536 ))
    DISK_MB=$(( $(blockdev --getsize64 "$DISK") / 1048576 ))
    [ $(( DISK_MB - ESP_MB - ROOT_MB )) -ge "${MPF_DATA_MIN_MB:-512}" ] || { echo "$DISK is too small: $ROOT_MB MB system + $ESP_MB MB boot + ${MPF_DATA_MIN_MB:-512} MB data"; exit 1; }
    printf 'label: gpt\n\nsize=%sMiB, type=U, name="firmware"\nsize=%sMiB, type=L, name="rootfs"\ntype=L, name="data"\n' "$ESP_MB" "$ROOT_MB" | sfdisk -q "$DISK"
else
    printf 'label: gpt\n\nsize=%sMiB, type=U, name="firmware"\ntype=L, name="rootfs"\n' "$ESP_MB" | sfdisk -q "$DISK"
fi
partprobe "$DISK"; udevadm settle; sleep 1
mkfs.vfat -F 32 -n mpfesp "$(p 1)" >/dev/null   # labels differ from the stick's (firmware, rootfs): never two of a kind
mkfs.ext4 -q -F -L mpfroot "$(p 2)"   # not "rootfs": the USB stick keeps that label, and two disks must not share one
[ "$READONLY" = 1 ] && mkfs.ext4 -q -F -L "${MPF_DATA_LABEL:-mpfdata}" -m 0 "$(p 3)"   # empty: mpf-persist seeds it at the first boot
T="$(mktemp -d)"; mount "$(p 2)" "$T"; mkdir -p "$T/boot/efi"; mount "$(p 1)" "$T/boot/efi"
echo "Copying the system (a few minutes)..."
# Copy the system as the image was built, not the stick's current state: a bind mount of / (not recursive) shows the folders
# under the persistent binds (/etc/ssh, /opt/games...) and under the RAM disks as the image has them.
SRC="$(mktemp -d)"; mount --bind / "$SRC"
rsync -aHAX --info=progress2 --exclude='/proc/*' --exclude='/sys/*' --exclude='/dev/*' --exclude='/run/*' --exclude='/tmp/*' \
    --exclude='/mnt/*' --exclude='/media/*' --exclude='/boot/efi/*' --exclude='/lost+found' --exclude='/data/*' "$SRC/" "$T/"
umount "$SRC"; rmdir "$SRC"
rsync -rt /boot/efi/ "$T/boot/efi/"        # bootloaders, mpf-network.txt
if [ "$READONLY" = 1 ] && [ -d /data ]; then
    # Games put on the stick (common/games/inject_image.py, or installed from the page): bundles still in the inbox and the installed
    # games go along; they are installed or seen by the first boot of the disk.
    D="$(mktemp -d)"; mount "$(p 3)" "$D"
    if [ -d /data/inbox ]; then mkdir -p "$D/inbox"; rsync -a /data/inbox/ "$D/inbox/"; fi
    if [ -d /data/persist/games ]; then mkdir -p "$D/persist/games"; rsync -a /data/persist/games/ "$D/persist/games/"; fi
    [ -d /data/mpf ] && { mkdir -p "$D/mpf"; rsync -a --exclude='maintenance' /data/mpf/ "$D/mpf/"; }
    sync; umount "$D"; rmdir "$D"
fi
mkdir -p "$T"/{proc,sys,dev,run,tmp,mnt,media}; chmod 1777 "$T/tmp"
# the copy boots from its own label (its loader is mpf-disk.efi, which looks for mpfroot), and grows its root partition
sed -i -e 's/^LABEL=rootfs /LABEL=mpfroot /' -e 's/^LABEL=firmware /LABEL=mpfesp /' "$T/etc/fstab"
cp /boot/efi/EFI/BOOT/mpf-disk.efi "$T/boot/efi/EFI/BOOT/BOOTX64.EFI"   # the loader that looks for the label mpfroot
if [ "$READONLY" != 1 ]; then
    mkdir -p "$T/etc/systemd/system/multi-user.target.wants"
    ln -sf /etc/systemd/system/resizerootfs.service "$T/etc/systemd/system/multi-user.target.wants/resizerootfs.service"
fi
if command -v efibootmgr >/dev/null && [ -d /sys/firmware/efi ]; then
    efibootmgr -c -d "$DISK" -p 1 -L "MPF" -l '\EFI\BOOT\BOOTX64.EFI' >/dev/null 2>&1 || true
fi
sync; umount "$T/boot/efi" "$T"; rmdir "$T"
echo "Done. Shut down, remove the USB stick, power on: the system starts from $DISK."
if [ "$READONLY" = 1 ]; then echo "Production mode: the system is read-only; settings, scores and games are on the data partition (p3). Wi-Fi and SSH keys of the stick are not copied: set them up again on the PC (mpf-network.txt, or the page on port 8080)."
else echo "The disk's root partition grows to fill it at the first boot."; fi
