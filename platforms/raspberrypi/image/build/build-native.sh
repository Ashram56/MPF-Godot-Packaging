#!/usr/bin/env bash
# Build a minimal Raspberry Pi 4 SD card image (Debian 13 "trixie" arm64 userland, Raspberry Pi kernel, boot firmware
# and Wi-Fi firmware from archive.raspberrypi.com, the same packages as Raspberry Pi OS) natively, without
# podman/docker and without loop devices. Same idea as the Jetson Xavier NX image (platforms/jetson/image), but simpler.
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
#   ROOT_PAD_MB=1024           free space left in the root filesystem of the image (grown at first boot anyway; with READONLY=1 it
#                              is only the room for a maintenance session: apt upgrade, a kernel)
#   READONLY=1                 production mode (default): root and boot partition read-only, logs in RAM, one small read/write
#                              partition "mpfdata" (settings, scores, games, Wi-Fi, SSH keys) made at the first boot in the free
#                              space after the root partition (the rest of the card). READONLY=0: an ordinary writable image whose
#                              root grows at first boot. common/readonly/README.md; the page on port 8080 or
#                              `sudo mpf-mode maintenance` (or MODE=maintenance in mpf-network.txt) makes it writable
# Output: $WORK/out/rpi4-debian13-sd.img.xz and .sha256

set -euo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$PWD/work}"
SUITE=trixie
MIRROR="http://deb.debian.org/debian"
RPI_MIRROR="http://archive.raspberrypi.com/debian"
RPI_KEY_FPR=CF8A1AF502A2AA2D763BAE7E82B129927FA3303E   # Raspberry Pi Archive Signing Key
IMG_NAME="rpi4-debian13-sd.img"
PI_PASSWORD="${PI_PASSWORD:-raspberry}"
EXTRAS="${EXTRAS-video x11 mpf}"
ROOT_PAD_MB="${ROOT_PAD_MB:-1024}"
READONLY="${READONLY:-1}"
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
    # Slave bind mounts: / is shared under WSL/systemd, and a shared bind of /dev would propagate the
    # dev/pts mount back onto the host's /dev/pts (and make it "busy" at unmount time).
    mountpoint -q "$R/dev" || { mount -o bind /dev "$R/dev"; mount --make-rslave "$R/dev"; }
    mountpoint -q "$R/dev/pts" || { mount -o bind /dev/pts "$R/dev/pts"; mount --make-rslave "$R/dev/pts"; }
    mountpoint -q "$R/boot/firmware" || { mount -o bind "$FWDIR" "$R/boot/firmware"; mount --make-rslave "$R/boot/firmware"; }
    if [ -L "$R/etc/resolv.conf" ] || [ -e "$R/etc/resolv.conf" ]; then
        mv "$R/etc/resolv.conf" "$R/etc/resolv.conf.build-bak"
    fi
    cp -L /etc/resolv.conf "$R/etc/resolv.conf"
    printf '#!/bin/sh\nexit 101\n' > "$R/usr/sbin/policy-rc.d"; chmod 755 "$R/usr/sbin/policy-rc.d"
}

