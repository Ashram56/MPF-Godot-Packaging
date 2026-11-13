# Raspberry Pi Zero W: the topper image

`build-zero.sh` builds `rpi-zero-topper.img.xz`: a flashable image that turns a **Pi Zero W (v1.1, ARMv6)** into the game's
remote topper ([platforms/pup-remote-topper.md](../../pup-remote-topper.md)). It is the official Raspberry Pi OS Lite
32-bit (Raspbian trixie armhf: Debian's own armhf needs ARMv7 and does not run on a Zero) with **mpv** and the
`pup-topper` agent already installed and started at boot.

**No video is in the image.** Under game format 2 the PuP Pack is never in a bundle or an image; the topper downloads the
videos from the running game at each connection. **Nothing is installed or generated on the Pi** (game-bundles.md, rules 12 and 13):
the one `apt-get install` is done here, at build time.

## Use

1. Flash `rpi-zero-topper.img.xz` (Raspberry Pi Imager, "Use custom", or `xzcat ... | sudo dd of=/dev/sdX bs=4M`).
2. On the card's boot partition (visible from Windows or macOS), edit:
   - `network-config`: your Wi-Fi name and password (2.4 GHz; netplan syntax, spaces not tabs),
   - `user-data`: hostname (default `pup-topper`), password of user `pi` (default `raspberry`: change it), SSH key,
   - `pup-topper.cfg`: the agent's settings (`host=auto` finds the game; `fit`, `align`, `audio`, `download`).
3. Put the card in the Pi, HDMI to the topper screen, power on. In the game, turn the remote screens on (`[remote] enabled`).

The first boot sets the hostname, the user and the Wi-Fi (cloud-init, the base image's own mechanism), then the service
`pup-topper` runs. Log: `journalctl -u pup-topper -f`. Downloaded videos: `/var/lib/pup-topper/media`.

## Build (x86_64 Linux or WSL2, root, about 8 GB, 10 to 20 minutes)

```bash
sudo bash platforms/raspberrypi/zero/build-zero.sh      # work folder ./work-zero, output in work-zero/out/
```

It needs Internet: `downloads.raspberrypi.com` (the base image, checksum-checked) and the Raspbian package mirrors
(`raspbian.raspberrypi.com` redirects to third-party mirrors; a sandbox that allows only that host cannot fetch the `.deb`
files, mpv comes from there). Steps: the base image grows by 600 MB; qemu-user emulates the ARM chroot where `apt-get
install mpv` runs; the agent (`topper.py`, `screen_rules.py` from this repository) and its service are copied; the boot
partition files are written with mtools (no loop device for FAT). `SKIP_PACKAGES=1` builds without the mpv step (tests).

## Checked

Built and structure-checked in a sandbox without the mirrors (`SKIP_PACKAGES=1`): the image has the agent, service enabled,
boot-partition files; the ARMv6 kernel 6.18 boots to userspace under QEMU `raspi0` (see below); the agent runs under qemu-user
against a game server. **Not checked:** the mpv install and the topper on a real Zero W (hardware decode `v4l2m2m-copy`, smooth playback,
Wi-Fi association, memory).

## Boot check under QEMU (no Pi needed)

QEMU's `raspi0` runs the Zero's ARMv6 kernel from the image. It emulates neither the power manager nor the Wi-Fi chip, so
two drivers are blacklisted and the console is the first UART; expect it to be slow (minutes to reach the login):

```bash
mcopy -i rpi-zero-topper.img@@$((16384*512)) ::kernel.img ::bcm2708-rpi-zero-w.dtb .      # MTOOLS_SKIP_CHECK=1
truncate -s 4G rpi-zero-topper.img      # the SD card size must be a power of two
qemu-system-arm -M raspi0 -m 512 -kernel kernel.img -dtb bcm2708-rpi-zero-w.dtb -display none -serial stdio \
  -drive file=rpi-zero-topper.img,if=sd,format=raw \
  -append "earlycon=pl011,mmio32,0x20201000 console=ttyAMA0,115200 root=/dev/mmcblk0p2 rootwait rw initcall_blacklist=bcm2835_pm_driver_init,bcm2835_wdt_driver_init"
```

Without `earlycon=...` there is no output at all; without the blacklist the kernel oopses in `bcm2835_pm_probe` and the boot
stops; without `rw` the root stays read-only and systemd cannot start. The `pup-topper` agent can also be run on its own
under `qemu-arm-static` in a chroot of the image (Python 3.13, ARM): `sync_media` against a game server worked.
