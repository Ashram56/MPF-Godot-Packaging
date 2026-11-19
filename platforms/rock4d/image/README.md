# Radxa ROCK 4D: minimal image

Builds `rock4d-debian13-sd.img.xz`: Debian 13 (trixie) arm64 `minbase`, the mainline kernel of trixie-backports (7.2: RK3576, Mali-G52
through Panfrost, rkvdec video decoder, HDMI; Debian's 6.12 has none of the board), a U-Boot built for the board
([build/uboot-build.sh](build/uboot-build.sh)), and the same services as the Raspberry Pi 5 image
([platforms/raspberrypi5/image](../../raspberrypi5/image/README.md)): production mode (read-only root and boot, `mpfdata` partition),
Wi-Fi/SSH from `mpf-network.txt` or the page on port 8080, access point `MPF-Setup`, MPF + Godot 4.6.3 + GMC + GoZen in
`/home/rock/MPF-Godot`, autologin and `startx -- -nocursor` on tty1. Login `rock` / `rock`. Page: [../../rock4d.md](../../rock4d.md).

**Status: built in a cloud sandbox (arm64 under QEMU user emulation), NOT booted on a board.** The board cannot be emulated.

## Layout of the image (GPT)

| Where | What |
|---|---|
| sector 64 | `u-boot-rockchip.bin`: idbloader (Rockchip DDR init) + ATF BL31 + U-Boot (rock-4d-rk3576_defconfig), read by the boot ROM from SD or eMMC |
| partition 1, 384 MB FAT32 `firmware` (bootable) | `/Image`, `/initrd.img`, `/rk3576-rock-4d.dtb`, `/extlinux/extlinux.conf`, `mpf-network.txt` (edit it from any PC) |
| partition 2, ext4 `rootfs` | the system; the `mpfdata` partition is made in the free space after it at the first boot |

`/etc/kernel/postinst.d/zz-mpf-rock4d` refreshes the FAT files on every kernel install (the previous kernel stays as a second menu entry).
Console: debug UART (pins on the 40-pin header, 1500000 baud 8N1) and HDMI.

## Build (WSL2 Ubuntu or x86_64 Linux, about 15 GB free)

```bash
cd platforms/rock4d/image/build
sudo bash wsl-build.sh        # work folder ~/rock4d-build, output in ~/rock4d-build/out/
```

Variables as the Pi 5 image (`EXTRAS`, `READONLY`, `WIFI_*`, `DMD_BRIDGE_TARBALL`), plus `ROCK_PASSWORD`, `UBOOT_BIN` (a U-Boot already
built) and `GOZEN_SO` (the GoZen with the hardware decoder, below). Needs `deb.debian.org`, `security.debian.org`, `github.com` and
`raw.githubusercontent.com` (the Rockchip blobs). Flash: Raspberry Pi Imager / balenaEtcher ("custom image"), or
`xzcat rock4d-debian13-sd.img.xz | sudo dd of=/dev/sdX bs=4M status=progress`. eMMC: from a booted system, or with the USB-C maskrom
mode and `rkdeveloptool`.
