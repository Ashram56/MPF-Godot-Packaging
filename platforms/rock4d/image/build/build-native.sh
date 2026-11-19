#!/usr/bin/env bash
# Build a minimal Radxa ROCK 4D (RK3576) SD card / eMMC image: Debian 13 "trixie" arm64 userland, the mainline Linux kernel of
# trixie-backports (RK3576, Mali-G52 through Panfrost, rkvdec decoder, HDMI), the board's U-Boot built by uboot-build.sh,
# natively, without podman/docker and without loop devices. Same layout and services as the Raspberry Pi 5 image
# (platforms/raspberrypi5/image), the bootloader and the kernel files are what differ.
#
# Run as root on an x86_64 Ubuntu 22.04+ host (WSL2 is fine) with ~15 GB free disk:
#   sudo ./build-native.sh            (or sudo bash wsl-build.sh, which also installs the host packages)
# Optional environment:
#   WORK=/path/to/workdir      (default: ./work; keep it in the Linux home under WSL, never /mnt/c)
#   UBOOT_BIN=/path/u-boot-rockchip.bin   a U-Boot already built (default: uboot-build.sh builds it)
#   ROCK_PASSWORD=...          password of user "rock" (default: rock)
#   WIFI_SSID=... WIFI_PSK=... pre-seed one Wi-Fi network (stored hashed via wpa_passphrase)
#   WIFI_COUNTRY=FR            regulatory country code for Wi-Fi
#   EXTRAS="video x11 mpf"     feature groups (default: all three; EXTRAS="" for the bare image)
#       video  : GStreamer + FFmpeg (V4L2 decoder tools)
#       x11    : Xorg (modesetting), startx, openbox, xrandr, Mesa GL (Panfrost) drivers
#       mpf    : MPF + Godot + GMC installed by install/install_linux.sh from this repository into
#                /home/rock/MPF-Godot; automatic login on tty1 and startx (needs video and x11, added when missing)
#   (Wi-Fi/SSH: edit mpf-network.txt on the boot partition, or use http://<ip>:8080; see common/netconfig/README.md)
#   ROOT_PAD_MB=1024           free space left in the root filesystem of the image
#   READONLY=1                 production mode (default): root and boot partition read-only, logs in RAM, one small read/write
#                              partition "mpfdata" made at the first boot in the free space after the root partition.
#                              READONLY=0: an ordinary writable image whose root grows at first boot. common/readonly/README.md
#   GOZEN_SO=/path/libgozen.linux.template_release.arm64.so   a GoZen build with the v4l2-request decoder (platforms/rock4d.md)
# Output: $WORK/out/rock4d-debian13-sd.img.xz, .sha256 and u-boot-rockchip.bin (+ SHA256SUMS)

set -euo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$PWD/work}"
SUITE=trixie
MIRROR="http://deb.debian.org/debian"
IMG_NAME="rock4d-debian13-sd.img"
ROCK_PASSWORD="${ROCK_PASSWORD:-rock}"
EXTRAS="${EXTRAS-video x11 mpf}"
ROOT_PAD_MB="${ROOT_PAD_MB:-1024}"
READONLY="${READONLY:-1}"
FW_MB=384
REPO_ROOT="$(cd "$KIT/../../../.." && pwd)"

R="$WORK/rootfs"
FWDIR="$WORK/firmware"      # bind-mounted on $R/boot/firmware while packages install (the kernel hook fills it), then copied into the FAT partition
OUT="$WORK/out"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
CHROOT_ENV=()   # set by proxy_in
in_chroot() { LC_ALL=C DEBIAN_FRONTEND=noninteractive chroot "$R" /usr/bin/env "${CHROOT_ENV[@]}" bash -c "$*"; }

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
mkdir -p "$WORK" "$OUT"

##############################################################################
log "1/6 Host dependencies and arm64 emulation"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    debootstrap debian-archive-keyring curl gnupg xz-utils e2fsprogs dosfstools mtools fdisk gcc-aarch64-linux-gnu make gcc bison flex swig \
    device-tree-compiler python3-pyelftools python3-setuptools libssl-dev libgnutls28-dev bc >/dev/null
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq qemu-user-static binfmt-support >/dev/null 2>&1 \
    || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq qemu-user qemu-user-binfmt >/dev/null
mountpoint -q /proc/sys/fs/binfmt_misc || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
if [ ! -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]; then
    update-binfmts --enable qemu-aarch64 2>/dev/null || cat /usr/lib/binfmt.d/qemu-aarch64.conf > /proc/sys/fs/binfmt_misc/register
fi

