#!/usr/bin/env bash
# Build a minimal Raspberry Pi 4 SD card image (Debian 13 "trixie" arm64, Debian's own Raspberry Pi kernel and
# firmware packages) natively, without podman/docker and without loop devices. Same idea as the Jetson Xavier NX
# image (platforms/jetson/image), but much simpler: no vendor BSP, the Pi boots a stock Debian arm64 kernel.
#
# Run as root on an x86_64 Ubuntu 22.04+ host (WSL2 is fine) with ~15 GB free disk:
#   sudo ./build-native.sh            (or sudo bash wsl-build.sh, which also installs the host packages)
# Optional environment:
#   WORK=/path/to/workdir      (default: ./work; keep it in the Linux home under WSL, never /mnt/c)
#   PI_PASSWORD=...            password of user "pi" (default: raspberry)
#   WIFI_SSID=... WIFI_PSK=... pre-seed one Wi-Fi network (stored hashed via wpa_passphrase)
#   WIFI_COUNTRY=FR            regulatory country code for Wi-Fi
#   EXTRAS="video x11 mpf"     feature groups (default: all three; EXTRAS="" for the bare image)
#       video  : GStreamer + FFmpeg (software decode)
#       x11    : Xorg (modesetting), startx, openbox, xrandr, Mesa Vulkan (v3dv) and GL drivers
#       mpf    : MPF + Godot + GMC installed by install/install_linux.sh from this repository into
#                /home/pi/MPF-Godot; automatic login on tty1 and startx (needs video and x11, added when missing)
#   (Wi-Fi/SSH: edit mpf-network.txt on the boot partition, or use http://<ip>:8080; see common/netconfig/README.md)
#   ROOT_PAD_MB=1024           free space left in the root filesystem of the image (grown at first boot anyway)
# Output: $WORK/out/rpi4-debian13-sd.img.xz and .sha256

set -euo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$PWD/work}"
SUITE=trixie
MIRROR="http://deb.debian.org/debian"
IMG_NAME="rpi4-debian13-sd.img"
PI_PASSWORD="${PI_PASSWORD:-raspberry}"
EXTRAS="${EXTRAS-video x11 mpf}"
ROOT_PAD_MB="${ROOT_PAD_MB:-1024}"
FW_MB=256
REPO_ROOT="$(cd "$KIT/../../../.." && pwd)"

R="$WORK/rootfs"
FWDIR="$WORK/firmware"      # bind-mounted on $R/boot/firmware while packages install, then copied into the FAT partition
OUT="$WORK/out"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
in_chroot() { LC_ALL=C DEBIAN_FRONTEND=noninteractive chroot "$R" /usr/bin/env bash -c "$*"; }

mount_chroot() {
    mkdir -p "$R/boot/firmware" "$FWDIR"
    mountpoint -q "$R/proc" || mount -t proc proc "$R/proc"
    mountpoint -q "$R/sys" || mount -t sysfs sys "$R/sys"
    mountpoint -q "$R/dev" || { mount -o bind /dev "$R/dev"; mount --make-rslave "$R/dev"; }   # rslave: no mount propagation back (WSL2)
    mountpoint -q "$R/dev/pts" || mount -o bind /dev/pts "$R/dev/pts"
    mountpoint -q "$R/boot/firmware" || mount -o bind "$FWDIR" "$R/boot/firmware"
    if [ -L "$R/etc/resolv.conf" ] || [ -e "$R/etc/resolv.conf" ]; then
        mv "$R/etc/resolv.conf" "$R/etc/resolv.conf.build-bak"
    fi
    cp -L /etc/resolv.conf "$R/etc/resolv.conf"
    printf '#!/bin/sh\nexit 101\n' > "$R/usr/sbin/policy-rc.d"; chmod 755 "$R/usr/sbin/policy-rc.d"
}

umount_chroot() {
    rm -f "$R/usr/sbin/policy-rc.d"
    for m in boot/firmware dev/pts dev sys proc; do
        if mountpoint -q "$R/$m"; then umount "$R/$m" 2>/dev/null || umount -l "$R/$m"; fi
    done
    if [ -e "$R/etc/resolv.conf.build-bak" ] || [ -L "$R/etc/resolv.conf.build-bak" ]; then
        mv -f "$R/etc/resolv.conf.build-bak" "$R/etc/resolv.conf"
    fi
    return 0
}
trap 'umount_chroot || true' EXIT

