#!/usr/bin/env bash
# Build a minimal Jetson Xavier NX SD card image (L4T 35.6.4 + Ubuntu 20.04 arm64)
# natively, without podman/docker. Derived from https://github.com/pythops/jetson-image
# (Containerfile.rootfs.20_04 + Containerfile.image.l4t35), trimmed to a minimal system.
#
# Run as root on an x86_64 Ubuntu 22.04/24.04 host with ~25 GB free disk:
#   sudo ./build-native.sh
# Optional environment:
#   WORK=/path/to/workdir      (default: ./work)
#   WIFI_SSID=... WIFI_PSK=... pre-seed one Wi-Fi network (stored hashed via wpa_passphrase)
#   WIFI_COUNTRY=FR            regulatory country code for Wi-Fi (default: unset = world domain)
#   JETSON_PASSWORD=...        password for user "jetson" (default: jetson)
#   EXTRAS="video docker x11"  optional feature groups to add (default: all three; EXTRAS="" for the bare image)
#       video  : GStreamer + NVIDIA hardware decode/encode plugins, NVIDIA FFmpeg build (nvv4l2 codecs)
#       docker : docker.io + NVIDIA container runtime (default runtime), jetson user in docker group
#       x11    : Xorg with NVIDIA driver, xinit/startx, openbox window manager, xrandr, xterm, Vulkan loader
# Output: $WORK/out/jetson-xavier-nx-l4t35.6.4-sd.img.xz and .sha256

set -euo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$PWD/work}"
BSP_URL="https://developer.download.nvidia.com/embedded/L4T/r35_Release_v6.4/release/Jetson_Linux_R35.6.4_aarch64.tbz2"
UBUNTU_MIRROR="http://ports.ubuntu.com/ubuntu-ports"
BOARD="jetson-xavier-nx-devkit"   # flash config name for the Xavier NX devkit (SD card module P3668-0000)
SOC="t194"
IMG_NAME="jetson-xavier-nx-l4t35.6.4-sd.img"
JETSON_PASSWORD="${JETSON_PASSWORD:-jetson}"
EXTRAS="${EXTRAS-video docker x11}"

L4T="$WORK/Linux_for_Tegra"
R="$L4T/rootfs"
OUT="$WORK/out"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
in_chroot() { LC_ALL=C DEBIAN_FRONTEND=noninteractive chroot "$R" /usr/bin/env bash -c "$*"; }

mount_chroot() {
    mountpoint -q "$R/proc" || mount -t proc proc "$R/proc"
    mountpoint -q "$R/sys" || mount -t sysfs sys "$R/sys"
    mountpoint -q "$R/dev" || mount -o bind /dev "$R/dev"
    mountpoint -q "$R/dev/pts" || mount -o bind /dev/pts "$R/dev/pts"
    # temporary DNS for apt inside the chroot
    if [ -L "$R/etc/resolv.conf" ] || [ -e "$R/etc/resolv.conf" ]; then
        mv "$R/etc/resolv.conf" "$R/etc/resolv.conf.build-bak"
    fi
    cp -L /etc/resolv.conf "$R/etc/resolv.conf"
    # never start services inside the chroot
    printf '#!/bin/sh\nexit 101\n' > "$R/usr/sbin/policy-rc.d"; chmod 755 "$R/usr/sbin/policy-rc.d"
}

