#!/usr/bin/env bash
# Builds snd-soc-rockchip-sai.ko for the kernel of the image: the RK3576's audio interface (SAI), which Debian's kernel leaves out
# (CONFIG_SND_SOC_ROCKCHIP_SAI is not set), so the board's HDMI sound card never appears. Source: the same driver from the upstream
# tree (tag v7.2), built out of tree against Debian's headers. Cross build on x86_64 Ubuntu 24.04 / Debian 13: the kbuild tools
# of the headers are arm64 programs and run under qemu-user (binfmt registered, as for the image build).
#   KVER=7.2.12+deb13 bash sai-module-build.sh        output: ./sai-out/snd-soc-rockchip-sai.ko and SHA256SUMS
# Host packages: gcc-14-aarch64-linux-gnu make dwarves curl dpkg-dev xz-utils qemu-user-static. Writes the headers into /usr/src (root).
set -euo pipefail
KVER="${KVER:-7.2.12+deb13}"
UPSTREAM_TAG=v7.2
DEB=https://deb.debian.org/debian
WORK="${SAI_WORK:-$PWD/sai-work}"; OUT="${SAI_OUT:-$PWD/sai-out}"
mkdir -p "$WORK" "$OUT"; cd "$WORK"
curl -fsSL "$DEB/dists/trixie-backports/main/binary-arm64/Packages.xz" | xz -dc > Packages
for p in linux-headers-$KVER-arm64 linux-headers-$KVER-common linux-kbuild-$KVER; do
    f="$(awk -v p="Package: $p" '$0==p {f=1} f&&/^Filename:/ {print $2; exit}' Packages)"
    curl -fsSL -o "$p.deb" "$DEB/$f"; dpkg-deb -x "$p.deb" x
done
[ -d "/usr/src/linux-headers-$KVER-arm64" ] || cp -a x/usr/src/linux-headers-$KVER-* /usr/src/
[ -d "/usr/lib/linux-kbuild-$KVER" ] || cp -a "x/usr/lib/linux-kbuild-$KVER" /usr/lib/
mkdir -p mod
for f in rockchip_sai.c rockchip_sai.h; do
    curl -fsSL -o mod/$f "https://raw.githubusercontent.com/torvalds/linux/$UPSTREAM_TAG/sound/soc/rockchip/$f"
done
printf 'obj-m += snd-soc-rockchip-sai.o\nsnd-soc-rockchip-sai-objs := rockchip_sai.o\n' > mod/Kbuild
export QEMU_LD_PREFIX=/usr/aarch64-linux-gnu
make -C "/usr/src/linux-headers-$KVER-arm64" M="$PWD/mod" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_DEBUG_INFO_BTF_MODULES= modules
aarch64-linux-gnu-strip --strip-debug mod/snd-soc-rockchip-sai.ko
aarch64-linux-gnu-strings mod/snd-soc-rockchip-sai.ko | grep -q "^vermagic=$KVER-arm64 " || { echo "wrong vermagic"; exit 1; }
cp mod/snd-soc-rockchip-sai.ko "$OUT/"
(cd "$OUT" && sha256sum snd-soc-rockchip-sai.ko | tee SHA256SUMS)
