# Tips and tricks: WSL and the Xavier NX, on any Linux

Short list of what saved time when setting up a Jetson Xavier NX from a Windows PC (WSL2) and on the board itself.
Everything is written for **any Linux distribution** (Debian, Ubuntu, Fedora, Arch, ...), and the flashing steps
**need no usbipd** when the host is a real Linux machine: usbipd only exists to hand a USB device from Windows to
WSL2. Details and the reasons are in [jetson.md](jetson.md), [jetson/image/README.md](jetson/image/README.md) and
[linux.md](linux.md).

Labels: **observed** (run on a real board, Xavier NX Developer Kit, L4T R35.6.4, 2026-10), **code** (read in the
script), **inferred** (not run).

## 1. Pick the host

| Host | USB to the board | Flash NVMe/QSPI | Status |
|---|---|---|---|
| Real Linux PC (any distro, kernel with `rndis_host` and an NFS server) | direct, no usbipd | one command, step 5 does everything over the board's USB network | inferred: the scripts are the WSL ones; not run on native Linux yet |
| WSL2 + usbipd-win 4.x | `usbipd attach --wsl` | guided, three pauses (steps 5, 6, 7) | observed |
| WSL2 without usbipd | none: the board cannot reach WSL | not possible. Use Windows balenaEtcher for an SD card, or a Linux live USB | observed (no USB in WSL without usbipd) |

A Linux live USB or a spare Ubuntu PC is the simplest way to avoid usbipd altogether.

## 2. Host set-up, any distribution

- **The flash scripts expect Ubuntu/Debian host packages** (`nvme-deps.sh` uses apt). On Fedora or Arch install the
  same tools by hand: `qemu-user-static` (binfmt aarch64), `dosfstools`, `mtools`, `lz4`, `xz`, `bzip2`, `cpio`,
  `device-tree-compiler`, `libxml2-utils`, `openssh-client`, `python3`, `sshpass`, `abootimg`, `nfs-kernel-server`
  (inferred names; `nvme-deps.sh` lists the full set and reports any it could not install).
- **Run the flash scripts yourself with `sudo` in a terminal.** A script launched by an agent stalled on the sudo
  password (observed).
- **Keep the work folder on the Linux filesystem** (`~/jetson-nvme`), never under `/mnt/c`: slow, and ext4 rights
  are needed for the rootfs.
- **WSL needs systemd** so udev sees the board's disks. `nvme-deps.sh` writes `[boot] systemd=true` into
  `/etc/wsl.conf`; then `wsl --shutdown` in PowerShell, reopen, re-attach the board.
- **Newer OpenSSH has no DSA keys**: NVIDIA's `ota_make_recovery_img_dtb.sh` runs `ssh-keygen -t dsa` and the flash
  fails later with `flash.idx is not found`. `nvme-flash.sh` deletes that line; do the same if you run NVIDIA's
  tools by hand. When something fails, read the first error in `flash-A.log`.

## 3. Recovery mode and USB (both hosts)

- Short **FC REC to GND** (pins 9-10 of the button header under the module), power on, wait 2 s. Use the
  **micro-USB data cable straight into the PC**, no hub.
- `lsusb` must show `0955:7e19` (recovery). If it does not, the board is not in recovery mode, whatever the host.
- The board **re-enumerates several times**: `7e19`, then `7035` (flashing initrd), then `7e19` again. On WSL each
  id must be re-attached (section 4); on native Linux nothing to do.
- Windows shows the 7035 device under its mass-storage driver name, not "Jetson": search by id,
  `usbipd list | findstr 0955`.

## 4. WSL2 with usbipd, the short version

Admin PowerShell, once:

```
usbipd policy add --effect Allow --operation AutoBind --hardware-id 0955:7e19
usbipd policy add --effect Allow --operation AutoBind --hardware-id 0955:7035
```

Then two PowerShell windows kept open for the whole flash:

```
usbipd attach --wsl --hardware-id 0955:7e19 --auto-attach
usbipd attach --wsl --hardware-id 0955:7035 --auto-attach
```

- "Waiting for device to expose ssh ... Timeout" is **expected** on WSL: its kernel has no `rndis_host` and no NFS
  server, so the scripts write the NVMe through the USB disk the board exposes (`--direct`) and the QSPI with
  `flashcmd.txt`. On native Linux the same step succeeds and the script finishes there.
- A laptop's built-in PCIe card reader cannot be passed through: write SD cards with Etcher on Windows.
- A stopped run: `nvme-direct.sh` redoes the NVMe write then the QSPI, `qspi-flash.sh` only the QSPI. The work
  folder keeps the BSP and images; `nvme-flash.sh` reuses them.

## 5. Native Linux, no usbipd

```bash
sudo bash platforms/jetson/image/flash/nvme-deps.sh
sudo IMG=/path/to/jetson-xavier-nx-l4t35.6.4-sd.img.xz bash platforms/jetson/image/flash/nvme-flash.sh
```

Skip every usbipd command. Inferred, not run: if step 5 stops at the ssh wait, the script's steps 6 and 7 (the
WSL path) work on native Linux too. Check the kernel has `rndis_host` (`modinfo rndis_host`) and that the NFS
server is installed.

## 6. On the board, after the flash

- **No clock battery**: the board boots with a wrong date and `apt`/TLS fail. Set it
  (`sudo date -s '2026-01-01 12:00'`) or enable `systemd-timesyncd`. The hardware-decoder installer refuses to run
  with a bad clock.
- **Stay on the board's L4T release**: `sudo apt-mark hold 'nvidia-l4t-*'` after install; NVIDIA's repo is already
  at 35.6.5 and a plain `apt upgrade` mixes releases and breaks the video libraries.
