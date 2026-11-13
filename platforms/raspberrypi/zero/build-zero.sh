#!/usr/bin/env bash
# Build the topper image for a Raspberry Pi Zero W (ARMv6): the official Raspberry Pi OS Lite 32-bit image (Raspbian trixie
# armhf: the only Raspberry Pi OS userland that runs on an ARMv6 core) plus mpv and the pup-topper agent. No video is in
# the image: the Pi downloads them from the game (platforms/pup-remote-topper.md). Wi-Fi, hostname and password are
# set in files on the boot partition (cloud-init: user-data, network-config) and the agent's settings in pup-topper.cfg;
# nothing is installed or generated on the Pi.
#
# Run as root on an x86_64 Linux host or WSL2 (about 8 GB free, 10 to 20 minutes). The host needs Internet access to
# downloads.raspberrypi.com (the base image) and to the Raspbian package mirrors (raspbian.raspberrypi.com redirects to
# them) for the one `apt-get install mpv` done in the image:
#   sudo bash platforms/raspberrypi/zero/build-zero.sh
# Optional environment:
#   WORK=/path     work folder (default ./work-zero, in the Linux home under WSL, never /mnt/c)
#   APT_MIRROR=URL Raspbian mirror to use instead of raspbian.raspberrypi.com, which is plain HTTP only: for a build host that
#                  only allows HTTPS (e.g. a sandbox behind a proxy), https://mirror.ox.ac.uk/sites/archive.raspbian.org/archive/raspbian/
#   APT_PROXY=URL  HTTPS proxy for apt in the image (with APT_CA=/path/ca-bundle.crt when the proxy re-signs TLS)
#   BASE_IMAGE=URL base image (default: the pinned one below); BASE_SHA256=... its checksum (default: read from the
#                  .sha256 next to it on the same server)
# Output: $WORK/out/rpi-zero-topper.img.xz and .sha256 (flash it with Raspberry Pi Imager, "Use custom", or dd)
set -euo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$KIT/../../.." && pwd)"
WORK="${WORK:-$PWD/work-zero}"
BASE_IMAGE="${BASE_IMAGE:-http://downloads.raspberrypi.com/raspios_lite_armhf/images/raspios_lite_armhf-2026-10-06/2026-10-06-raspios-trixie-armhf-lite.img.xz}"
OUT="$WORK/out"; MNT="$WORK/mnt"; IMG="$WORK/base.img"
export MTOOLS_SKIP_CHECK=1

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
in_chroot() { LC_ALL=C DEBIAN_FRONTEND=noninteractive chroot "$MNT" /usr/bin/env bash -c "$*"; }
cleanup() {
    for m in dev/pts dev sys proc; do mountpoint -q "$MNT/$m" && { umount "$MNT/$m" || umount -l "$MNT/$m"; }; done
    mountpoint -q "$MNT" && umount "$MNT" || true
    rm -f "$MNT/usr/bin/qemu-arm-static" 2>/dev/null || true
}
trap cleanup EXIT

