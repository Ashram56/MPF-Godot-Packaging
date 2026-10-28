#!/usr/bin/env bash
# Build a minimal x86_64 UEFI disk image (Debian 13 "trixie" amd64, Debian kernel, Intel/AMD VAAPI video drivers) for
# mini PCs such as the Nipogi AK2PLUS (Intel N100). Same idea as the Raspberry Pi 4 image (platforms/raspberrypi/image) but
# simpler: the host is the same architecture, so no emulation, and no loop device (FAT via mtools, ext4 via mke2fs -d).
# The bootloader is one GRUB EFI file (EFI/BOOT/BOOTX64.EFI) built with grub-mkstandalone, so it needs no
# grub-install on the target and works from a USB stick or an internal disk alike.
#
# Run as root on an x86_64 Ubuntu 22.04+ / Debian host (WSL2 is fine) with ~15 GB free disk:
#   sudo ./build-native.sh            (or sudo bash wsl-build.sh, which also installs the host packages)
# Optional environment:
#   WORK=/path/to/workdir      (default: ./work; keep it in the Linux home under WSL, never /mnt/c)
#   MPF_PASSWORD=...           password of user "mpf" (default: mpf)
#   WIFI_SSID=... WIFI_PSK=... pre-seed one Wi-Fi network (stored hashed via wpa_passphrase)
#   WIFI_COUNTRY=FR            regulatory country code for Wi-Fi
#   EXTRAS="video x11 mpf"     feature groups (default: all three; EXTRAS="" for the bare image)
#       video  : GStreamer + FFmpeg + vainfo (VAAPI test tools)
#       x11    : Xorg (modesetting), startx, openbox, xrandr, Mesa Vulkan (Intel ANV, AMD RADV) and GL drivers
#       mpf    : MPF + Godot + GMC installed by install/install_linux.sh from this repository into
#                /home/mpf/MPF-Godot; automatic login on tty1 and startx (needs video and x11, added when missing)
#   KEYMAP=fr                  keyboard layout of GRUB, the console and X (xkb name; default fr = AZERTY; us for QWERTY)
#   ROOT_PAD_MB=1024           free space left in the root filesystem of the image (grown at first boot anyway)
# Output: $WORK/out/x86-debian13-uefi.img.xz and .sha256

set -euo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$PWD/work}"
SUITE=trixie
MIRROR="http://deb.debian.org/debian"
IMG_NAME="x86-debian13-uefi.img"
MPF_PASSWORD="${MPF_PASSWORD:-mpf}"
EXTRAS="${EXTRAS-video x11 mpf}"
ROOT_PAD_MB="${ROOT_PAD_MB:-1024}"
KEYMAP="${KEYMAP:-fr}"
ESP_MB=256
REPO_ROOT="$(cd "$KIT/../../../.." && pwd)"

R="$WORK/rootfs"
ESP="$WORK/esp"             # bind-mounted on $R/boot/efi while packages install, then copied into the FAT partition
OUT="$WORK/out"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
CHROOT_ENV=()   # set by proxy_in
in_chroot() { LC_ALL=C DEBIAN_FRONTEND=noninteractive chroot "$R" /usr/bin/env "${CHROOT_ENV[@]}" bash -c "$*"; }

mount_chroot() {
    mkdir -p "$R/boot/efi" "$ESP"
    mountpoint -q "$R/proc" || mount -t proc proc "$R/proc"
    mountpoint -q "$R/sys" || mount -t sysfs sys "$R/sys"
    # Slave bind mounts: / is shared under WSL/systemd, and a shared bind of /dev would propagate the
    # dev/pts mount back onto the host's /dev/pts (and make it "busy" at unmount time).
    mountpoint -q "$R/dev" || { mount -o bind /dev "$R/dev"; mount --make-rslave "$R/dev"; }
    mountpoint -q "$R/dev/pts" || { mount -o bind /dev/pts "$R/dev/pts"; mount --make-rslave "$R/dev/pts"; }
    mountpoint -q "$R/boot/efi" || { mount -o bind "$ESP" "$R/boot/efi"; mount --make-rslave "$R/boot/efi"; }
    if [ -L "$R/etc/resolv.conf" ] || [ -e "$R/etc/resolv.conf" ]; then
        mv "$R/etc/resolv.conf" "$R/etc/resolv.conf.build-bak"
    fi
    cp -L /etc/resolv.conf "$R/etc/resolv.conf"
    printf '#!/bin/sh\nexit 101\n' > "$R/usr/sbin/policy-rc.d"; chmod 755 "$R/usr/sbin/policy-rc.d"
}