[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
mkdir -p "$WORK" "$OUT"

##############################################################################
log "1/6 Host dependencies and arm64 emulation"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    debootstrap debian-archive-keyring curl gpg xz-utils e2fsprogs dosfstools mtools fdisk >/dev/null
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq qemu-user-static binfmt-support >/dev/null 2>&1 \
    || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq qemu-user qemu-user-binfmt >/dev/null
mountpoint -q /proc/sys/fs/binfmt_misc || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
if [ ! -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]; then
    update-binfmts --enable qemu-aarch64 2>/dev/null || cat /usr/lib/binfmt.d/qemu-aarch64.conf > /proc/sys/fs/binfmt_misc/register
fi

##############################################################################
log "2/6 Minimal Debian $SUITE arm64 rootfs"
if [ ! -x "$R/bin/bash" ]; then
    debootstrap --arch=arm64 --variant=minbase --include=ca-certificates "$SUITE" "$R" "$MIRROR"
fi
cat > "$R/etc/apt/sources.list" <<APT
deb $MIRROR $SUITE main contrib non-free non-free-firmware
deb $MIRROR $SUITE-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security $SUITE-security main contrib non-free non-free-firmware
APT
rm -f "$R/etc/apt/sources.list.d/debian.sources"
cat > "$R/etc/dpkg/dpkg.cfg.d/excludes" <<'DPKG'
path-exclude=/usr/share/doc/*
path-include=/usr/share/doc/*/copyright
path-exclude=/usr/share/man/*
path-exclude=/usr/share/info/*
path-exclude=/usr/share/locale/*
path-include=/usr/share/locale/locale.alias
DPKG
printf 'APT::Install-Recommends "false";\nAPT::Install-Suggests "false";\n' > "$R/etc/apt/apt.conf.d/99norecommends"

echo mpf-pi4 > "$R/etc/hostname"
printf '127.0.0.1\tlocalhost\n127.0.1.1\tmpf-pi4\n::1\tlocalhost ip6-localhost ip6-loopback\n' > "$R/etc/hosts"
printf 'LABEL=firmware /boot/firmware vfat defaults 0 2\nLABEL=rootfs / ext4 defaults,noatime 0 1\n' > "$R/etc/fstab"
# Kernel command line used by raspi-firmware to write cmdline.txt (eth0/wlan0 names, console on the screen)
mkdir -p "$R/etc/kernel"
echo "console=tty1 root=LABEL=rootfs rootfstype=ext4 rootwait fsck.repair=yes net.ifnames=0 quiet" > "$R/etc/kernel/cmdline"

# Raspberry Pi's own apt repository, for the Raspberry Pi kernel: only it has the V4L2 hardware video decoders of
# the Pi 4 (bcm2835-codec H.264, rpi-hevc-dec HEVC). Low priority, so Debian packages are never replaced.
mkdir -p "$R/usr/share/keyrings"
curl -fsSL https://archive.raspberrypi.com/debian/raspberrypi.gpg.key | gpg --dearmor > "$R/usr/share/keyrings/raspberrypi-archive-keyring.gpg"
echo "deb [signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.gpg] http://archive.raspberrypi.com/debian/ $SUITE main" > "$R/etc/apt/sources.list.d/raspi.list"
printf 'Package: *\nPin: origin archive.raspberrypi.com\nPin-Priority: 100\n' > "$R/etc/apt/preferences.d/raspi"
mount_chroot
in_chroot "apt-get update -qq && apt-get -y -qq upgrade"
# Kernel, Pi bootloader files and device trees (raspi-firmware fills /boot/firmware), Wi-Fi firmware
SYSTEM_PKGS="systemd systemd-sysv systemd-timesyncd systemd-resolved dbus udev kmod sudo locales openssh-server
  iproute2 iputils-ping curl nano parted fdisk e2fsprogs openssl less wpasupplicant iw rfkill wireless-regdb
  linux-image-rpi-v8 raspi-firmware firmware-brcm80211 initramfs-tools"
in_chroot "apt-get install -y -qq $SYSTEM_PKGS"
cat >> "$R/boot/firmware/config.txt" <<'CFG'

# MPF / Godot image
arm_64bit=1
dtoverlay=vc4-kms-v3d
max_framebuffers=2
disable_overscan=1
CFG

install -m 755 "$KIT/files/resizerootfs.sh" "$R/usr/local/bin/resizerootfs.sh"
install -m 644 "$KIT/files/resizerootfs.service" "$R/etc/systemd/system/resizerootfs.service"

in_chroot "sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen && locale-gen >/dev/null && update-locale LANG=en_US.UTF-8"

# Networking: systemd-networkd + resolved, wired preferred over Wi-Fi via route metric.
mkdir -p "$R/etc/systemd/network"
printf '[Match]\nName=eth* en*\n\n[Network]\nDHCP=yes\n\n[DHCP]\nRouteMetric=100\n' > "$R/etc/systemd/network/20-wired.network"
printf '[Match]\nName=wlan* wl*\n\n[Network]\nDHCP=yes\n\n[DHCP]\nRouteMetric=600\n' > "$R/etc/systemd/network/25-wireless.network"
ln -sf /run/systemd/resolve/stub-resolv.conf "$R/etc/resolv.conf.build-bak"   # becomes /etc/resolv.conf on unmount
# Wi-Fi: add networks later with
#   wpa_passphrase "SSID" "password" | sudo tee -a /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
#   sudo systemctl restart wpa_supplicant@wlan0
WPA="$R/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"
mkdir -p "$R/etc/wpa_supplicant"
{
    echo "ctrl_interface=DIR=/run/wpa_supplicant GROUP=sudo"
    echo "update_config=1"
    [ -n "${WIFI_COUNTRY:-}" ] && echo "country=${WIFI_COUNTRY}"
    if [ -n "${WIFI_SSID:-}" ] && [ -n "${WIFI_PSK:-}" ]; then
        in_chroot "wpa_passphrase '$WIFI_SSID' '$WIFI_PSK'" | grep -v '#psk='
    fi
} > "$WPA"
chmod 600 "$WPA"
in_chroot "systemctl enable resizerootfs.service systemd-timesyncd ssh systemd-networkd systemd-resolved wpa_supplicant@wlan0.service >/dev/null 2>&1"
in_chroot "systemctl disable wpa_supplicant.service >/dev/null 2>&1 || true"

# Wi-Fi / SSH setup shared with the other images (common/netconfig): text file on the boot partition read at
# every boot, setup web page on port 8080, access point "MPF-Setup" when no network comes up.
in_chroot "apt-get install -y -qq python3 hostapd dnsmasq-base"
in_chroot "systemctl disable hostapd >/dev/null 2>&1 || true; systemctl mask hostapd >/dev/null 2>&1 || true"
NC="$REPO_ROOT/common/netconfig"
install -m 755 "$NC/mpf_netconfig.py" "$R/usr/local/bin/mpf_netconfig.py"
install -m 644 "$NC"/mpf-netconfig-*.service "$R/etc/systemd/system/"
install -m 644 "$NC/mpf-network.txt.template" "$FWDIR/mpf-network.txt"
printf 'MPF_NETCONFIG_FILE=/boot/firmware/mpf-network.txt\nMPF_USER=pi\nMPF_WLAN=wlan0\n' > "$R/etc/default/mpf-netconfig"
in_chroot "systemctl enable mpf-netconfig-apply.service mpf-netconfig-web.service mpf-netconfig-ap.service >/dev/null 2>&1"

in_chroot "id pi >/dev/null 2>&1 || useradd --create-home -G sudo,video,audio,render,input,tty -p \"\$(openssl passwd -6 '$PI_PASSWORD')\" -s /bin/bash pi"

##############################################################################
log "3/6 Optional feature groups: ${EXTRAS:-none}"
has() { case " $EXTRAS " in *" $1 "*) return 0;; *) return 1;; esac; }
if [ -n "$EXTRAS" ]; then
    has mpf && ! has video && EXTRAS="$EXTRAS video"
    has mpf && ! has x11 && EXTRAS="$EXTRAS x11"
    if has video; then
        in_chroot "apt-get install -y -qq gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-alsa v4l-utils ffmpeg alsa-utils"
    fi
    if has x11; then
        in_chroot "apt-get install -y -qq xserver-xorg-core xserver-xorg-input-libinput xinit x11-xserver-utils xauth openbox xterm libpam-systemd \
            mesa-vulkan-drivers libgl1-mesa-dri libegl1 libvulkan1 libxcursor1 libxinerama1 libxrandr2 libxi6 libxext6 libxrender1 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3"
        printf 'allowed_users=console\nneeds_root_rights=auto\n' > "$R/etc/X11/Xwrapper.config"
        cat > "$R/home/pi/.xinitrc" <<'XRC'
#!/bin/sh
# Edit to taste. Extend the desktop across all connected outputs (HDMI-1 + HDMI-2), left to right:
prev=""
for out in $(xrandr | awk '/ connected/ {print $1}'); do
    if [ -z "$prev" ]; then xrandr --output "$out" --auto --primary; else xrandr --output "$out" --auto --right-of "$prev"; fi
    prev="$out"
done
exec openbox-session
XRC
        chmod 755 "$R/home/pi/.xinitrc"
    fi
    if has mpf; then
        # The repository's own Linux installer, run as the cabinet user in the chroot (Python 3.11 via uv, MPF,
        # MPF Monitor, Godot linux.arm64, GMC with our fixes).
        mkdir -p "$R/home/pi/MPF-Godot"
        tar -C "$REPO_ROOT" --exclude=.git --exclude='platforms/*/image/build/work' -cf - . | tar -C "$R/home/pi/MPF-Godot" -xf -
        in_chroot "chown -R pi:pi /home/pi"
        in_chroot "apt-get install -y -qq git build-essential cmake pkg-config"
        printf 'pi ALL=(ALL) NOPASSWD:ALL\n' > "$R/etc/sudoers.d/99-build"; chmod 440 "$R/etc/sudoers.d/99-build"
        in_chroot "su - pi -c 'cd ~/MPF-Godot && MPF_GODOT_DIR=~/MPF-Godot bash install/install_linux.sh --yes'"
        rm -f "$R/etc/sudoers.d/99-build"
        mkdir -p "$R/etc/systemd/system/getty@tty1.service.d"
        printf '[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin pi --noclear %%I $TERM\n' > "$R/etc/systemd/system/getty@tty1.service.d/autologin.conf"
        cat >> "$R/home/pi/.profile" <<'PROF'
# Start X on the first console (automatic login); remove this to get a plain shell
if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = /dev/tty1 ]; then exec startx; fi
PROF
    fi
    in_chroot "chown -R pi:pi /home/pi"
