#!/usr/bin/env bash
# Builds rockchip-vdec.ko (the rkvdec stateless video decoder) for the kernel of the image, with the RK3576 power-up priming patch:
# on a ROCK 4D (RK3576, VDPU383) the mainline driver decodes cold after each power-up and about 30-40 % of the power-ups give wrong
# pictures (luma and chroma, the whole clip) until the next power-down. The Rockchip BSP runs a priming decode at every power-up;
# the patch (S. Wright, linux-rockchip list, 2026-06) ports it. Source: tag v7.2 of the upstream tree + that patch, built out of tree
# against Debian's headers; the module replaces the kernel's own (install it to /lib/modules/$KVER/updates/, then depmod).
#   KVER=7.2.12+deb13 bash rkvdec-module-build.sh      output: ./rkvdec-out/rockchip-vdec.ko and SHA256SUMS
# Host packages and binfmt: as sai-module-build.sh.
set -euo pipefail
KVER="${KVER:-7.2.12+deb13}"
TAG=v7.2
PATCH_URL=https://raw.githubusercontent.com/SympleNZ/rkvdec-vdpu383-h264-bug/master/fix/0001-media-rkvdec-prime-VDPU383-deblock-warmup-rk3576.patch
PATCH_SHA256="${PATCH_SHA256:-$(cat "$(dirname "$0")/files/rkvdec-warmup.patch.sha256" 2>/dev/null || true)}"
DEB=https://deb.debian.org/debian
WORK="${RKVDEC_WORK:-$PWD/rkvdec-work}"; OUT="${RKVDEC_OUT:-$PWD/rkvdec-out}"
mkdir -p "$WORK" "$OUT"; cd "$WORK"
curl -fsSL "$DEB/dists/trixie-backports/main/binary-arm64/Packages.xz" | xz -dc > Packages
for p in linux-headers-$KVER-arm64 linux-headers-$KVER-common linux-kbuild-$KVER; do
    f="$(awk -v p="Package: $p" '$0==p {f=1} f&&/^Filename:/ {print $2; exit}' Packages)"
    [ -f "$p.deb" ] || curl -fsSL -o "$p.deb" "$DEB/$f"; dpkg-deb -x "$p.deb" x
done
[ -d "/usr/src/linux-headers-$KVER-arm64" ] || cp -a x/usr/src/linux-headers-$KVER-* /usr/src/
[ -d "/usr/lib/linux-kbuild-$KVER" ] || cp -a "x/usr/lib/linux-kbuild-$KVER" /usr/lib/
rm -rf mod; mkdir -p mod; T=https://raw.githubusercontent.com/torvalds/linux/$TAG/drivers/media/platform/rockchip/rkvdec
curl -fsSL -o mod/Makefile $T/Makefile
for f in $(grep -o 'rkvdec[a-z0-9-]*\.o' mod/Makefile | sed 's/\.o$//' | sort -u); do curl -fsSL -o mod/$f.c $T/$f.c; done
for i in 1 2 3; do for h in $(grep -ho '#include "[^"]*"' mod/*.c mod/*.h 2>/dev/null | sed 's/#include "//;s/"//' | sort -u); do
    [ -f mod/$h ] || curl -fsSL -o mod/$h $T/$h; done; done
curl -fsSL -o fix.patch "$PATCH_URL"
[ -z "$PATCH_SHA256" ] || echo "$PATCH_SHA256  fix.patch" | sha256sum -c -
mkdir -p tree/drivers/media/platform/rockchip && rm -rf tree/drivers/media/platform/rockchip/rkvdec && cp -r mod tree/drivers/media/platform/rockchip/rkvdec
(cd tree && patch -p1 < ../fix.patch)
cd tree/drivers/media/platform/rockchip/rkvdec
# out-of-tree Kbuild: the module name of the kernel's own driver, built as a module whatever the kernel's config says
sed -i 's/^obj-\$(CONFIG_VIDEO_ROCKCHIP_VDEC)/obj-m/' Makefile
export QEMU_LD_PREFIX=/usr/aarch64-linux-gnu
make -C "/usr/src/linux-headers-$KVER-arm64" M="$PWD" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CONFIG_DEBUG_INFO_BTF_MODULES= modules
aarch64-linux-gnu-strip --strip-debug rockchip-vdec.ko
STR="$(aarch64-linux-gnu-strings rockchip-vdec.ko)"
grep -q "^vermagic=$KVER-arm64 " <<<"$STR" || { echo "wrong vermagic"; exit 1; }
grep -q "deblock-priming" <<<"$STR" || { echo "the priming patch is not in the module"; exit 1; }
cp rockchip-vdec.ko "$OUT/"
(cd "$OUT" && sha256sum rockchip-vdec.ko | tee SHA256SUMS)