umount_chroot() {
    rm -f "$R/usr/sbin/policy-rc.d"
    for m in boot/efi dev/pts dev sys proc; do
        mountpoint -q "$R/$m" && { umount "$R/$m" || umount -l "$R/$m"; }
    done
    if [ -e "$R/etc/resolv.conf.build-bak" ] || [ -L "$R/etc/resolv.conf.build-bak" ]; then
        mv -f "$R/etc/resolv.conf.build-bak" "$R/etc/resolv.conf"
    fi
    return 0
}
# Behind a TLS-inspecting proxy (CI sandboxes): give the chroot the proxy and its CA while the installers run. /etc/environment
# is read by `su -`. Both are removed again afterwards, the image never carries them.
proxy_in() {
    [ -n "${HTTPS_PROXY:-}" ] && [ -f "${CURL_CA_BUNDLE:-}" ] || return 0
    cp "$CURL_CA_BUNDLE" "$R/usr/local/share/ca-certificates/build-proxy.crt"
    CHROOT_ENV=(SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
                PIP_CERT=/etc/ssl/certs/ca-certificates.crt UV_NATIVE_TLS=1)
    in_chroot "update-ca-certificates >/dev/null 2>&1"
    printf 'HTTPS_PROXY=%s\nhttps_proxy=%s\nNO_PROXY=%s\nno_proxy=%s\nSSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt\nCURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt\nREQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt\nPIP_CERT=/etc/ssl/certs/ca-certificates.crt\nUV_NATIVE_TLS=1\n' \
        "$HTTPS_PROXY" "$HTTPS_PROXY" "${NO_PROXY:-}" "${NO_PROXY:-}" > "$R/etc/environment"
}
proxy_out() {
    rm -f "$R/usr/local/share/ca-certificates/build-proxy.crt" "$R/etc/environment"
    CHROOT_ENV=()
    in_chroot "update-ca-certificates --fresh >/dev/null 2>&1"
}

trap 'umount_chroot || true' EXIT

