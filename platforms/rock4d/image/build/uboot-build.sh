#!/usr/bin/env bash
# Builds the ROCK 4D (RK3576) bootloader: mainline U-Boot with the board's own defconfig (rock-4d-rk3576) and Rockchip's
# DDR init (TPL) and ARM Trusted Firmware (BL31) blobs from rockchip-linux/rkbin, both pinned and checked.
# Output (UBOOT_OUT, default ./uboot-out): u-boot-rockchip.bin (for an SD card or eMMC: written at sector 64),
# u-boot-rockchip-spi.bin (for the SPI NOR flash; the image does not use it) and the sha256 of both.
# Needs: gcc-aarch64-linux-gnu make bison flex swig device-tree-compiler python3-pyelftools python3-setuptools libssl-dev
# libgnutls28-dev bc curl, and HTTPS access to deb.debian.org and raw.githubusercontent.com.
set -euo pipefail
UBOOT_VER="2026.10~rc5"
UBOOT_URL="https://deb.debian.org/debian/pool/main/u/u-boot/u-boot_${UBOOT_VER}.orig.tar.gz"
UBOOT_SHA256=fd7102f0a26792f89b1fe6752dd62290c6e57d36254fbf05188000c55a624666
RKBIN_REV=3e288fe814e059dd06833495f845cab04ac20a5c
BL31_NAME=rk3576_bl31_v1.25.elf
BL31_SHA256=a709eb309746a46c192405fe95b725a668c20ee05b134478838a69e723bfafb2
TPL_NAME=rk3576_ddr_lp4_2112MHz_lp5_2736MHz_v1.13.bin
TPL_SHA256=f697151bdd09d31bf7a1e49d63796a6a200e81bf8f9a766c2e95c840e88fc0ce
WORK="${UBOOT_WORK:-$PWD/uboot-work}"
OUT="${UBOOT_OUT:-$PWD/uboot-out}"
mkdir -p "$WORK" "$OUT"
cd "$WORK"
if [ ! -f u-boot.tar.gz ]; then curl -fsSL -o u-boot.tar.gz "$UBOOT_URL"; fi
echo "$UBOOT_SHA256  u-boot.tar.gz" | sha256sum -c -
for f in "$BL31_NAME:$BL31_SHA256" "$TPL_NAME:$TPL_SHA256"; do
    n="${f%%:*}"
    [ -f "$n" ] || curl -fsSL -o "$n" "https://raw.githubusercontent.com/rockchip-linux/rkbin/$RKBIN_REV/bin/rk35/$n"
    echo "${f##*:}  $n" | sha256sum -c -
done
rm -rf src && mkdir src && tar -xzf u-boot.tar.gz -C src --strip-components=1
cd src
export BL31="$WORK/$BL31_NAME" ROCKCHIP_TPL="$WORK/$TPL_NAME"
make -s CROSS_COMPILE=aarch64-linux-gnu- rock-4d-rk3576_defconfig
make -s -j"$(nproc)" CROSS_COMPILE=aarch64-linux-gnu- 2>&1 | grep -v -E 'tee-os|OP-TEE|documentation for your board|^$|simple-bin' || true
for f in u-boot-rockchip.bin u-boot-rockchip-spi.bin; do
    [ -s "$f" ] || { echo "$f was not built"; exit 1; }
    cp "$f" "$OUT/"
done
(cd "$OUT" && sha256sum u-boot-rockchip.bin u-boot-rockchip-spi.bin > SHA256SUMS && cat SHA256SUMS)