# the board's bootloader (about a minute)
if [ -z "${UBOOT_BIN:-}" ]; then
    UBOOT_WORK="$WORK/uboot-work" UBOOT_OUT="$WORK/uboot-out" bash "$KIT/uboot-build.sh"
    UBOOT_BIN="$WORK/uboot-out/u-boot-rockchip.bin"
fi
[ -s "$UBOOT_BIN" ] || { echo "no U-Boot at $UBOOT_BIN"; exit 1; }

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
# The kernel comes from trixie-backports (mainline 7.x: RK3576 and the ROCK 4D are in it, Debian's 6.12 has neither); everything
# else stays trixie.
echo "deb $MIRROR $SUITE-backports main contrib non-free non-free-firmware" > "$R/etc/apt/sources.list.d/backports.list"
cat > "$R/etc/dpkg/dpkg.cfg.d/excludes" <<'DPKG'
path-exclude=/usr/share/doc/*
path-include=/usr/share/doc/*/copyright
path-exclude=/usr/share/man/*
path-exclude=/usr/share/info/*
path-exclude=/usr/share/locale/*
path-include=/usr/share/locale/locale.alias
DPKG
printf 'APT::Install-Recommends "false";\nAPT::Install-Suggests "false";\n' > "$R/etc/apt/apt.conf.d/99norecommends"

echo mpf-rock4d > "$R/etc/hostname"
printf '127.0.0.1\tlocalhost\n127.0.1.1\tmpf-rock4d\n::1\tlocalhost ip6-localhost ip6-loopback\n' > "$R/etc/hosts"
printf 'LABEL=firmware /boot/firmware vfat defaults 0 2\nLABEL=rootfs / ext4 defaults,noatime 0 1\n' > "$R/etc/fstab"

mount_chroot
proxy_in
in_chroot "apt-get update -qq && apt-get -y -qq upgrade"
# Kernel (below) and Wi-Fi firmware
SYSTEM_PKGS="systemd systemd-sysv systemd-timesyncd systemd-resolved dbus udev kmod sudo locales openssh-server
  iproute2 iputils-ping curl nano parted fdisk e2fsprogs openssl less wpasupplicant iw rfkill wireless-regdb
  initramfs-tools rsync"
in_chroot "apt-get install -y -qq $(echo $SYSTEM_PKGS)"   # one line: in_chroot runs bash -c, a newline would split the command
# Kernel hook: copies the kernel, the initramfs and the board's device tree to the FAT partition and writes the U-Boot menu
# (extlinux), on every kernel install or update. U-Boot of the board reads /extlinux/extlinux.conf there.
install -d "$R/etc/kernel/postinst.d" "$R/etc/default"
install -m 755 "$KIT/files/zz-mpf-rock4d" "$R/etc/kernel/postinst.d/zz-mpf-rock4d"
CMDLINE="root=LABEL=rootfs rootfstype=ext4 rootwait fsck.repair=yes net.ifnames=0 console=ttyS2,1500000n8 console=tty1 quiet$([ "$READONLY" = 1 ] && echo ' ro')"
echo "MPF_CMDLINE=\"$CMDLINE\"" > "$R/etc/default/mpf-boot"
mkdir -p "$R/etc/initramfs-tools/conf.d"
echo "COMPRESS=zstd" > "$R/etc/initramfs-tools/conf.d/compress"
in_chroot "apt-get install -y -qq zstd"
in_chroot "apt-get install -y -qq -t $SUITE-backports linux-image-arm64"
in_chroot "apt-get install -y -qq firmware-realtek firmware-brcm80211 firmware-atheros firmware-mediatek"
in_chroot "apt-cache policy linux-image-arm64 | grep -B1 -A1 Installed"
for f in Image initrd.img rk3576-rock-4d.dtb extlinux/extlinux.conf; do
    [ -s "$FWDIR/$f" ] || { echo "missing /boot/firmware/$f"; ls -laR "$FWDIR"; exit 1; }
done
KVER="$(ls "$R/lib/modules" | head -1)"
for m in rockchip-vdec panfrost rockchipdrm dw_mmc-rockchip sdhci-of-dwcmshc dwmac-rk; do
    find "$R/lib/modules/$KVER" \( -name "$m.ko*" -o -name "${m//-/_}.ko*" \) | grep -q . || { echo "kernel module $m is missing in $KVER"; exit 1; }
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
CAB="$KIT/../../cabinet"   # platforms/rock4d/cabinet: GoZen/audio settings, game environment, X layout
install -m 644 "$CAB/mpf-netconfig.env" "$R/etc/default/mpf-netconfig"
# Game bundle uploaded from the web page (common/games/README.md): GODOT / MPF_GAME_VENV point at what the base system provides
mkdir -p "$R/opt/games" && chown 1000:1000 "$R/opt/games"
install -m 644 "$CAB/mpf-game.env" "$R/etc/default/mpf-game"
# default sound on the HDMI output
install -m 644 "$CAB/asound.conf" "$R/etc/asound.conf"
in_chroot "systemctl enable mpf-netconfig-apply.service mpf-netconfig-web.service mpf-netconfig-ap.service mpf-netconfig-inbox.service >/dev/null 2>&1"

in_chroot "id rock >/dev/null 2>&1 || useradd --create-home -G sudo,video,audio,render,input,tty -p \"\$(openssl passwd -6 '$ROCK_PASSWORD')\" -s /bin/bash rock"
if [ "$READONLY" = 1 ]; then
    . "$REPO_ROOT/common/readonly/install-readonly.sh"
    # the X server of a user session writes ~/.local/share/xorg/Xorg.0.log and stops at once when it cannot (the login would end and
    # restart every 2 s on a read-only root: seen on the x86 image), and the toolchain writes ~/.cache: RAM disks owned by rock
    mpf_readonly_install "$R" rock /boot/firmware "" "/home/rock/.cache:128m /home/rock/.local/share/xorg:8m"
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
            libgl1-mesa-dri libegl1 libgles2 libgbm1 libvulkan1 mesa-utils-bin libxcursor1 libxinerama1 libxrandr2 libxi6 libxext6 libxrender1 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3"
        printf 'allowed_users=console\nneeds_root_rights=auto\n' > "$R/etc/X11/Xwrapper.config"
        # every connected output on, left to right (backglass + full LCD DMD, like the Jetson image)
        install -m 755 "$CAB/xinitrc" "$R/home/rock/.xinitrc"
        if [ "$READONLY" = 1 ]; then   # X server log in RAM (see mpf_readonly_install above)
            printf '#!/bin/sh\n\nexec /usr/bin/X -nolisten tcp -logfile /tmp/Xorg.0.log "$@"\n' > "$R/etc/X11/xinit/xserverrc"
            chmod 755 "$R/etc/X11/xinit/xserverrc"
        fi
    fi
    if has mpf; then
        # The repository's own Linux installer, run as the cabinet user in the chroot (Python 3.11 via uv, MPF,
        # MPF Monitor, Godot linux.arm64, GMC with our fixes).
        mkdir -p "$R/home/rock/MPF-Godot"
        # Only the files git tracks (with their local edits): not .cache/ (GoZen build tree), .venv/, toolchain/...
        if git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
            git -C "$REPO_ROOT" ls-files -z | tar -C "$REPO_ROOT" --null -T - -cf - | tar -C "$R/home/rock/MPF-Godot" -xf -
        else
            tar -C "$REPO_ROOT" --exclude=.git --exclude=.cache --exclude=.venv --exclude=toolchain \
                --exclude='platforms/*/image/build/work' -cf - . | tar -C "$R/home/rock/MPF-Godot" -xf -
        fi
        in_chroot "chown -R rock:rock /home/rock"
        in_chroot "apt-get install -y -qq git build-essential cmake pkg-config"
        # sudo cannot work in the chroot (qemu-user binfmt without the C flag ignores setuid), so the installer
        # runs twice: as root for the system packages only, then as rock, where it finds them all in place
        # (--xvfb: the rock pass has no DISPLAY and wants Xvfb, the root pass may inherit one from WSLg).
        in_chroot "cd /home/rock/MPF-Godot && bash install/install_linux.sh --yes --no-setup --xvfb"
        rm -rf "$R/root/.local" "$R/root/.cache"   # root's copy of uv / Python 3.11, rock gets its own
        in_chroot "su - rock -c 'cd ~/MPF-Godot && MPF_GODOT_DIR=~/MPF-Godot bash install/install_linux.sh --yes'"
        # dmd_bridge, the platform's ZeDMD + Serum output (libzedmd and libserum, PPUC's, unmodified) in ~/MPF-Godot/native/bin/dmd_bridge,
        # where common/netconfig/mpf_dmd.py finds it. DMD_BRIDGE_TARBALL=<aarch64 tarball> (+ DMD_BRIDGE_SHA256) installs a prebuilt one;
        # without it libzedmd and libserum are compiled in the chroot (slow under QEMU).
        if [ -n "${DMD_BRIDGE_TARBALL:-}" ]; then
            [ -z "${DMD_BRIDGE_SHA256:-}" ] || echo "$DMD_BRIDGE_SHA256  $DMD_BRIDGE_TARBALL" | sha256sum -c - || exit 1
            mkdir -p "$R/home/rock/MPF-Godot/native/bin"
            tar xzf "$DMD_BRIDGE_TARBALL" -C "$R/home/rock/MPF-Godot/native/bin"   # contains dmd_bridge/ (binary + lib/, RUNPATH $ORIGIN/lib)
            [ -x "$R/home/rock/MPF-Godot/native/bin/dmd_bridge/dmd_bridge" ] || { echo "no dmd_bridge in $DMD_BRIDGE_TARBALL"; exit 1; }
            in_chroot "chown -R rock:rock /home/rock/MPF-Godot/native/bin"
        else
            in_chroot "apt-get install -y -qq autoconf automake libtool"
            in_chroot "su - rock -c 'cd ~/MPF-Godot && bash native/dmd_bridge/build_all.sh'"
        fi
        if [ -n "${GOZEN_SO:-}" ]; then   # a GoZen build with FFmpeg's v4l2-request decoder (platforms/rock4d.md, "Video")
            install -m 755 "$GOZEN_SO" "$R/home/rock/MPF-Godot/addons/gde_gozen/bin/libgozen.linux.template_release.arm64.so"
            sed -i 's/^GOZEN_HWDEC=0/GOZEN_HWDEC=1/' "$R/etc/default/mpf-netconfig"
            in_chroot "chown rock:rock /home/rock/MPF-Godot/addons/gde_gozen/bin/*"
        fi
        mkdir -p "$R/etc/systemd/system/getty@tty1.service.d"
        printf '[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin rock --noclear %%I $TERM\n' > "$R/etc/systemd/system/getty@tty1.service.d/autologin.conf"
        cat >> "$R/home/rock/.profile" <<'PROF'
