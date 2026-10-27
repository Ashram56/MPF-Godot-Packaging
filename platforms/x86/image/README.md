# x86_64 mini PC: minimal UEFI image

Builds `x86-debian13-uefi.img.xz`: Debian 13 (trixie) amd64 `minbase` with Debian's kernel (`linux-image-amd64`), no desktop, no docs.
Made for mini PCs with an Intel N-series or recent Core / AMD GPU, first the Nipogi AK2PLUS (Intel N100): the VAAPI
drivers (`intel-media-va-driver`, `mesa-va-drivers`) are in, and the game's GoZen decodes the PuP videos with them
([hwdec-vaapi-linux-x86](../../../fixes/gde-gozen/hwdec-vaapi-linux-x86.md)). Counterpart of the Raspberry Pi 4 image
([platforms/raspberrypi/image](../../raspberrypi/image/README.md)), simpler to build: the host has the same architecture, so no emulation, and no
loop device is needed (FAT via mtools, ext4 via `mke2fs -d`).

**Status 2026-10-27: built, installed and booted under QEMU + OVMF** (cloud sandbox): the stick shows the installer menu, `mpf-install-to-disk` copies to a
second virtual disk, that disk alone boots (GRUB, kernel 6.12, root grown, DHCP, SSH, setup page on 8080, X session on tty1). Image 1.1 GB compressed,
4.3 GB raw. Not yet checked on the AK2PLUS beyond the first (stick) run: VAAPI untested (QEMU has no Intel GPU). Behind a TLS-inspecting proxy the build gives the chroot
the proxy and its CA while the installers run (removed again).

| Item | Value |
|---|---|
| Login | `mpf` / `mpf` (`MPF_PASSWORD=` at build time), in `sudo`; SSH on port 22 |
| Boot | UEFI only (GPT, 256 MB FAT32 "firmware" ESP + ext4 "rootfs"); a standalone GRUB EFI file with its configuration inside (in a standalone GRUB the ESP is not the loader's own directory, so nothing can be read next to it): `EFI/BOOT/BOOTX64.EFI` finds the root partition labelled `rootfs` (the stick) and starts `/vmlinuz`; `EFI/BOOT/mpf-disk.efi` does the same for `mpfroot` and the installer copies it over `BOOTX64.EFI` of the internal disk (first version: one loader reading `mpf-boot.cfg` fell to a `grub>` prompt on the installed disk). Keyboard AZERTY in GRUB, console and X (`KEYMAP=us` at build time for QWERTY). **Secure Boot must be off** (the loader is not signed) |
| Network | Ethernet by DHCP; Wi-Fi by wpa_supplicant on `wlan0` (`net.ifnames=0`: `eth0`, `wlan0`); Wi-Fi/SSH setup like the other images, below |
| Firmware | `firmware-iwlwifi`, `firmware-realtek`, `firmware-mediatek`, `firmware-atheros`, `firmware-intel-graphics`, `firmware-intel-misc`: the usual Wi-Fi / Ethernet / graphics chips of mini PCs |
| First boot | root partition grows to fill the disk; unique SSH host keys |
| Extras (default on) | `video` GStreamer + FFmpeg + `vainfo` + `intel_gpu_top`; `x11` Xorg + openbox + Mesa (Vulkan ANV / RADV); `mpf` MPF, Monitor, Godot, GMC via `install/install_linux.sh` in `/home/mpf/MPF-Godot`, autologin + `startx` on tty1 |

## Build (WSL2 Ubuntu or x86_64 Linux, about 15 GB free, 15 to 30 minutes)

```bash
cd platforms/x86/image/build
sudo bash wsl-build.sh        # installs host packages, work folder ~/x86-build, output in ~/x86-build/out/
```

`sudo EXTRAS="" bash wsl-build.sh` gives the bare image. Needs access to `deb.debian.org`, `security.debian.org` and `github.com`.

## Put it on the mini PC

1. Write the `.img.xz` to a USB stick (balenaEtcher or Raspberry Pi Imager "Use custom" read `.xz`; or `xzcat img.xz | sudo dd of=/dev/sdX bs=4M status=progress`).
2. In the firmware setup (Del or F2 at power on): Secure Boot off, boot from the USB stick. The system starts and the root partition grows to the stick.
3. **Install on the internal disk**: from the stick the PC shows a menu on the screen (no game, no X): the internal disks (the stick is left out), you pick a number and type its name again; the whole disk is erased (Windows included), the system is copied (about 5 minutes on real hardware), then it powers off: remove the stick and switch on. The same menu over SSH: `sudo mpf-installer`; without the menu: `sudo mpf-install-to-disk /dev/sda --yes` (`lsblk -dpno NAME,SIZE,TRAN` lists the disks; the AK2PLUS has an M.2 SATA, so `sda`, not `nvme`). In the menu `s` gives a shell and `g` starts the game session from the stick. Only an installed disk starts the game by itself. The disk's root grows to fill it at its first boot.

## Wi-Fi and SSH

Edit `mpf-network.txt` on the FAT partition (visible from Windows after writing the stick), or open `http://<address>:8080` (login: `mpf` and its password). With no
network after 90 s the PC opens a Wi-Fi access point `MPF-Setup` (password `mpf-setup`), page at `http://192.168.4.1:8080`
(only when the Wi-Fi chip supports an access point). Details: [common/netconfig](../../../common/netconfig/README.md). Claude Code is not in the image
(install it over SSH). The setup page also installs the game bundle and the PuP Pack, like on the Pi 4 image.

## Check the hardware video decoder

```bash
vainfo                                  # driver iHD, VAProfileH264High / HEVCMain ... VAEntrypointVLD
bash eval_hw.sh                         # platforms/x86/eval_hw.sh: 1, 2 and 3 streams of 1080p30 H.264 and HEVC, hardware and software
```
In the game's log: `GoZen: hardware decoding h264 (vaapi)` for each video.