[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
mkdir -p "$WORK" "$OUT" "$MNT"

log "1/6 Host packages and ARM emulation"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl xz-utils e2fsprogs mtools fdisk >/dev/null
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq qemu-user-static binfmt-support >/dev/null 2>&1 \
    || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq qemu-user qemu-user-binfmt >/dev/null
mountpoint -q /proc/sys/fs/binfmt_misc || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
[ -e /proc/sys/fs/binfmt_misc/qemu-arm ] || cat /usr/lib/binfmt.d/qemu-arm.conf > /proc/sys/fs/binfmt_misc/register
[ -e /proc/sys/fs/binfmt_misc/qemu-arm ] || { echo "qemu-arm is not registered in binfmt_misc"; exit 1; }

log "2/6 Base image: Raspberry Pi OS Lite 32-bit"
if [ ! -s "$WORK/base.img.xz" ]; then
    curl -fL --retry 3 -o "$WORK/base.img.xz.part" "$BASE_IMAGE"; mv "$WORK/base.img.xz.part" "$WORK/base.img.xz"
fi
SUM="${BASE_SHA256:-$(curl -fsSL "$BASE_IMAGE.sha256" | cut -d' ' -f1)}"
echo "$SUM  $WORK/base.img.xz" | sha256sum -c -
xz -dkc "$WORK/base.img.xz" > "$IMG"
# partitions: 1 = FAT boot, 2 = ext4 root (read from the table; no loop partition nodes needed, offsets are enough)
eval "$(sfdisk -d "$IMG" | python3 -c '
import re, sys
parts = [dict(re.findall(r"(start|size)=\s*(\d+)", l)) for l in sys.stdin if "start=" in l]
print("B_START=%s B_SECT=%s R_START=%s" % (parts[0]["start"], parts[0]["size"], parts[1]["start"]))')"
echo "boot at sector $B_START ($B_SECT sectors), root at sector $R_START"

log "3/6 Root file system: mpv and the agent"
# room for mpv and its libraries (about 200 MB): grow the file, then the file system, before mounting
truncate -s +600M "$IMG"
# the root partition is the last one: extend its table entry to the end of the file
sfdisk -q --no-reread -N 2 "$IMG" <<< "$R_START,$(( $(stat -c %s "$IMG") / 512 - R_START ))"
LOOP="$(losetup -f --show -o $((R_START*512)) "$IMG")"
e2fsck -fy "$LOOP" >/dev/null || true
resize2fs "$LOOP" >/dev/null
losetup -d "$LOOP"
mount -o loop,offset=$((R_START*512)) "$IMG" "$MNT"
cp "$(command -v qemu-arm-static)" "$MNT/usr/bin/"
mountpoint -q "$MNT/proc" || mount -t proc proc "$MNT/proc"
mountpoint -q "$MNT/sys" || mount -t sysfs sys "$MNT/sys"
mountpoint -q "$MNT/dev" || { mount -o bind /dev "$MNT/dev"; mount --make-rslave "$MNT/dev"; }
mountpoint -q "$MNT/dev/pts" || { mount -o bind /dev/pts "$MNT/dev/pts"; mount --make-rslave "$MNT/dev/pts"; }
mv "$MNT/etc/resolv.conf" "$MNT/etc/resolv.conf.build-bak" 2>/dev/null || true
cp -L /etc/resolv.conf "$MNT/etc/resolv.conf"
printf '#!/bin/sh\nexit 101\n' > "$MNT/usr/sbin/policy-rc.d"; chmod 755 "$MNT/usr/sbin/policy-rc.d"
# the Pi's memcpy preload is for the real CPU: under emulation it only prints errors
[ -f "$MNT/etc/ld.so.preload" ] && mv "$MNT/etc/ld.so.preload" "$MNT/etc/ld.so.preload.build-bak"
if [ -n "${APT_MIRROR:-}" ] || [ -n "${APT_PROXY:-}" ]; then
    for f in "$MNT"/etc/apt/sources.list.d/*.sources "$MNT"/etc/apt/sources.list; do
        [ -f "$f" ] || continue
        [ -n "${APT_MIRROR:-}" ] && sed -i "s#http://raspbian.raspberrypi.com/raspbian/#${APT_MIRROR%/}/#" "$f"
        sed -i "s#http://archive.raspberrypi.com/#https://archive.raspberrypi.com/#" "$f"
    done
    [ -n "${APT_PROXY:-}" ] && echo "Acquire::https::Proxy \"$APT_PROXY\";" > "$MNT/etc/apt/apt.conf.d/99build-proxy"
    [ -n "${APT_CA:-}" ] && { cp "$APT_CA" "$MNT/usr/local/share/build-ca.crt"; echo 'Acquire::https::CaInfo "/usr/local/share/build-ca.crt";' >> "$MNT/etc/apt/apt.conf.d/99build-proxy"; }
fi
if [ -z "${SKIP_PACKAGES:-}" ]; then   # SKIP_PACKAGES=1: the build test without the Raspbian mirrors (no mpv in the result)
    in_chroot "apt-get update -qq"
    in_chroot "apt-get install -y -qq --no-install-recommends mpv python3 libdrm2 libgbm1 libegl1 libgles2 libv4l-0t64"
    in_chroot "mpv --version | head -1"
    in_chroot "apt-get clean; rm -rf /var/lib/apt/lists/*"
fi

log "4/6 The agent and its service"
install -d "$MNT/opt/pup-topper"
install -m 644 "$REPO/mpf_godot/pup_remote/topper/topper.py" "$REPO/mpf_godot/pup_remote/screen_rules.py" "$MNT/opt/pup-topper/"
install -m 644 "$KIT/files/pup-topper.service" "$MNT/etc/systemd/system/pup-topper.service"
in_chroot "systemctl enable pup-topper.service ssh >/dev/null 2>&1"
# a topper needs none of these on a 512 MB single core
in_chroot "systemctl disable userconfig.service rpi-eeprom-update.service bluetooth.service hciuart.service triggerhappy.service apt-daily.timer apt-daily-upgrade.timer man-db.timer >/dev/null 2>&1 || true"
in_chroot "python3 -m py_compile /opt/pup-topper/topper.py /opt/pup-topper/screen_rules.py && rm -rf /opt/pup-topper/__pycache__"
[ -f "$MNT/etc/ld.so.preload.build-bak" ] && mv "$MNT/etc/ld.so.preload.build-bak" "$MNT/etc/ld.so.preload"
mv -f "$MNT/etc/resolv.conf.build-bak" "$MNT/etc/resolv.conf" 2>/dev/null || true
rm -f "$MNT/usr/sbin/policy-rc.d" "$MNT/usr/bin/qemu-arm-static" "$MNT/etc/apt/apt.conf.d/99build-proxy" "$MNT/usr/local/share/build-ca.crt"
# the image's own sources go back to the Raspberry Pi hosts (the Pi has plain HTTP access)
sed -i "s#https://archive.raspberrypi.com/#http://archive.raspberrypi.com/#" "$MNT"/etc/apt/sources.list.d/*.sources 2>/dev/null || true
[ -n "${APT_MIRROR:-}" ] && sed -i "s#${APT_MIRROR%/}/#http://raspbian.raspberrypi.com/raspbian/#" "$MNT"/etc/apt/sources.list.d/*.sources 2>/dev/null || true
LC_ALL=C chroot "$MNT" /usr/bin/dpkg-query -W -f='${Package}\t${Version}\n' > "$OUT/packages-zero.tsv" 2>/dev/null || true
cleanup; trap - EXIT

log "5/6 Boot partition: Wi-Fi, hostname, agent settings (no loop device: mtools)"
BOOT="$IMG@@$((B_START*512))"
mcopy -o -i "$BOOT" "$KIT/files/user-data" ::user-data
mcopy -o -i "$BOOT" "$KIT/files/network-config" ::network-config
sed "s#^media=.*#media=/var/lib/pup-topper/media#" "$REPO/mpf_godot/pup_remote/topper/pup-topper.cfg" > "$WORK/pup-topper.cfg"
mcopy -o -i "$BOOT" "$WORK/pup-topper.cfg" ::pup-topper.cfg
# USB link (the Zero's micro-USB data port to a USB port of the game computer): Ethernet gadget with fixed MACs, so the
# game computer can recognise it (host/usb-link-host.sh); the Zero is 10.55.0.2 (network-config), the game computer 10.55.0.1
mtype -i "$BOOT" ::cmdline.txt | tr -d '\r\n' > "$WORK/cmdline.txt"
grep -q 'g_ether' "$WORK/cmdline.txt" || \
    printf ' modules-load=dwc2,g_ether g_ether.host_addr=02:70:75:70:00:01 g_ether.dev_addr=02:70:75:70:00:02\n' >> "$WORK/cmdline.txt"
mcopy -o -i "$BOOT" "$WORK/cmdline.txt" ::cmdline.txt
sed -i "s#^host=.*#host=10.55.0.1#" "$WORK/pup-topper.cfg"; mcopy -o -i "$BOOT" "$WORK/pup-topper.cfg" ::pup-topper.cfg
# Zero W: the GPU needs memory for the H.264 decoder; no Bluetooth (frees the UART and a core's time)
mtype -i "$BOOT" ::config.txt > "$WORK/config.txt"
grep -q '^gpu_mem=' "$WORK/config.txt" || printf '\n[all]\ngpu_mem=96\ndtoverlay=disable-bt\ndtoverlay=dwc2,dr_mode=peripheral\n' >> "$WORK/config.txt"
mcopy -o -i "$BOOT" "$WORK/config.txt" ::config.txt

log "6/6 Compress"
mv "$IMG" "$OUT/rpi-zero-topper.img"
cd "$OUT" && xz -T0 -6 -f rpi-zero-topper.img && sha256sum rpi-zero-topper.img.xz | tee rpi-zero-topper.img.xz.sha256