umount_chroot() {
    rm -f "$R/usr/sbin/policy-rc.d"
    for m in boot/firmware dev/pts dev sys proc; do
        mountpoint -q "$R/$m" && { umount "$R/$m" || umount -l "$R/$m"; }
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
    debootstrap debian-archive-keyring curl gnupg xz-utils e2fsprogs dosfstools mtools fdisk >/dev/null
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
# Raspberry Pi repository, only for the kernel, the boot firmware and the Wi-Fi firmware (pinned above Debian);
# everything else stays Debian. The key comes from the raspberrypi-archive-keyring package (fetched over HTTPS,
# fingerprint checked): the standalone raspberrypi.gpg.key still carries SHA-1 bindings, which apt's sqv rejects.
# Installing the package below keeps it up to date.
mkdir -p "$R/usr/share/keyrings" "$WORK/keyring"
KEYRING_DEB="$(curl -fsSL "${RPI_MIRROR/http:/https:}/dists/$SUITE/main/binary-arm64/Packages.gz" | gzip -dc \
    | awk '/^Package: raspberrypi-archive-keyring$/ {p=1} p && /^Filename:/ {print $2; p=0}')"
KEYRING_DEB="${KEYRING_DEB%%$'\n'*}"   # first entry; no early exit in the pipe (pipefail + SIGPIPE)
[ -n "$KEYRING_DEB" ] || { echo "raspberrypi-archive-keyring not found in $RPI_MIRROR"; exit 1; }
curl -fsSL "${RPI_MIRROR/http:/https:}/$KEYRING_DEB" -o "$WORK/keyring/keyring.deb"
dpkg-deb -x "$WORK/keyring/keyring.deb" "$WORK/keyring/x"
gpg --show-keys --with-colons "$WORK/keyring/x/usr/share/keyrings/raspberrypi-archive-keyring.pgp" | grep -q "^fpr:*$RPI_KEY_FPR:" \
    || { echo "unexpected Raspberry Pi archive key"; exit 1; }
install -m 644 "$WORK/keyring/x/usr/share/keyrings/raspberrypi-archive-keyring.pgp" "$R/usr/share/keyrings/"
rm -rf "$WORK/keyring" "$R/usr/share/keyrings/raspberrypi-archive-keyring.gpg"
echo "deb [signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.pgp] $RPI_MIRROR $SUITE main" > "$R/etc/apt/sources.list.d/raspi.list"
cat > "$R/etc/apt/preferences.d/raspi" <<'PIN'
Package: raspi-firmware firmware-brcm80211 raspberrypi-archive-keyring linux-image-* linux-headers-* linux-kbuild-* linux-base-rpi-*
Pin: origin archive.raspberrypi.com
Pin-Priority: 990

Package: *
Pin: origin archive.raspberrypi.com
Pin-Priority: 100
PIN
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

mount_chroot
in_chroot "apt-get update -qq && apt-get -y -qq upgrade"
# Kernel, Pi bootloader files and device trees (raspi-firmware fills /boot/firmware), Wi-Fi firmware
SYSTEM_PKGS="systemd systemd-sysv systemd-timesyncd systemd-resolved dbus udev kmod sudo locales openssh-server
  iproute2 iputils-ping curl nano parted fdisk e2fsprogs openssl less wpasupplicant iw rfkill wireless-regdb
  initramfs-tools rsync raspberrypi-archive-keyring"
in_chroot "apt-get install -y -qq $(echo $SYSTEM_PKGS)"   # one line: in_chroot runs bash -c, a newline would split the command
# Raspberry Pi kernel (v8 = Pi 3/4/400/CM4) and firmware: raspi-firmware copies start4.elf & co, kernel8.img,
# initramfs8, the device trees and overlays into /boot/firmware on every update. It leaves config.txt and
# cmdline.txt alone: they are ours, below.
in_chroot "apt-get install -y -qq raspi-firmware linux-image-rpi-v8 firmware-brcm80211"
in_chroot "apt-cache policy linux-image-rpi-v8 raspi-firmware firmware-brcm80211 | grep -B1 -A1 Installed"
cat > "$FWDIR/config.txt" <<'CFG'
# Raspberry Pi 4 boot configuration (https://www.raspberrypi.com/documentation/computers/config_txt.html)
arm_64bit=1
kernel=kernel8.img
auto_initramfs=1
arm_boost=1

# KMS graphics driver (Mesa v3d/v3dv), both HDMI outputs
dtoverlay=vc4-kms-v3d
max_framebuffers=2
disable_fw_kms_setup=1
disable_overscan=1
display_auto_detect=1

dtparam=audio=on
CFG
echo "console=serial0,115200 console=tty1 root=LABEL=rootfs rootfstype=ext4 fsck.repair=yes rootwait net.ifnames=0 quiet$([ "$READONLY" = 1 ] && echo ' ro')" > "$FWDIR/cmdline.txt"
for f in kernel8.img initramfs8 start4.elf fixup4.dat bcm2711-rpi-4-b.dtb overlays/vc4-kms-v3d.dtbo; do
    [ -s "$FWDIR/$f" ] || { echo "missing /boot/firmware/$f"; ls -la "$FWDIR"; exit 1; }
done

if [ "$READONLY" != 1 ]; then   # a read-only image keeps its root as built: mpf-persist makes the data partition in the free space instead
    install -m 755 "$KIT/files/resizerootfs.sh" "$R/usr/local/bin/resizerootfs.sh"
    install -m 644 "$KIT/files/resizerootfs.service" "$R/etc/systemd/system/resizerootfs.service"
fi

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
# Wi-Fi power saving (brcmfmac enables it) made the latency 170 ms and more to the gateway: off for good
mkdir -p "$R/etc/systemd/system/wpa_supplicant@wlan0.service.d"
printf '[Service]\nExecStartPost=-/usr/sbin/iw dev wlan0 set power_save off\n' > "$R/etc/systemd/system/wpa_supplicant@wlan0.service.d/power-save-off.conf"
[ "$READONLY" != 1 ] && in_chroot "systemctl enable resizerootfs.service >/dev/null 2>&1"
in_chroot "systemctl enable systemd-timesyncd ssh systemd-networkd systemd-resolved wpa_supplicant@wlan0.service >/dev/null 2>&1"
in_chroot "systemctl disable wpa_supplicant.service >/dev/null 2>&1 || true"

# Wi-Fi / SSH setup shared with the other images (common/netconfig): text file on the boot partition read at
# every boot, setup web page on port 8080, access point "MPF-Setup" when no network comes up.
in_chroot "apt-get install -y -qq python3 hostapd dnsmasq-base"
in_chroot "systemctl disable hostapd >/dev/null 2>&1 || true; systemctl mask hostapd >/dev/null 2>&1 || true"
NC="$REPO_ROOT/common/netconfig"
install -m 755 "$NC"/mpf_*.py "$R/usr/local/bin/"
install -m 644 "$NC"/mpf-netconfig-*.service "$NC/mpf-game.service" "$R/etc/systemd/system/"
install -m 644 "$NC/mpf-network.txt.template" "$FWDIR/mpf-network.txt"
printf 'MPF_NETCONFIG_FILE=/boot/firmware/mpf-network.txt\nMPF_USER=pi\nMPF_WLAN=wlan0\nMPF_GOZEN_SO=/home/pi/MPF-Godot/addons/gde_gozen/bin/libgozen.linux.template_release.arm64.so\n' > "$R/etc/default/mpf-netconfig"
# Game bundle uploaded from the web page (common/games/README.md): GODOT / MPF_GAME_VENV point at what the base system provides
mkdir -p "$R/opt/games" && chown 1000:1000 "$R/opt/games"
printf 'MPF_GAME_ARGS=-- --rendering-driver opengl3\n' > "$R/etc/default/mpf-game"
in_chroot "systemctl enable mpf-netconfig-apply.service mpf-netconfig-web.service mpf-netconfig-ap.service mpf-netconfig-inbox.service >/dev/null 2>&1"

in_chroot "id pi >/dev/null 2>&1 || useradd --create-home -G sudo,video,audio,render,input,tty -p \"\$(openssl passwd -6 '$PI_PASSWORD')\" -s /bin/bash pi"
if [ "$READONLY" = 1 ]; then
    . "$REPO_ROOT/common/readonly/install-readonly.sh"
    mpf_readonly_install "$R" pi /boot/firmware ""
    # the game starts at power-on (the page's "start at power-on" switch toggles this link in a short writable window)
    in_chroot "systemctl enable mpf-game.service >/dev/null 2>&1"
fi

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
        # Only the files git tracks (with their local edits): not .cache/ (GoZen build tree), .venv/, toolchain/...
        if git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
            git -C "$REPO_ROOT" ls-files -z | tar -C "$REPO_ROOT" --null -T - -cf - | tar -C "$R/home/pi/MPF-Godot" -xf -
        else
            tar -C "$REPO_ROOT" --exclude=.git --exclude=.cache --exclude=.venv --exclude=toolchain \
                --exclude='platforms/*/image/build/work' -cf - . | tar -C "$R/home/pi/MPF-Godot" -xf -
        fi
        in_chroot "chown -R pi:pi /home/pi"
        in_chroot "apt-get install -y -qq git build-essential cmake pkg-config"
        # sudo cannot work in the chroot (qemu-user binfmt without the C flag ignores setuid), so the installer
        # runs twice: as root for the system packages only, then as pi, where it finds them all in place
        # (--xvfb: the pi pass has no DISPLAY and wants Xvfb, the root pass may inherit one from WSLg).
        in_chroot "cd /home/pi/MPF-Godot && bash install/install_linux.sh --yes --no-setup --xvfb"
        rm -rf "$R/root/.local" "$R/root/.cache"   # root's copy of uv / Python 3.11, pi gets its own
        in_chroot "su - pi -c 'cd ~/MPF-Godot && MPF_GODOT_DIR=~/MPF-Godot bash install/install_linux.sh --yes'"
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
