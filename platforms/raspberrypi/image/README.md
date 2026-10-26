# Raspberry Pi 4: minimal image

Builds `rpi4-debian13-sd.img.xz`: Debian 13 (trixie) arm64 `minbase` with the Raspberry Pi kernel (`linux-image-rpi-v8`, `raspi-firmware` and `firmware-brcm80211` from archive.raspberrypi.com, for the V4L2 hardware video decoders)
no desktop, no docs. Counterpart of the Xavier NX image ([platforms/jetson/image](../../jetson/image/README.md)),
but simpler: no vendor BSP, and no loop device is needed (FAT via mtools, ext4 via `mke2fs -d`).

**Status: built and booted on a Pi 4 (Wi-Fi page, game upload, hardware GoZen tested). The image rebuilt for the settings below has not been built yet.**

| Item | Value |
|---|---|
| Login | `pi` / `raspberry` (`PI_PASSWORD=` at build time), in `sudo`; SSH on port 22 |
| Network | Ethernet by DHCP; Wi-Fi by wpa_supplicant on `wlan0` (`WIFI_SSID`, `WIFI_PSK`, `WIFI_COUNTRY`) |
| First boot | Production mode (default, `READONLY=0` at build time for an ordinary image): root and boot partition read-only, logs in RAM, one small read/write partition `mpfdata` for the game, settings, scores, Wi-Fi and SSH keys, made at the first boot in the free space at the end of the card; unique SSH host keys. `sudo mpf-mode maintenance` (or the page on port 8080, or `MODE=maintenance` in `mpf-network.txt`) makes the system writable for updates: [common/readonly](../../../common/readonly/README.md)
| Game | upload the game bundle and the PuP Pack on the setup page (`http://<address>:8080`); the game starts at power-on (`mpf-game.service`) with the ROM's classic DMD, PuP off until a pack is installed |
| Extras (default on) | `video` GStreamer + FFmpeg (software decode); `x11` Xorg + openbox + Mesa Vulkan (v3dv); `mpf` MPF, Monitor, Godot, GMC via `install/install_linux.sh` in `/home/pi/MPF-Godot`, autologin + `startx` on tty1 |

## Wi-Fi and SSH

Edit `mpf-network.txt` on the FAT boot partition (visible from Windows/macOS after flashing), or open `http://<address>:8080`
(login: `pi` and its password). With no network after 90 s the Pi opens a Wi-Fi access point `MPF-Setup` (password `mpf-setup`),
page at `http://192.168.4.1:8080`. Details: [common/netconfig](../../../common/netconfig/README.md). Claude Code is not in the image (install it over SSH).

## Build (WSL2 Ubuntu or x86_64 Linux, about 15 GB free, 20 to 40 minutes)

```bash
cd platforms/raspberrypi/image/build
sudo bash wsl-build.sh        # installs host packages, work folder ~/pi4-build, output in ~/pi4-build/out/
```

`sudo EXTRAS="" bash wsl-build.sh` gives the bare image. Needs HTTPS/HTTP access to `deb.debian.org`,
`security.debian.org`, `archive.raspberrypi.com` and `github.com`.

Flash the `.img.xz` with Raspberry Pi Imager ("Use custom") or `xzcat img.xz | sudo dd of=/dev/sdX bs=4M status=progress`.

## Pi 4 settings (measured, [platforms/raspberrypi.md](../../raspberrypi.md))

The cabinet files in [../cabinet](../cabinet/) hold the measured settings; the image applies what does not depend on the screen or on a kernel build.

| Setting | In the image |
|---|---|
| `snd_bcm2835.enable_headphones=1` (jack sound card) | yes, `cmdline.txt` |
| `/etc/asound.conf`: ALSA default on the jack, no dmix | yes |
| `~/.xinitrc`: one X output (HDMI-2 at 1920x1080 if connected, else HDMI-1), openbox | yes; X starts with `-nocursor` |
| Game arguments `-- --rendering-driver opengl3 --max-fps 30 --audio-output-latency 60` | yes, `/etc/default/mpf-game` (30 FPS cap, 60 ms ALSA latency) |
| `GOZEN_AUDIO_LATENCY=0.087` | yes, `/etc/default/mpf-netconfig` |
| Game base: `/opt/tron-venv` (MPF 0.80.1, pillow, fonttools, psutil), `GODOT` and `MPF_GAME_VENV` in `/etc/default/mpf-game`, `python3-dev` | yes |
| GoZen with the V4L2 hardware decoder and zero-copy (the .so of the repository) | installed over the bundle's own one by the setup page; **not enabled**: `GOZEN_HWDEC=1` is left out |
| Fixed `bcm2835-codec` module ([patch](../cabinet/bcm2835-codec-flush-completion.patch)) | **no**: it is built for one kernel version, outside the image build. Without it a zero-copy decoder oopses when it closes, hence no `GOZEN_HWDEC=1` |
| Godot 4.6.3 with the EGL patch (`--render-thread separate`) | **no**: the image has the official Godot, so the launcher keeps `--render-thread safe` and the main thread is the limit |
| Screen EDID, `video=HDMI-A-2:1920x1080@60D` in `cmdline.txt`, timezone | **no**: they depend on the screen and the owner; edit `cmdline.txt` (FAT partition) |

To switch the hardware decoder on once the module and the patched Godot are installed: add `GOZEN_HWDEC=1` to `/etc/default/mpf-netconfig`, `--render-thread separate` to `MPF_GAME_ARGS`, `GODOT=` to the patched binary, and restart `mpf-game`.