[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
[ "$(uname -m)" = x86_64 ] || { echo "build on an x86_64 host"; exit 1; }
mkdir -p "$WORK" "$OUT"

##############################################################################
log "1/6 Host dependencies"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    debootstrap debian-archive-keyring curl gnupg xz-utils e2fsprogs dosfstools mtools fdisk grub-efi-amd64-bin grub-common console-setup >/dev/null

##############################################################################
log "2/6 Minimal Debian $SUITE amd64 rootfs"
if [ ! -x "$R/bin/bash" ]; then
    debootstrap --arch=amd64 --variant=minbase --include=ca-certificates "$SUITE" "$R" "$MIRROR"
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

echo mpf-x86 > "$R/etc/hostname"
printf '127.0.0.1\tlocalhost\n127.0.1.1\tmpf-x86\n::1\tlocalhost ip6-localhost ip6-loopback\n' > "$R/etc/hosts"
printf 'LABEL=firmware /boot/efi vfat umask=0077,nofail 0 2\nLABEL=rootfs / ext4 defaults,noatime 0 1\n' > "$R/etc/fstab"

mount_chroot
in_chroot "apt-get update -qq && apt-get -y -qq upgrade"
# systemd and the network; initramfs-tools with MODULES=most so the same image boots from USB, SATA, NVMe or eMMC
SYSTEM_PKGS="systemd systemd-sysv systemd-timesyncd systemd-resolved dbus udev kmod sudo locales openssh-server
  iproute2 iputils-ping curl nano parted fdisk e2fsprogs dosfstools rsync efibootmgr openssl less wpasupplicant iw rfkill
  wireless-regdb initramfs-tools pciutils usbutils"
in_chroot "apt-get install -y -qq $(echo $SYSTEM_PKGS)"   # one line: in_chroot runs bash -c, a newline would split the command
echo 'MODULES=most' > "$R/etc/initramfs-tools/conf.d/modules"
grep -qx i915 "$R/etc/initramfs-tools/modules" || printf 'i915\n' >> "$R/etc/initramfs-tools/modules"   # the GPU comes up with the initramfs: a picture early, /dev/dri ready before the login
# Debian's kernel, firmware for the common mini-PC chips (Wi-Fi: Intel, Realtek, MediaTek, Atheros; Ethernet: Realtek;
# Intel graphics GuC/HuC; Bluetooth shares the Wi-Fi packages), the Intel and AMD VAAPI drivers
in_chroot "apt-get install -y -qq linux-image-amd64 firmware-iwlwifi firmware-realtek firmware-mediatek firmware-atheros firmware-intel-graphics firmware-intel-misc \
    intel-media-va-driver mesa-va-drivers libva2 libva-drm2 vainfo"
in_chroot "ls /boot/vmlinuz-* /boot/initrd.img-* && test -L /vmlinuz && test -L /initrd.img"

# Bootloader: standalone GRUB EFI files with their configuration inside (in a standalone GRUB $cmdpath is the memory disk, not
# the ESP, so nothing can be read next to the file). The loader finds the root partition by label and starts /vmlinuz (a
# symlink Debian keeps on the newest kernel, so a kernel update needs no bootloader work). Two loaders: EFI/BOOT/BOOTX64.EFI
# looks for the stick's root label "rootfs"; EFI/BOOT/mpf-disk.efi looks for "mpfroot", and mpf-install-to-disk copies it
# over BOOTX64.EFI of the internal disk.
mkdir -p "$ESP/EFI/BOOT"
GRUBFILES=()
KEYMAP_CMDS=""
if [ "$KEYMAP" != us ]; then
    grub-kbdcomp -o "$WORK/grub-keymap.gkb" "$KEYMAP" 2>/dev/null || { echo "grub-kbdcomp $KEYMAP failed"; exit 1; }
    GRUBFILES+=("boot/grub/layouts/$KEYMAP.gkb=$WORK/grub-keymap.gkb")
    KEYMAP_CMDS="insmod keylayouts
keymap \$prefix/layouts/$KEYMAP.gkb
"
fi
make_loader() {   # make_loader ROOT_LABEL OUTPUT
    cat > "$WORK/grub-embedded.cfg" <<CFG
set timeout=0
${KEYMAP_CMDS}search --no-floppy --label $1 --set=root
linux /vmlinuz root=LABEL=$1 rootfstype=ext4 rootwait net.ifnames=0 fsck.repair=yes quiet loglevel=3
initrd /initrd.img
boot
CFG
    grub-mkstandalone -O x86_64-efi -o "$2" \
        --modules="part_gpt part_msdos fat ext2 search search_label search_fs_file linux normal configfile echo test all_video gzio keylayouts" \
        "boot/grub/grub.cfg=$WORK/grub-embedded.cfg" "${GRUBFILES[@]}"
    [ -s "$2" ] || { echo "grub-mkstandalone failed"; exit 1; }
}
make_loader rootfs "$ESP/EFI/BOOT/BOOTX64.EFI"
make_loader mpfroot "$ESP/EFI/BOOT/mpf-disk.efi"

install -m 755 "$KIT/files/resizerootfs.sh" "$R/usr/local/bin/resizerootfs.sh"
install -m 644 "$KIT/../../../raspberrypi/image/build/files/resizerootfs.service" "$R/etc/systemd/system/resizerootfs.service"
install -m 755 "$KIT/files/mpf-install-to-disk.sh" "$R/usr/local/sbin/mpf-install-to-disk"
install -m 755 "$KIT/files/mpf-installer.sh" "$R/usr/local/sbin/mpf-installer"
# the stick's console menu runs without a password, nothing else does
printf 'mpf ALL=(root) NOPASSWD: /usr/local/sbin/mpf-installer, /usr/local/sbin/mpf-install-to-disk\n' > "$R/etc/sudoers.d/mpf-installer"
chmod 440 "$R/etc/sudoers.d/mpf-installer"

printf 'XKBMODEL="pc105"\nXKBLAYOUT="%s"\nXKBVARIANT=""\nXKBOPTIONS=""\nBACKSPACE="guess"\n' "$KEYMAP" > "$R/etc/default/keyboard"
mkdir -p "$R/etc/X11/xorg.conf.d"
printf 'Section "InputClass"\n    Identifier "keyboard layout"\n    MatchIsKeyboard "on"\n    Option "XkbLayout" "%s"\nEndSection\n' "$KEYMAP" > "$R/etc/X11/xorg.conf.d/00-keyboard.conf"
in_chroot "apt-get install -y -qq console-setup keyboard-configuration >/dev/null 2>&1 && setupcon --save-only >/dev/null 2>&1 || true"
in_chroot "sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen && locale-gen >/dev/null && update-locale LANG=en_US.UTF-8"

# Networking: systemd-networkd + resolved, wired preferred over Wi-Fi via route metric (interface names eth0, wlan0:
# net.ifnames=0 on the kernel command line, as on the Pi image, so common/netconfig finds wlan0).
mkdir -p "$R/etc/systemd/network"
printf '[Match]\nName=eth* en*\n\n[Network]\nDHCP=yes\n\n[DHCP]\nRouteMetric=100\n' > "$R/etc/systemd/network/20-wired.network"
printf '[Match]\nName=wlan* wl*\n\n[Network]\nDHCP=yes\n\n[DHCP]\nRouteMetric=600\n' > "$R/etc/systemd/network/25-wireless.network"
ln -sf /run/systemd/resolve/stub-resolv.conf "$R/etc/resolv.conf.build-bak"   # becomes /etc/resolv.conf on unmount
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
mkdir -p "$R/etc/systemd/system/wpa_supplicant@wlan0.service.d"
printf '[Service]\nExecStartPost=-/usr/sbin/iw dev wlan0 set power_save off\n' > "$R/etc/systemd/system/wpa_supplicant@wlan0.service.d/power-save-off.conf"
in_chroot "systemctl enable resizerootfs.service systemd-timesyncd ssh systemd-networkd systemd-resolved wpa_supplicant@wlan0.service >/dev/null 2>&1"
in_chroot "systemctl disable wpa_supplicant.service >/dev/null 2>&1 || true"

# Wi-Fi / SSH setup shared with the other images (common/netconfig): text file on the ESP (visible from Windows after
# flashing) read at every boot, setup web page on port 8080, access point "MPF-Setup" when no network comes up.
in_chroot "apt-get install -y -qq python3 hostapd dnsmasq-base"
in_chroot "systemctl disable hostapd >/dev/null 2>&1 || true; systemctl mask hostapd >/dev/null 2>&1 || true"
NC="$REPO_ROOT/common/netconfig"
install -m 755 "$NC/mpf_netconfig.py" "$R/usr/local/bin/mpf_netconfig.py"
install -m 644 "$NC"/mpf-netconfig-*.service "$NC/mpf-game.service" "$R/etc/systemd/system/"
install -m 644 "$NC/mpf-network.txt.template" "$ESP/mpf-network.txt"
install -m 644 "$KIT/../../cabinet/mpf-netconfig.env" "$R/etc/default/mpf-netconfig"
install -d "$R/etc/mpf"
install -m 644 "$KIT/../../cabinet/game-override.cfg" "$R/etc/mpf/game-override.cfg"
mkdir -p "$R/opt/games" && chown 1000:1000 "$R/opt/games"
install -m 644 "$KIT/../../cabinet/mpf-game.env" "$R/etc/default/mpf-game"
in_chroot "systemctl enable mpf-netconfig-apply.service mpf-netconfig-web.service mpf-netconfig-ap.service mpf-game.service >/dev/null 2>&1"

in_chroot "id mpf >/dev/null 2>&1 || useradd --create-home -G sudo,video,audio,render,input,tty -p \"\$(openssl passwd -6 '$MPF_PASSWORD')\" -s /bin/bash mpf"

##############################################################################
log "3/6 Optional feature groups: ${EXTRAS:-none}"
has() { case " $EXTRAS " in *" $1 "*) return 0;; *) return 1;; esac; }
if [ -n "$EXTRAS" ]; then
    has mpf && ! has video && EXTRAS="$EXTRAS video"
    has mpf && ! has x11 && EXTRAS="$EXTRAS x11"
    if has video; then
        in_chroot "apt-get install -y -qq gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-vaapi gstreamer1.0-alsa v4l-utils ffmpeg alsa-utils intel-gpu-tools"
    fi
    if has x11; then
        in_chroot "apt-get install -y -qq xserver-xorg-core xserver-xorg-input-libinput xinit x11-xserver-utils xauth openbox xterm libpam-systemd \
            mesa-vulkan-drivers libgl1-mesa-dri libegl1 libvulkan1 libxcursor1 libxinerama1 libxrandr2 libxi6 libxext6 libxrender1 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3"
        printf 'allowed_users=console\nneeds_root_rights=auto\n' > "$R/etc/X11/Xwrapper.config"
        install -m 755 "$KIT/../../cabinet/xinitrc" "$R/home/mpf/.xinitrc"
    fi
    if has mpf; then
        # The repository's own Linux installer, run as the cabinet user in the chroot (Python 3.11 via uv, MPF,
        # MPF Monitor, Godot linux.x86_64, GMC with our fixes).
        mkdir -p "$R/home/mpf/MPF-Godot"
        # Only the files git tracks (with their local edits): not .cache/ (GoZen build tree), .venv/, toolchain/...
        if git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
            git -C "$REPO_ROOT" ls-files -z | tar -C "$REPO_ROOT" --null -T - -cf - | tar -C "$R/home/mpf/MPF-Godot" -xf -
        else
            tar -C "$REPO_ROOT" --exclude=.git --exclude=.cache --exclude=.venv --exclude=toolchain \
                --exclude='platforms/*/image/build/work' -cf - . | tar -C "$R/home/mpf/MPF-Godot" -xf -
        fi
        in_chroot "chown -R mpf:mpf /home/mpf"
        proxy_in
        in_chroot "apt-get install -y -qq git build-essential cmake pkg-config"
        # The installer runs twice: as root for the system packages only, then as mpf, where it finds them all in
        # place (--xvfb: the mpf pass has no DISPLAY and wants Xvfb, the root pass may inherit one from WSLg).
        in_chroot "cd /home/mpf/MPF-Godot && bash install/install_linux.sh --yes --no-setup --xvfb"
        rm -rf "$R/root/.local" "$R/root/.cache"   # root's copy of uv / Python 3.11, mpf gets its own
        in_chroot "su - mpf -c 'cd ~/MPF-Godot && MPF_GODOT_DIR=~/MPF-Godot bash install/install_linux.sh --yes'"
        proxy_out
        mkdir -p "$R/etc/systemd/system/getty@tty1.service.d"
        printf '[Unit]\nStartLimitIntervalSec=0\n\n[Service]\nRestartSec=2\nExecStart=\nExecStart=-/sbin/agetty --autologin mpf --noclear %%I $TERM\n' > "$R/etc/systemd/system/getty@tty1.service.d/autologin.conf"
        cat >> "$R/home/mpf/.profile" <<'PROF'
