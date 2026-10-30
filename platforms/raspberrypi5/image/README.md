# Raspberry Pi 5: minimal image

Builds `rpi5-debian13-sd.img.xz`: Debian 13 (trixie) arm64 `minbase` with the Raspberry Pi 5 kernel
(`linux-image-rpi-2712`, 16 KB pages, `rpi-hevc-dec`), `raspi-firmware` and `firmware-brcm80211` from
archive.raspberrypi.com, no desktop, no docs. Same build and same services as the Pi 4 image
([platforms/raspberrypi/image](../../raspberrypi/image/README.md)): production mode (read-only root, `mpfdata`
partition), Wi-Fi/SSH from `mpf-network.txt` or the page on port 8080, access point `MPF-Setup`, MPF + Godot 4.6.3 + GMC +
GoZen in `/home/pi/MPF-Godot`, autologin and `startx -- -nocursor` on tty1. Login `pi` / `raspberry`.

**Status: built (2026-10-30, in a cloud sandbox under QEMU user emulation), NOT booted on a Pi 5.** See "Tested" below.

## What differs from the Pi 4 image

| | Pi 4 | Pi 5 image |
|---|---|---|
| Kernel / firmware files | `kernel8.img`, `start4.elf`, `bcm2711-rpi-4-b.dtb` | `kernel_2712.img`, `initramfs_2712`, `bcm2712-rpi-5-b.dtb`, `vc4-kms-v3d-pi5` (the bootloader is in the EEPROM) |
| Screens | one (limited, a copy per frame) | **multi-screen like the Jetson**: every connected output on, left to right (two micro-HDMI: backglass and full LCD DMD), [cabinet/xinitrc](../cabinet/xinitrc) |
| DMD | classic DMD forced | the game's own setting (full LCD DMD) |
| Sound | 3.5 mm jack (`snd_bcm2835`) | none on the board: default ALSA device is HDMI output 0 (`vc4hdmi0`, [cabinet/asound.conf](../cabinet/asound.conf)); change it for HDMI-A-2 or a USB card |
| Video decoder | H.264 `bcm2835-codec` (stateful, `GOZEN_HWDEC=1` with a fixed module) | **HEVC only** (`rpi-hevc-dec`, stateless V4L2 request API); no H.264 decoder |
| Game base | | `GODOT` / `MPF_GAME_VENV` in [cabinet/mpf-game.env](../cabinet/mpf-game.env) (as the x86 image) |

## Video: HEVC and hardware decoding

The Pi 5 decodes only HEVC in hardware, through a **stateless** decoder: FFmpeg needs its V4L2-request hwaccel
(the Raspberry Pi patch set, `hevc_v4l2request` / drm_prime frames), not `hevc_v4l2m2m`, which the existing
GoZen build drives (`build/gozen/gozen_v4l2m2m.patch`). Neither Debian's FFmpeg nor this repository's GoZen has it.
Therefore, in this first image:

- `GOZEN_HWDEC=0`: PuP videos (H.264) decode in software on the four Cortex-A76 cores. Not measured.
- Hardware HEVC is a second step: a GoZen build with FFmpeg + the Pi's v4l2-request patches and a dmabuf to EGL path
  (as [fixes/gde-gozen/v4l2m2m-zero-copy.md](../../../fixes/gde-gozen/v4l2m2m-zero-copy.md)), tested on a real Pi 5.
- The videos then have to be HEVC. Converting on the target with x265 (software, a Pi 5 has no encoder) would take
  minutes per video and wear the card; converting once before the install (`ffmpeg -c:v libx265`, audio copied) is the
  recommended place, in the game's PuP install step. Decision pending with the owner.

## Tested

- Built: `rpi5-debian13-sd.img.xz`, 685 MB, sha256 `5577baa0f1af2fc4b433fd281206df02be73a3c37f99588564cc8a16221fb9bf`
  (3.1 GB image: FAT `firmware` 256 MB + ext4 `rootfs`). About 80 min in an x86 sandbox: the packages' install
  scripts run in an arm64 chroot under QEMU user emulation, which dominates.
- Checked statically in the image: partition table, `kernel_2712.img` / `initramfs_2712` / `bcm2712-rpi-5-b.dtb` /
  `vc4-kms-v3d-pi5` present (the build stops otherwise), `config.txt`, `cmdline.txt` (`ro`), kernel modules 6.18.50+rpt-rpi-2712,
  fstab (read-only + tmpfs), services enabled, `/etc/default/mpf-*`, `asound.conf`, `.xinitrc`; MPF 0.80.1, Godot 4.6.3 arm64, GMC 1.0.0 installed.
- **Not tested**: boot on a Pi 5, display, multi-screen layout, sound, Wi-Fi, the setup page, a game upload, video decoding speed.
  A Pi 5 cannot be emulated, so none of this can be checked without the board.

## Build (WSL2 Ubuntu or x86_64 Linux, about 15 GB free)

```bash
cd platforms/raspberrypi5/image/build
sudo bash wsl-build.sh        # work folder ~/pi5-build, output in ~/pi5-build/out/rpi5-debian13-sd.img.xz (+ .sha256)
```

Needs HTTP(S) access to `deb.debian.org`, `security.debian.org`, `archive.raspberrypi.com` and `github.com`
(`archive.raspberrypi.com` is blocked in the cloud sandbox: build on the buildbox). Variables as the Pi 4 image
(`EXTRAS`, `READONLY`, `WIFI_*`, `PI_PASSWORD`). Flash with Raspberry Pi Imager ("Use custom") or
`xzcat img.xz | sudo dd of=/dev/sdX bs=4M status=progress`.
