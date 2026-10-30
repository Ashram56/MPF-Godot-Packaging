# Raspberry Pi 5: minimal image

Builds `rpi5-debian13-sd.img.xz`: Debian 13 (trixie) arm64 `minbase` with the Raspberry Pi 5 kernel
(`linux-image-rpi-2712`, 16 KB pages, `rpi-hevc-dec`), `raspi-firmware` and `firmware-brcm80211` from
archive.raspberrypi.com, no desktop, no docs. Same build and same services as the Pi 4 image
([platforms/raspberrypi/image](../../raspberrypi/image/README.md)): production mode (read-only root, `mpfdata`
partition), Wi-Fi/SSH from `mpf-network.txt` or the page on port 8080, access point `MPF-Setup`, MPF + Godot 4.6.3 + GMC +
GoZen in `/home/pi/MPF-Godot`, autologin and `startx -- -nocursor` on tty1. Login `pi` / `raspberry`.

**Status: scripts written from the Pi 4 image; NOT built, NOT booted on a Pi 5** (see "Tested" below).

## What differs from the Pi 4 image

| | Pi 4 | Pi 5 image |
|---|---|---|
| Kernel / firmware files | `kernel8.img`, `start4.elf`, `bcm2711-rpi-4-b.dtb` | `kernel_2712.img`, `initramfs_2712`, `bcm2712-rpi-5-b.dtb`, `vc4-kms-v3d-pi5` (the bootloader is in the EEPROM) |
| Screens | one (limited, a copy per frame) | **multi-screen like the Jetson**: every connected output on, left to right (two micro-HDMI: backglass and full LCD DMD), [cabinet/xinitrc](../cabinet/xinitrc) |
| DMD | classic DMD forced | the game's own setting (full LCD DMD) |
| Sound | 3.5 mm jack (`snd_bcm2835`) | none on the board: HDMI audio or USB sound card; not configured yet |
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

## Build (WSL2 Ubuntu or x86_64 Linux, about 15 GB free)

```bash
cd platforms/raspberrypi5/image/build
sudo bash wsl-build.sh        # work folder ~/pi5-build, output in ~/pi5-build/out/rpi5-debian13-sd.img.xz (+ .sha256)
```

Needs HTTP(S) access to `deb.debian.org`, `security.debian.org`, `archive.raspberrypi.com` and `github.com`
(`archive.raspberrypi.com` is blocked in the cloud sandbox: build on the buildbox). Variables as the Pi 4 image
(`EXTRAS`, `READONLY`, `WIFI_*`, `PI_PASSWORD`). Flash with Raspberry Pi Imager ("Use custom") or
`xzcat img.xz | sudo dd of=/dev/sdX bs=4M status=progress`.