# First console (automatic login): from the USB stick (root label "rootfs") the installer menu, from an installed disk X.
# Remove this to get a plain shell.
if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = /dev/tty1 ]; then
    if [ "$(findmnt -no LABEL /)" = rootfs ]; then exec sudo /usr/local/sbin/mpf-installer; fi
    # udev gives the video group /dev/dri/card0 a moment after the login: wait for it, or X fails and getty gives up
    for _ in $(seq 1 100); do [ -w /dev/dri/card0 ] && break; sleep 0.2; done
    udevadm settle --timeout=10 2>/dev/null
    exec startx
fi
PROF
    fi
    in_chroot "chown -R mpf:mpf /home/mpf"
fi
in_chroot "apt-get clean"
rm -rf "$R"/var/lib/apt/lists/* "$R"/home/mpf/.cache/uv "$R"/root/.bash_history 2>/dev/null || true

# Unique SSH host keys per machine: drop the build-time keys, regenerate on first boot
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
rm -rf "$R/boot/efi"; mkdir -p "$R/boot/efi"
ROOT_MB=$(( $(du -sm --apparent-size "$R" | cut -f1) + ROOT_PAD_MB ))
IMG="$OUT/$IMG_NAME"
rm -f "$IMG"
truncate -s $(( (1 + ESP_MB + ROOT_MB + 1) * 1024 * 1024 )) "$IMG"
printf 'label: gpt\nunit: sectors\nfirst-lba: 2048\n\nstart=2048, size=%s, type=U, name="firmware"\ntype=L, name="rootfs"\n' $(( ESP_MB * 2048 )) | sfdisk -q "$IMG"
ESP_START=2048; ROOT_START=$(( 2048 + ESP_MB * 2048 ))
# FAT32 ESP filled with mtools, ext4 root populated straight from the directory
dd if=/dev/zero of="$WORK/esp.img" bs=1M count=$ESP_MB status=none
mkfs.vfat -F 32 -n firmware "$WORK/esp.img" >/dev/null
mcopy -s -i "$WORK/esp.img" "$ESP"/* ::/
dd if="$WORK/esp.img" of="$IMG" bs=512 seek=$ESP_START conv=notrunc status=none; rm -f "$WORK/esp.img"
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
