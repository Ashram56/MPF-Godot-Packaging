# Raspberry Pi 4: minimal image

Builds `rpi4-debian13-sd.img.xz`: Debian 13 (trixie) arm64 `minbase` with Debian's own kernel (`linux-image-arm64`)
and `raspi-firmware`, no desktop, no docs. Counterpart of the Xavier NX image ([platforms/jetson/image](../../jetson/image/README.md)),
but simpler: no vendor BSP, and no loop device is needed (FAT via mtools, ext4 via `mke2fs -d`).

**Status: scripts written, NOT yet run or booted on a board.** Expect a first round of fixes.

| Item | Value |
|---|---|
| Login | `pi` / `raspberry` (`PI_PASSWORD=` at build time), in `sudo`; SSH on port 22 |
| Network | Ethernet by DHCP; Wi-Fi by wpa_supplicant on `wlan0` (`WIFI_SSID`, `WIFI_PSK`, `WIFI_COUNTRY`) |
| First boot | root partition grows to fill the card; unique SSH host keys |
| Extras (default on) | `video` GStreamer + FFmpeg (software decode); `x11` Xorg + openbox + Mesa Vulkan (v3dv); `mpf` MPF, Monitor, Godot, GMC via `install/install_linux.sh` in `/home/pi/MPF-Godot`, autologin + `startx` on tty1 |

## Build (WSL2 Ubuntu or x86_64 Linux, about 15 GB free, 20 to 40 minutes)

```bash
cd platforms/raspberrypi/image/build
sudo bash wsl-build.sh        # installs host packages, work folder ~/pi4-build, output in ~/pi4-build/out/
```

`sudo EXTRAS="" bash wsl-build.sh` gives the bare image. Needs HTTPS/HTTP access to `deb.debian.org`,
`security.debian.org` and `github.com`.

Flash the `.img.xz` with Raspberry Pi Imager ("Use custom") or `xzcat img.xz | sudo dd of=/dev/sdX bs=4M status=progress`.
No hardware video decoder is wired in yet (the Pi 4 has V4L2 H.264/HEVC decoders; future work).