fi
in_chroot "apt-get clean"
rm -rf "$R"/var/lib/apt/lists/* "$R"/home/pi/.cache/uv "$R"/root/.bash_history 2>/dev/null || true

# Unique SSH host keys per card: drop the build-time keys, regenerate on first boot
rm -f "$R"/etc/ssh/ssh_host_*
cat > "$R/etc/systemd/system/ssh-hostkeys.service" <<'UNIT'
[Unit]
Description=Generate SSH host keys on first boot
Before=ssh.service
ConditionPathExistsGlob=!/etc/ssh/ssh_host_*_key

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A

[Install]
WantedBy=multi-user.target
UNIT
in_chroot "systemctl enable ssh-hostkeys.service >/dev/null 2>&1"

# Package manifest for review (before the chroot is torn down)
LC_ALL=C chroot "$R" dpkg-query -W -f='${Package}\t${Version}\t${Installed-Size}\n' > "$OUT/packages.tsv"
umount_chroot

##############################################################################
log "4/6 Partition and populate the image (no loop device)"
rm -rf "$R/boot/firmware"; mkdir -p "$R/boot/firmware"
ROOT_MB=$(( $(du -sm --apparent-size "$R" | cut -f1) + ROOT_PAD_MB ))
IMG="$OUT/$IMG_NAME"
rm -f "$IMG"
truncate -s $(( (1 + FW_MB + ROOT_MB + 1) * 1024 * 1024 )) "$IMG"
printf 'label: dos\nunit: sectors\n\n2048,%s,c,*\n,,83\n' $(( FW_MB * 2048 )) | sfdisk -q "$IMG"
FW_START=2048; ROOT_START=$(( 2048 + FW_MB * 2048 ))
# FAT32 firmware partition filled with mtools, ext4 root populated straight from the directory
dd if=/dev/zero of="$WORK/fw.img" bs=1M count=$FW_MB status=none
mkfs.vfat -F 32 -n firmware "$WORK/fw.img" >/dev/null
mcopy -s -i "$WORK/fw.img" "$FWDIR"/* ::/
dd if="$WORK/fw.img" of="$IMG" bs=512 seek=$FW_START conv=notrunc status=none; rm -f "$WORK/fw.img"
dd if=/dev/zero of="$WORK/root.img" bs=1M count=0 seek=$ROOT_MB status=none
mke2fs -q -t ext4 -L rootfs -d "$R" "$WORK/root.img"
dd if="$WORK/root.img" of="$IMG" bs=512 seek=$ROOT_START conv=notrunc,sparse status=none; rm -f "$WORK/root.img"

##############################################################################
log "5/6 Compress"
cd "$OUT"
xz -T0 -6 -f "$IMG_NAME"
sha256sum "$IMG_NAME.xz" > "$IMG_NAME.xz.sha256"
log "6/6 Done: $OUT/$IMG_NAME.xz"
cat "$IMG_NAME.xz.sha256"