umount_chroot() {
    rm -f "$R/usr/sbin/policy-rc.d"
    for m in dev/pts dev sys proc; do
        mountpoint -q "$R/$m" && umount "$R/$m"
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
log "1/7 Host dependencies and arm64 emulation"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    debootstrap qemu-user-static binfmt-support curl patch bzip2 xz-utils lz4 \
    libxml2-utils python3 python3-yaml python-is-python3 gdisk parted cpio binutils \
    dosfstools mtools e2fsprogs openssh-client >/dev/null
mountpoint -q /proc/sys/fs/binfmt_misc || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
if [ ! -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]; then
    update-binfmts --enable qemu-aarch64 2>/dev/null || cat /usr/lib/binfmt.d/qemu-aarch64.conf > /proc/sys/fs/binfmt_misc/register
fi

##############################################################################
log "2/7 NVIDIA L4T 35.6.4 BSP"
if [ ! -x "$L4T/apply_binaries.sh" ]; then
    curl -fL --retry 4 -o "$WORK/bsp.tbz2" "$BSP_URL"
    tar -xjpf "$WORK/bsp.tbz2" -C "$WORK"
    rm -f "$WORK/bsp.tbz2"
fi

##############################################################################
log "3/7 Minimal Ubuntu 20.04 arm64 rootfs"
if [ ! -x "$R/bin/bash" ]; then
    debootstrap --arch=arm64 --variant=minbase focal "$R" "$UBUNTU_MIRROR"
fi
cat > "$R/etc/apt/sources.list" <<EOF
deb $UBUNTU_MIRROR focal main restricted universe multiverse
deb $UBUNTU_MIRROR focal-updates main restricted universe multiverse
deb $UBUNTU_MIRROR focal-security main restricted universe multiverse
# bionic is needed for libffi6 (NVIDIA multimedia libraries link against it)
deb $UBUNTU_MIRROR bionic main
EOF
# Never let bionic replace focal packages
cat > "$R/etc/apt/preferences.d/bionic-low" <<'EOF'
Package: *
Pin: release n=bionic
Pin-Priority: 100
EOF
# Keep the image small: no docs, man pages or translations
cat > "$R/etc/dpkg/dpkg.cfg.d/excludes" <<'EOF'
path-exclude=/usr/share/doc/*
path-include=/usr/share/doc/*/copyright
path-exclude=/usr/share/man/*
path-exclude=/usr/share/info/*
path-exclude=/usr/share/locale/*
path-include=/usr/share/locale/locale.alias
EOF
printf 'APT::Install-Recommends "false";\nAPT::Install-Suggests "false";\n' > "$R/etc/apt/apt.conf.d/99norecommends"

# On re-runs, keep NVIDIA's repo out of the base stage so apt never upgrades the L4T 35.6.4 packages
NV_LIST="$R/etc/apt/sources.list.d/nvidia-l4t-apt-source.list"
[ -e "$NV_LIST" ] && mv "$NV_LIST" "$WORK/nvidia-l4t-apt-source.list.saved"
mount_chroot
in_chroot "apt-get update -qq && apt-get -y -qq upgrade"

# Packages that NVIDIA's L4T debs depend on (unchanged from upstream pythops recipe)
NVIDIA_DEPS="libgles2 libpangoft2-1.0-0 libxkbcommon0 libwayland-egl1 libwayland-cursor0
  libunwind8 libasound2 libpixman-1-0 libjpeg-turbo8 libinput10 libcairo2
  device-tree-compiler iso-codes libffi6 libncursesw5 libdrm-common libdrm2
  libegl-mesa0 libegl1 libegl1-mesa libgtk-3-0 python2 python-is-python2
  libgstreamer1.0-0 libgstreamer-plugins-bad1.0-0 i2c-tools bridge-utils
  python3 libnl-genl-3-200 libnl-route-3-200"
# Tools NVIDIA's image tooling copies out of the rootfs into the recovery initrd
RECOVERY_DEPS="mtd-utils isc-dhcp-client xxd"
# Bare-minimum system
SYSTEM_PKGS="systemd systemd-sysv dbus udev kmod sudo locales ca-certificates openssh-server
  iproute2 iputils-ping curl nano parted fdisk gdisk e2fsprogs openssl less"
# Wi-Fi: wpa_supplicant (iwd cannot run on the L4T kernel: CONFIG_CRYPTO_USER_API_HASH is not set)
WIFI_PKGS="wpasupplicant iw rfkill wireless-regdb"

in_chroot "apt-get install -y -qq $(echo $SYSTEM_PKGS $NVIDIA_DEPS $RECOVERY_DEPS $WIFI_PKGS) linux-firmware"

# linux-firmware is ~700 MB: keep only the Intel 8265/8000C Wi-Fi blobs, drop the rest.
# (The devkit's Realtek RTL8822CE Wi-Fi/BT firmware comes from NVIDIA's nvidia-l4t-firmware deb.)
in_chroot 'mkdir -p /tmp/fw && cp -a /lib/firmware/iwlwifi-8265-* /lib/firmware/iwlwifi-8000C-* /tmp/fw/ &&
  apt-get purge -y -qq linux-firmware && apt-get autoremove -y -qq --purge &&
  mkdir -p /lib/firmware && cp -a /tmp/fw/. /lib/firmware/ && rm -rf /tmp/fw'

# tegratop: small TUI monitor from the upstream author (optional, prebuilt arm64 binary)
curl -fsSL https://github.com/pythops/tegratop/releases/latest/download/tegratop-linux-arm64 -o "$R/usr/local/bin/tegratop" \
    && chmod +x "$R/usr/local/bin/tegratop" || echo "warning: tegratop download failed, skipping"

# Grow the root partition to fill the SD card on boot
install -m 755 "$KIT/files/resizerootfs.sh" "$R/usr/local/bin/resizerootfs.sh"
install -m 644 "$KIT/files/resizerootfs.service" "$R/lib/systemd/system/resizerootfs.service"

# Hostname, locale
echo jetson > "$R/etc/hostname"
printf '127.0.0.1\tlocalhost\n127.0.1.1\tjetson\n::1\tlocalhost ip6-localhost ip6-loopback\n' > "$R/etc/hosts"
in_chroot "locale-gen en_US.UTF-8 >/dev/null && update-locale LANG=en_US.UTF-8"

# Networking: systemd-networkd + resolved. Wired preferred over Wi-Fi via route metric.
# Interfaces are named eth0/wlan0 because L4T boots with net.ifnames=0.
mkdir -p "$R/etc/systemd/network"
printf '[Match]\nName=eth* en*\n\n[Network]\nDHCP=yes\n\n[DHCP]\nRouteMetric=100\n' > "$R/etc/systemd/network/20-wired.network"
printf '[Match]\nName=wlan* wl*\n\n[Network]\nDHCP=yes\n\n[DHCP]\nRouteMetric=600\n' > "$R/etc/systemd/network/25-wireless.network"
ln -sf /run/systemd/resolve/stub-resolv.conf "$R/etc/resolv.conf.build-bak"   # becomes /etc/resolv.conf on unmount

# Wi-Fi: wpa_supplicant bound to wlan0. Add networks later with:
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
# The generic D-Bus wpa_supplicant.service is not needed (wpa_supplicant@wlan0 runs it directly)
in_chroot "systemctl disable wpa_supplicant.service >/dev/null 2>&1 || true"

# User jetson / password (default "jetson"), in sudo
in_chroot "id jetson >/dev/null 2>&1 || useradd --create-home -G sudo,video,audio -p \"\$(openssl passwd -6 '$JETSON_PASSWORD')\" -s /bin/bash jetson"
printf 'if [ -d "/usr/local/cuda/bin" ] ; then\n  PATH="/usr/local/cuda/bin:$PATH"\nfi\n' >> "$R/home/jetson/.profile"

in_chroot "apt-get clean"
rm -rf "$R"/var/lib/apt/lists/* "$R"/root/.bash_history
umount_chroot
[ -e "$WORK/nvidia-l4t-apt-source.list.saved" ] && mv "$WORK/nvidia-l4t-apt-source.list.saved" "$NV_LIST"

##############################################################################
log "4/7 NVIDIA patches (upstream pythops + build-host independence)"
cd "$L4T"
chmod 4755 "$R/usr/bin/sudo"
if [ ! -e nv_tegra/.patched ]; then
    patch nv_tegra/nv-apply-debs.sh < "$KIT/files/patches/nv-apply-debs.diff"
    patch tools/jetson-disk-image-creator.sh < "$KIT/files/patches/agx-orin.diff"
    # Write partitions with dd at GPT offsets instead of loop/kpartx (no device-mapper needed),
    # and fill the EFI system partition with mtools instead of mounting vfat.
    python3 - <<'PYEOF'
import re
p = 'tools/jetson-disk-image-creator.sh'; s = open(p).read()
s = s.replace('\tloop_dev="$(losetup --show -f -P "${sd_blob_name}")"\n', '')
s = s.replace('\t\t\tsudo dd if="${target_file}" of="${loop_dev}p${part_num}"\n',
'''\t\t\tstart="$(sgdisk -i "${part_num}" "${sd_blob_name}" | awk '/^First sector/ {print $3}')"
\t\t\tlast="$(sgdisk -i "${part_num}" "${sd_blob_name}" | awk '/^Last sector/ {print $3}')"
\t\t\tif [ "$(stat -c %s "${target_file}")" -gt $(( (last - start + 1) * 512 )) ]; then echo "ERROR: ${target_file} too big for partition ${part_num}"; exit 1; fi
\t\t\tdd if="${target_file}" of="${sd_blob_name}" bs=512 seek="${start}" conv=sync,notrunc status=none
''')
s = re.sub(r'\n\tlosetup -d "\$\{loop_dev\}"\n\tloop_dev=""\n', '\n', s)
assert 'seek="${start}"' in s and 'losetup --show -f -P' not in s, 'creator patch failed'
open(p, 'w').write(s)

p = 'flash.sh'; s = open(p).read()
i = s.index('\tesp_mnt_dir="espmnt";\n')
j = s.index('\techo -e -n "\\tSync\'ing ${esp_img_name} ... ";', i)
s = s[:i] + ('\tmmd -i "${esp_loop_dev}" ::/EFI ::/EFI/BOOT; chkerr "make ${esp_img_name}/EFI/BOOT failed.";\n'
             '\tmcopy -i "${esp_loop_dev}" "${efi_file}" ::/EFI/BOOT/BOOTAA64.efi;\n'
             '\tchkerr "Copying ${efi_file} to BOOTAA64.efi failed.";\n') + s[j:]
s = s.replace('\tumount "${esp_mnt_dir}" > /dev/null 2>&1;\n', '').replace('\trmdir "${esp_mnt_dir}" > /dev/null 2>&1;\n', '')
open(p, 'w').write(s)
PYEOF
    touch nv_tegra/.patched
fi
# Drop GUI tools
rm -f nv_tegra/l4t_deb_packages/nvidia-l4t-nvpmodel-gui-tools*.deb \
      nv_tegra/l4t_deb_packages/nvidia-l4t-jetsonpower-gui-tools*.deb \
      tools/python-jetson-gpio_*_arm64.deb

##############################################################################
log "5/7 Install NVIDIA L4T packages into the rootfs (apply_binaries.sh)"
./apply_binaries.sh
# Point NVIDIA's apt repo at the Xavier (t194) packages
sed -i "s/<SOC>/$SOC/" "$R/etc/apt/sources.list.d/nvidia-l4t-apt-source.list"
echo jetson > "$R/etc/hostname"
in_chroot "chown -R jetson:jetson /home/jetson && chmod 1777 /tmp"
# Remove unneeded NVIDIA services for a headless image (Weston desktop)
in_chroot "systemctl disable nvweston.service >/dev/null 2>&1 || true"

# Optional extra L4T packages (e.g. CUDA) could be installed here with the chroot mounted:
#   mount_chroot; in_chroot "apt-get update && apt-get install -y cuda-toolkit-11-4"; umount_chroot

##############################################################################
log "5b/7 Optional feature groups: ${EXTRAS:-none}"
has() { case " $EXTRAS " in *" $1 "*) return 0;; *) return 1;; esac; }
if [ -n "$EXTRAS" ]; then
    mount_chroot
    in_chroot "apt-get update -qq"   # Ubuntu + NVIDIA jetson repos (common, t194, ffmpeg)
    if has video; then
        # NVIDIA's nvv4l2decoder/nvv4l2h264enc etc. come from nvidia-l4t-gstreamer (already installed);
        # these add the GStreamer core tools and the demux/parse elements pipelines need (qtdemux, h264parse...).
        in_chroot "apt-get install -y -qq gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-alsa v4l-utils"
        # FFmpeg 4.2.7 rebuilt by NVIDIA with h264/hevc nvv4l2 decoders (from repo.download.nvidia.com/jetson/ffmpeg)
        printf 'Package: ffmpeg\nPin: origin repo.download.nvidia.com\nPin-Priority: 1001\n' > "$R/etc/apt/preferences.d/nvidia-ffmpeg"
        in_chroot "apt-get install -y -qq ffmpeg"
    fi
    if has docker; then
        in_chroot "apt-get install -y -qq docker.io nvidia-container"
        mkdir -p "$R/etc/docker"
        cat > "$R/etc/docker/daemon.json" <<'JSON'
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    },
    "default-runtime": "nvidia"
}
JSON
        in_chroot "usermod -aG docker jetson && systemctl enable docker.service containerd.service >/dev/null 2>&1"
    fi
    if has x11; then
        # Xorg core + NVIDIA's Xorg driver (nvidia-l4t-x11/3d-core, already installed), no desktop.
        in_chroot "apt-get install -y -qq xserver-xorg-core xserver-xorg-input-libinput xinit x11-xserver-utils xauth openbox xterm libpam-systemd \
            libvulkan1 libxcursor1 libxinerama1 libxrandr2 libxi6 libxext6 libxrender1 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3"
        # Allow "startx" from a console login for the jetson user
        printf 'allowed_users=console\nneeds_root_rights=auto\n' > "$R/etc/X11/Xwrapper.config"
        cat > "$R/home/jetson/.xinitrc" <<'XRC'
#!/bin/sh
# Edit to taste. Extend the desktop across all connected outputs (HDMI + DP), left to right:
prev=""
for out in $(xrandr | awk '/ connected/ {print $1}'); do
    if [ -z "$prev" ]; then xrandr --output "$out" --auto --primary; else xrandr --output "$out" --auto --right-of "$prev"; fi
    prev="$out"
done
exec openbox-session
XRC
        chmod 755 "$R/home/jetson/.xinitrc"; in_chroot "chown jetson:jetson /home/jetson/.xinitrc"
        in_chroot "usermod -aG video,render,input,tty jetson 2>/dev/null || usermod -aG video,input,tty jetson"
    fi
    in_chroot "apt-get clean"
    rm -rf "$R"/var/lib/apt/lists/*
    umount_chroot
fi

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

# Initrd DNS fix from upstream
TMPI="$WORK/initrd-edit"; rm -rf "$TMPI"; mkdir -p "$TMPI/lab"
gzip -d -c bootloader/l4t_initrd.img > "$TMPI/initrd"
( cd "$TMPI/lab" && cpio -i --quiet < ../initrd && echo "nameserver 127.0.0.53" > etc/resolv.conf \
  && find . | cpio --create --quiet --format=newc | gzip > ../new_initrd.gz )
cp "$TMPI/new_initrd.gz" bootloader/l4t_initrd.img
rm -rf "$TMPI"

##############################################################################
log "6/7 Create the SD card image"
cd "$L4T/tools"
rm -f jetson.img
USER=root ./jetson-disk-image-creator.sh -o jetson.img -b "$BOARD" -d SD
mv jetson.img "$OUT/$IMG_NAME"

##############################################################################
log "7/7 Compress"
cd "$OUT"
# package manifest for review
LC_ALL=C chroot "$R" dpkg-query -W -f='${Package}\t${Version}\t${Installed-Size}\n' > "$OUT/packages.tsv"
xz -T0 -6 -f "$IMG_NAME"
sha256sum "$IMG_NAME.xz" > "$IMG_NAME.xz.sha256"
log "Done: $OUT/$IMG_NAME.xz"
cat "$IMG_NAME.xz.sha256"
