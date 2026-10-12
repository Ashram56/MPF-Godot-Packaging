#!/bin/bash
# Install every host dependency for flashing L4T 35.6.4 (Xavier NX) from WSL2 Ubuntu or a native Ubuntu host.
#   sudo bash nvme-deps.sh     (safe to re-run)
set -uo pipefail
source "$(dirname "$0")/nx-env.sh"
need_root
export DEBIAN_FRONTEND=noninteractive

echo "== apt packages"
apt-get update
PKGS="abootimg binfmt-support binutils bc cpio cpp device-tree-compiler dosfstools \
 e2fsprogs gdisk parted fdisk kmod iproute2 iputils-ping net-tools usbutils udev util-linux \
 lbzip2 bzip2 xz-utils zstd lz4 rsync mtools openssl openssh-client sshpass \
 uuid-runtime whois xxd libxml2-utils python3 python3-yaml python-is-python3 \
 qemu-user-static nfs-kernel-server tar wget curl sudo"
MISSING=""
for p in $PKGS; do
  apt-get install -y --no-install-recommends "$p" >/dev/null 2>&1 || MISSING="$MISSING $p"
done
[ -n "$MISSING" ] && echo "!! could not install:$MISSING" || echo "all apt packages installed"

echo "== kernel modules (USB network + mass storage used by initrd flash)"
for m in cdc_ether cdc_ncm rndis_host usb_storage; do
  modprobe "$m" 2>/dev/null && echo "ok  $m" || echo "!!  $m not loadable (built in, or missing: WSL has no rndis_host, that is expected)"
done

echo "== systemd/udev (initrd flash needs udev to find the board's disks)"
if [ "$(ps -p 1 -o comm=)" = "systemd" ]; then
  echo "ok  systemd is running"
  systemctl start systemd-udevd 2>/dev/null || true
elif grep -qi microsoft /proc/version; then
  echo "!!  systemd is NOT running in this WSL distro. Enabling it in /etc/wsl.conf."
  grep -q '^\[boot\]' /etc/wsl.conf 2>/dev/null || printf '\n[boot]\n' >> /etc/wsl.conf
  grep -q '^systemd=true' /etc/wsl.conf || sed -i '/^\[boot\]/a systemd=true' /etc/wsl.conf
  echo "    Now run in PowerShell:  wsl --shutdown   then reopen WSL, re-attach the board with usbipd, and run nvme-flash.sh"
else
  echo "!!  systemd is not PID 1; make sure udev is running before flashing"
fi

echo "== L4T's own prerequisites (if the BSP is already extracted)"
[ -x "$L4T/tools/l4t_flash_prerequisites.sh" ] && (cd "$L4T" && ./tools/l4t_flash_prerequisites.sh) || echo "(skipped: BSP not extracted yet; nvme-flash.sh runs it)"

echo "== DONE"