- **Python**: Ubuntu 20.04 has 3.8; the Linux line fetches a uv-built 3.11 (no compiler). A broken deadsnakes
  install falls back to uv by itself.
- **MPF Monitor on arm64 with glibc < 2.39**: PyQt6 must be `< 6.8` (no wheel, source build fails). The installer
  does this and leaves the monitor out below glibc 2.28.
- **Install order**: Linux one line, then `platforms/jetson/install_jetson_hwdec.sh`, then
  `platforms/jetson/jetson_selftest.sh` (every check must pass). See [jetson.md](jetson.md#install-order).
- **Screens**: several windows need **X11** (no Wayland). The devkit's DisplayPort has no DP++ dual mode: a passive
  DP to HDMI adapter fails, use a native DP monitor or an active adapter. USB-C has no video.
- **Sound**: the devkit's default ALSA card is the unused I2S one. The decoder installer writes `~/.asoundrc` to
  send it to HDMI (`hw:HDA,7` through dmix) when no PulseAudio/PipeWire is installed.
- **Screens blank mid-game**: turn idle blanking off (the decoder installer does); a sleeping monitor loses its
  mode.
- **Power**: `sudo nvpmodel -m 5` (10 W, 4 cores) or 8 (20 W). Modes 3 and 4 are not playable; `jetson_clocks`
  gains nothing.
- **Vsync**: with the NVIDIA R35 Vulkan/X11 driver keep vsync on one window only, or four windows give 15 FPS.
- **Submodules on a reused board** can point at a local path ([jetson.md](jetson.md), finding 15).
- **No GitHub credentials on the board** (Remote Control): hand changes back as `git format-patch` files.

## 7. When it still fails

| Symptom | Likely cause | Look at |
|---|---|---|
| `Cannot Open USB`, `USB communication failed` | board changed id, host lost it | section 3; re-attach (WSL) or replug; the QSPI step retries up to 6 times |
| `missing cfgfile` for QSPI | R35.6.4 names it `flash_l4t_t194_qspi_p3668.xml` | use NVIDIA's Example 2 without `-c` |
| `flash.idx is not found` | DSA `ssh-keygen` line, or an earlier error | `flash-A.log` |
| Initrd cannot see the disk | udev/systemd missing (WSL) | section 2 |
| Image creation fails in a container or VM | `losetup -P`, `kpartx`, vfat not available | the image builder writes partitions with `dd`; use a real VM or host |
| `mmcblk` I/O errors after an SD card flash | bad or fake card; Etcher verifies only what it wrote | [jetson/image/README.md](jetson/image/README.md#notes) |

## 8. Raspberry Pi 4 (Debian 13 trixie, Raspberry Pi kernel 6.18, Godot 4.6.3 OpenGL ES)

Found with Tron Legacy MPF on 2026-10-24 (all observed). Every measured setting, with the cabinet's files: [raspberrypi.md](raspberrypi.md). Performance findings: [GoZen zero-copy](../fixes/gde-gozen/v4l2m2m-zero-copy.md),
[the canvas shader's fill rate](../fixes/godot/pi4-canvas-shader-fill-rate.md).

- **No 3.5 mm jack sound card**: the device tree's bootargs carry `snd_bcm2835.enable_headphones=0` even with
  `dtparam=audio=on`. Append `snd_bcm2835.enable_headphones=1` to `/boot/firmware/cmdline.txt` (one line).
- **A screen that sends no EDID** (forced with `video=HDMI-A-n:1920x1080@60D`) gets **no HDMI audio**: vc4 treats it as
  DVI and the ALSA open fails with -524. Give it an EDID with a CEA block (basic audio, an LPCM short audio descriptor,
  the HDMI vendor block) and the same timing in `/lib/firmware/edid/`, then `drm.edid_firmware=HDMI-A-n:edid/<file>.bin`.
  Force the mode on both HDMI ports if either may be used.
- **ALSA default** with no PulseAudio/PipeWire is card 0, often an HDMI port with nothing on it: Godot then logs "All
  audio drivers failed" and uses its Dummy driver. Write `/etc/asound.conf` (`plug` to `hw:Headphones`; dmix on the
  jack stalls, `hw_ptr` stays 0).
- **X keeps an unplugged HDMI output as the primary at 0,0**, so the game opens its windows on a screen that does not
  exist: `xrandr --output HDMI-1 --off --output HDMI-2 --mode 1920x1080 --pos 0x0 --primary` in `~/.xinitrc`.
- **Vulkan freezes with video**: run Godot with `--rendering-driver opengl3`. Measured 2026-10-24 on Mesa 25.0.7: not a freeze but ~2 s a frame (V3DV uploads copied video planes with render passes that allocate and zero tile-state buffers); a video-less 1080p scene is faster in Vulkan (74.8 vs 39 fps). Separate render thread in Vulkan crashed when a script touched the scene tree from it.
- **Remote Control on the board**: `claude remote-control` started by a service from the home directory asks for
  folder trust at every start; start it from a dedicated folder and answer once. Do not build on the board: FFmpeg and
  godot-cpp took about 45 minutes with the game stopped; cross-build elsewhere and give the library to the board through
  a throwaway git branch it clones.
- **Windowed is slow**: Godot in a non-fullscreen X window is copied by X every frame (+7 ms on the TFU and +10 ms of
  rendering at 1080p); fullscreen page flips.

Last updated 2026-10-24. Add a numbered finding to [jetson.md](jetson.md) or [linux.md](linux.md) when a tip here
needs its full story.