# Start X on the first console (automatic login); remove this to get a plain shell
if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = /dev/tty1 ]; then exec startx -- -nocursor; fi
PROF
    fi
    in_chroot "chown -R rock:rock /home/rock"
fi
in_chroot "apt-get clean"
rm -rf "$R"/var/lib/apt/lists/* "$R"/home/rock/.cache/uv "$R"/root/.bash_history 2>/dev/null || true

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

proxy_out
# Package manifest for review (before the chroot is torn down)
LC_ALL=C chroot "$R" dpkg-query -W -f='${Package}\t${Version}\t${Installed-Size}\n' > "$OUT/packages.tsv"
umount_chroot

##############################################################################
log "4/6 Partition and populate the image (no loop device)"
rm -rf "$R/boot/firmware"; mkdir -p "$R/boot/firmware"
ROOT_MB=$(( $(du -sm --apparent-size "$R" | cut -f1) + ROOT_PAD_MB ))
IMG="$OUT/$IMG_NAME"
rm -f "$IMG"
# GPT: [0, 16 MiB) is the bootloader (idbloader + U-Boot at sector 64, as the RK3576 boot ROM reads it), then the FAT
# partition "firmware" (kernel, initramfs, device tree, extlinux menu, mpf-network.txt; flagged bootable for U-Boot) and the root.
FW_START=32768; ROOT_START=$(( FW_START + FW_MB * 2048 ))
truncate -s $(( (ROOT_START / 2048 + ROOT_MB + 2) * 1024 * 1024 )) "$IMG"
printf 'label: gpt\nunit: sectors\nfirst-lba: 34\n\n%s,%s,U,*\n%s,,L\n' "$FW_START" $(( FW_MB * 2048 )) "$ROOT_START" | sfdisk -q "$IMG"
dd if="$UBOOT_BIN" of="$IMG" bs=512 seek=64 conv=notrunc status=none
dd if=/dev/zero of="$WORK/fw.img" bs=1M count=$FW_MB status=none
mkfs.vfat -F 32 -n firmware "$WORK/fw.img" >/dev/null
mcopy -s -i "$WORK/fw.img" "$FWDIR"/* ::/
dd if="$WORK/fw.img" of="$IMG" bs=512 seek=$FW_START conv=notrunc status=none; rm -f "$WORK/fw.img"
dd if=/dev/zero of="$WORK/root.img" bs=1M count=0 seek=$ROOT_MB status=none
mke2fs -q -t ext4 -L rootfs -d "$R" "$WORK/root.img"
dd if="$WORK/root.img" of="$IMG" bs=512 seek=$ROOT_START conv=notrunc,sparse status=none; rm -f "$WORK/root.img"
# the data partition of the first boot needs free space after the root: GPT backup header is moved by mpf-persist
sfdisk -d "$IMG" > "$OUT/partition-table.txt"

##############################################################################
log "5/6 Compress"
cd "$OUT"
cp "$UBOOT_BIN" "$OUT/u-boot-rockchip.bin"
xz -T0 -6 -f "$IMG_NAME"
sha256sum "$IMG_NAME.xz" u-boot-rockchip.bin > SHA256SUMS
sha256sum "$IMG_NAME.xz" > "$IMG_NAME.xz.sha256"
log "6/6 Done: $OUT/$IMG_NAME.xz"
cat SHA256SUMS
