# Raspberry Pi 4: minimal image

Builds `rpi4-debian13-sd.img.xz`: Debian 13 (trixie) arm64 `minbase` with the Raspberry Pi kernel (`linux-image-rpi-v8`, `raspi-firmware` and `firmware-brcm80211` from archive.raspberrypi.com, for the V4L2 hardware video decoders)
no desktop, no docs. Counterpart of the Xavier NX image ([platforms/jetson/image](../../jetson/image/README.md)),
but simpler: no vendor BSP, and no loop device is needed (FAT via mtools, ext4 via `mke2fs -d`).

**Status: scripts written, NOT yet run or booted on a board.** Expect a first round of fixes.

| Item | Value |
|---|---|
| Login | `pi` / `raspberry` (`PI_PASSWORD=` at build time), in `sudo`; SSH on port 22 |
| Network | Ethernet by DHCP; Wi-Fi by wpa_supplicant on `wlan0` (`WIFI_SSID`, `WIFI_PSK`, `WIFI_COUNTRY`) |
| First boot | Production mode (default, `READONLY=0` at build time for an ordinary image): root and boot partition read-only, logs in RAM, one small read/write partition `mpfdata` for the game, settings, scores, Wi-Fi and SSH keys, made at the first boot in the free space at the end of the card; unique SSH host keys. `sudo mpf-mode maintenance` (or the page on port 8080, or `MODE=maintenance` in `mpf-network.txt`) makes the system writable for updates: [common/readonly](../../../common/readonly/README.md)
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
No hardware video decoder is wired in yet (the Pi 4 has V4L2 H.264/HEVC decoders; future work).
