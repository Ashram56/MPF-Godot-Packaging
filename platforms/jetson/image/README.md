# Jetson Xavier NX: minimal image, build and flash

How to build the minimal Xavier NX devkit image (`jetson-xavier-nx-l4t35.6.4-sd.img.xz`) and how to flash it to an
SD card or to an NVMe SSD, from Windows through WSL2 (usbipd) or from a native Linux host. Every problem we hit
on the way and its fix is listed in [Fixes](#fixes), and is already built into the scripts.

The scripts live in [`scripts/jetson_image/`](../scripts/jetson_image/):

| Script | What it does |
|---|---|
| `build/build-native.sh` | Builds the image from scratch on an x86_64 Linux host (no podman/docker) |
| `build/files/` | First-boot resize unit and the patches applied to NVIDIA's tools |
| `build/packages.tsv` | Package manifest of the delivered image (package, version, installed size) |
| `flash/sd-flash.sh` | Writes the image to an SD card from Linux or WSL |
| `flash/nvme-deps.sh` | Installs the host packages the NVMe flash needs (WSL or native Ubuntu) |
| `flash/nvme-flash.sh` | Guided NVMe + QSPI flash, one run, pauses at every USB reconnect |
| `flash/nvme-direct.sh` | Re-runs only the NVMe write (board already in initrd flashing mode), then the QSPI |
| `flash/qspi-flash.sh` | Re-runs only the QSPI bootloader write, with wait and retry |
| `flash/nx-env.sh` | Shared settings (work folder, board identity, image lookup); sourced by the others |

The image itself is not in the repository (about 630 MB compressed, 3.5 GB raw). Build it, or get the delivered
copy with its `.sha256`.

**Tested:** the image boots from an SD card on a Xavier NX devkit (P3668-0000 on P3509), and from a 128 GB NVMe
with no SD card (2026-10-08, flashed from WSL2 with the steps that make up `nvme-flash.sh`). Wi-Fi, X, Docker
GPU and hardware decode were checked in the build only, not yet on the board. The native Linux NVMe path follows
NVIDIA's README and has not been run here.

## What you get

| Item | Value |
|---|---|
| Board | Jetson Xavier NX devkit, SD card module (P3668-0000) on carrier P3509 |
| BSP | NVIDIA Jetson Linux (L4T) 35.6.4, kernel 5.10.216-tegra |
| Userland | Ubuntu 20.04 (focal) arm64, debootstrap `minbase`, no desktop, no recommends, no docs |
| Login | `jetson` / `jetson` (set another with `JETSON_PASSWORD=` at build time), in `sudo`; SSH on port 22 |
| Network | Ethernet by DHCP; Wi-Fi by wpa_supplicant on `wlan0`; systemd-networkd + resolved, wired preferred |
| First boot | the root partition grows to fill the card or SSD; unique SSH host keys are generated |
| Extras (default on) | `video`: NVIDIA GStreamer plugins + NVIDIA FFmpeg 4.2.7 (`h264_nvv4l2dec`); `docker`: docker.io + NVIDIA runtime as default; `x11`: Xorg with NVIDIA's driver, `startx`, openbox, spanning all outputs |

CUDA, cuDNN and TensorRT are not on the host; on JetPack 5 the containers bring them (for example
`nvcr.io/nvidia/l4t-jetpack:r35.4.1`). `sudo apt install cuda-toolkit-11-4` adds the toolkit on the board.

## Build the image

Host: x86_64 Linux as root (Ubuntu 22.04/24.04; a VM or container is fine), about 25 GB free and 30 to 45
minutes, outbound HTTPS to `developer.download.nvidia.com`, `repo.download.nvidia.com`, `ports.ubuntu.com` and
`github.com`. No loop devices, device-mapper or vfat module are needed.

```bash
cd scripts/jetson_image/build
sudo bash build-native.sh                       # everything; output in ./work/out/
sudo EXTRAS="" bash build-native.sh             # bare image, without video/docker/x11
sudo WIFI_SSID="MyNet" WIFI_PSK="secret" WIFI_COUNTRY=FR bash build-native.sh   # pre-seeds one Wi-Fi network
```

| Variable | Default | Meaning |
|---|---|---|
| `WORK` | `./work` | Work folder (BSP, rootfs, output); ignored by git |
| `EXTRAS` | `video docker x11` | Feature groups; empty for none |
| `WIFI_SSID` / `WIFI_PSK` / `WIFI_COUNTRY` | unset | One WPA-PSK network (stored hashed) and the regulatory country |
| `JETSON_PASSWORD` | `jetson` | Password of the `jetson` user |

Output: `work/out/jetson-xavier-nx-l4t35.6.4-sd.img.xz`, its `.sha256` and `packages.tsv`. The script can be
re-run: it skips the BSP download and debootstrap when they are there. Delete `work/` (`sudo rm -rf work`, it is
owned by root) to start clean.

The stages, in order: host packages and qemu-aarch64 binfmt; BSP download; debootstrap and the package groups;
patches to NVIDIA's tools; `apply_binaries.sh`; the feature groups; NVIDIA's `jetson-disk-image-creator.sh -b
jetson-xavier-nx-devkit -d SD`; xz. Read `build-native.sh` for the package lists: each group says why it is there.

**From Windows:** the script should run in WSL2 Ubuntu as well (WSL2 has binfmt_misc), but this has not been
tried. Keep `WORK` in the Linux home (`WORK=~/nx-build`), never under `/mnt/c`, where ownership, device files and
symlinks are lost.

### Splitting and joining

Some file shares drop single files of about 550 MB. Split with `split -b 85M -d -a 1 file.img.xz file.img.xz.part`
and join in order:

- Linux / WSL: `cat jetson-xavier-nx-l4t35.6.4-sd.img.xz.part* > jetson-xavier-nx-l4t35.6.4-sd.img.xz`
  (`sd-flash.sh` and `nvme-flash.sh` also take the `.part0` directly and join it themselves).
- Windows cmd (`copy /b`, every name written out, no `...` shorthand):
  ```
  copy /b jetson-xavier-nx-l4t35.6.4-sd.img.xz.part0 + jetson-xavier-nx-l4t35.6.4-sd.img.xz.part1 + jetson-xavier-nx-l4t35.6.4-sd.img.xz.part2 + jetson-xavier-nx-l4t35.6.4-sd.img.xz.part3 + jetson-xavier-nx-l4t35.6.4-sd.img.xz.part4 + jetson-xavier-nx-l4t35.6.4-sd.img.xz.part5 + jetson-xavier-nx-l4t35.6.4-sd.img.xz.part6 + jetson-xavier-nx-l4t35.6.4-sd.img.xz.part7 jetson-xavier-nx-l4t35.6.4-sd.img.xz
  ```

Check the result against the `.sha256` file (`certutil` only prints a hash, it cannot compare):

- Linux / WSL: `sha256sum -c jetson-xavier-nx-l4t35.6.4-sd.img.xz.sha256`
- PowerShell (prints `True` on a match):
  `(Get-FileHash .\jetson-xavier-nx-l4t35.6.4-sd.img.xz -Algorithm SHA256).Hash -eq (Get-Content .\jetson-xavier-nx-l4t35.6.4-sd.img.xz.sha256).Split(' ')[0]`
- cmd (prints `MATCH`):
  `for /f "tokens=1" %h in (jetson-xavier-nx-l4t35.6.4-sd.img.xz.sha256) do certutil -hashfile jetson-xavier-nx-l4t35.6.4-sd.img.xz SHA256 | findstr /i %h && echo MATCH`

## Flash to an SD card

The SD-module Xavier NX boots the card through the bootloader in its QSPI flash, which must be L4T 35.x. A board
last flashed with JetPack 5 is fine. If the card does not boot, flash the QSPI once: run `flash/nvme-flash.sh`
(see [NVMe](#flash-to-an-nvme-ssd)) up to its first pause, press Ctrl+C, then run `flash/qspi-flash.sh`.

- **Windows:** balenaEtcher, pointed at the `.img.xz` (it decompresses it itself).
- **Linux:** `sudo bash scripts/jetson_image/flash/sd-flash.sh jetson-xavier-nx-l4t35.6.4-sd.img.xz /dev/sdX`
  (checks the sha256, asks for `YES`, unmounts and writes), or by hand:
  `xzcat jetson-xavier-nx-l4t35.6.4-sd.img.xz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress`.
- **WSL:** the same `sd-flash.sh`, once a USB card reader is attached to WSL with usbipd (`usbipd list`, then
  `usbipd bind --busid <id> --force` and `usbipd attach --wsl --busid <id>`; `lsblk` then shows the card). A
  laptop's built-in PCIe reader cannot be passed through: use Etcher on Windows.

The first boot grows the root partition to the card's size. Etcher verifies only the 3.5 GB it wrote, so it says
nothing about the rest of the card; see [Notes](#notes) for `mmcblk` I/O errors.

## Flash to an NVMe SSD

Needed when the board runs without an SD card: no card has to be in the slot. The image's root filesystem (its
`APP` partition) is flashed to the NVMe with the stock L4T 35.6.4 BSP, and the module's QSPI bootloader is written
too so it matches the BSP. **Both the NVMe and the QSPI are erased.** Nothing is rebuilt.

`jetson-xavier-nx-devkit` in the commands is NVIDIA's name for the SD-slot module (P3668-0000), and the `-qspi`
variant means "bootloader only": neither needs a card.

### Recovery mode

On the P3509 carrier, short FC REC to GND (pins 9 and 10 of the button header under the module), apply power,
wait 2 s, then remove the jumper (or leave it on until flashing ends). Use the carrier's micro-USB port with a data
cable, plugged straight into the PC, not into a hub. The board then shows as `0955:7e19` (Windows: "APX", maybe
with a yellow mark in Device Manager; usbipd does not need a Windows driver). If it is not in `usbipd list` at
all, it is not in recovery mode.

During the flash it reboots into NVIDIA's flashing initrd and comes back as `0955:7035` ("Jetson device in initrd
flashing mode"), and it re-enumerates several more times.

### From Windows (WSL2 + usbipd)

Needs WSL2 Ubuntu with systemd and usbipd-win 4.x (`usbipd --version`).

1. **Admin PowerShell, once:** let usbipd share both USB identities by itself.
   ```
   usbipd policy add --effect Allow --operation AutoBind --hardware-id 0955:7e19
   usbipd policy add --effect Allow --operation AutoBind --hardware-id 0955:7035
   ```
2. **Two PowerShell windows, left running during the whole flash:**
   ```
   usbipd attach --wsl --hardware-id 0955:7e19 --auto-attach
   ```
   ```
   usbipd attach --wsl --hardware-id 0955:7035 --auto-attach
   ```
   The second one says the device is not there yet: it attaches it when it appears. If `0955:7035` is not
   attached when the script asks for it, find it by id (Windows names it after its mass-storage driver, not
   "Jetson"): `usbipd list | findstr 0955`, then `usbipd bind --busid <id> --force` and
   `usbipd attach --wsl --busid <id>`.
3. **WSL, as root:**
   ```bash
   sudo bash scripts/jetson_image/flash/nvme-deps.sh
   ```
   It installs the host packages, loads the USB drivers and, if WSL is not running systemd, turns it on in
   `/etc/wsl.conf`. In that case run `wsl --shutdown` in PowerShell, reopen WSL and re-attach the board.
4. **WSL, the guided flash:**
   ```bash
   sudo IMG=/mnt/c/Users/<you>/Downloads/jetson-xavier-nx-l4t35.6.4-sd.img.xz bash scripts/jetson_image/flash/nvme-flash.sh
   ```
   `IMG` can also be the `.part0` of the split image or a raw `.img`. The work folder is `~/jetson-nvme` of the
   user who ran sudo (`WORKDIR=` to change it); keep it on the Linux filesystem. What it does:
   - **0-1.** Joins and checks the image, decompresses it, downloads and extracts the BSP (about 700 MB).
   - **2.** Copies the image's APP partition into `Linux_for_Tegra/rootfs` (no `apply_binaries.sh`: the L4T
     packages are already in it).
   - **3.** Host fixes: removes the DSA `ssh-keygen` line from NVIDIA's recovery-image script, runs NVIDIA's
     `l4t_flash_prerequisites.sh`.
   - **4.** Generates the QSPI and NVMe images **offline**, with the board identity in `BOARD_ENV`
     (`BOARDID=3668 BOARDSKU=0000 FAB=200 BOARDREV=G.0` by default, from the tested devkit), so the board is
     not touched yet. This is NVIDIA's `README_initrd_flash.txt` "Example 2".
   - **5. Pause: recovery mode (7e19).** `l4t_initrd_flash.sh --flash-only` boots the board into the flashing
     initrd. Under WSL it ends with "Waiting for device to expose ssh ... Timeout": that is expected.
   - **6. Pause: initrd mode (7035).** Writes the NVMe through the USB disk the board exposes
     (`l4t_initrd_flash.sh --direct sdX`, README "Workflow 12"). It picks the only non-empty USB disk, shows it,
     and asks you to type `YES`. Check the size is your SSD's.
   - **7. Pause: recovery mode again (7e19).** Builds the QSPI package with `flash.sh --no-flash`, then runs
     `bootloader/flashcmd.txt`. If it stops because the board re-enumerated before usbipd re-attached it, it
     pauses so you can check, then resumes (tegraflash continues from the board's current state), up to 6 times.

   At every pause the script checks with `lsusb` that the right id is visible in WSL, and prints the usbipd
   commands if it is not.
5. Remove the recovery jumper, power-cycle, log in as `jetson` / `jetson`, and check `lsblk` shows `/` on
   `nvme0n1p1`, grown to the SSD's size after the first boot.

If a run stops part way: `nvme-direct.sh` redoes step 6 (board still in initrd mode) and then the QSPI, and
`qspi-flash.sh` redoes only step 7. Both use the BSP and images left in the work folder. If the board has left
initrd mode, run `nvme-flash.sh` again: it reuses the image and BSP it already has, and you let step 5 time out.

Logs, in the work folder: `flash-A.log` and `flash-B.log` (image generation), `flash-C.log` (initrd boot),
`direct-nvme.log`, `qspi-build.log`, `qspi-flash.log`. A failure in A or B shows up later as
`bootloader/signed/flash.idx is not found`: read the first error in `flash-A.log`.

### From a native Linux host

Same scripts, same command, without the usbipd part:

```bash
sudo bash scripts/jetson_image/flash/nvme-deps.sh
sudo IMG=/path/to/jetson-xavier-nx-l4t35.6.4-sd.img.xz bash scripts/jetson_image/flash/nvme-flash.sh
```

A native Ubuntu kernel has `rndis_host` and an NFS server, so step 5 flashes both the QSPI and the NVMe over the
board's USB network and the script ends there; steps 6 and 7 only run when step 5 times out. The commands step 5
amounts to, from `Linux_for_Tegra/` with the image's rootfs in `rootfs/` and the board in recovery mode
(README_initrd_flash.txt, Example 2):

```bash
sudo ./tools/kernel_flash/l4t_initrd_flash.sh --no-flash jetson-xavier-nx-devkit-qspi internal
sudo ./tools/kernel_flash/l4t_initrd_flash.sh --no-flash --external-device nvme0n1p1 \
  -c ./tools/kernel_flash/flash_l4t_external.xml --external-only --append jetson-xavier-nx-devkit external
sudo ./tools/kernel_flash/l4t_initrd_flash.sh --flash-only
```

Not run here yet; if it stops at the ssh wait, the WSL path (steps 6 and 7) works on native Linux too.

## Check the board

```bash
cat /etc/nv_tegra_release                     # R35 (release), REVISION: 6.4
lsblk                                         # / on mmcblk1p1 (SD) or nvme0n1p1 (NVMe), full size
networkctl; ip a                              # eth0 / wlan0
wpa_passphrase "SSID" "pass" | sudo tee -a /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
sudo systemctl restart wpa_supplicant@wlan0   # join Wi-Fi
ffmpeg -c:v h264_nvv4l2dec -i v.mp4 -f null - # hardware decode through NVIDIA's FFmpeg
docker info | grep -i runtime                 # Default Runtime: nvidia
startx                                        # from the console as jetson
sudo apt-mark hold 'nvidia-l4t-*'             # stay on 35.6.4 (see Notes)
```

Then bring up the game's hardware video decoding with [jetson.md](jetson.md#xavier-nx-checklist).

## Fixes

### Building the image

| Problem | Symptom | Fix (in `build-native.sh`) |
|---|---|---|
| iwd needs `CONFIG_CRYPTO_USER_API_HASH`, which the L4T 35 kernel lacks | Wi-Fi never comes up (upstream pythops recipe) | wpa_supplicant on `wlan0` (`wpa_supplicant@wlan0`), crypto in userspace |
| L4T debs depend on packages the trimmed rootfs dropped | `nvidia-l4t-tools`, `-kernel`, `-bootloader`, `-initrd`, `-jetson-io` fail to configure | Add `python3 libnl-genl-3-200 libnl-route-3-200` |
| NVIDIA's recovery image copies `mtd_debug`, `dhclient-script` and `xxd` out of the rootfs | Image creation fails | Add `mtd-utils isc-dhcp-client xxd` |
| NVIDIA's recovery initrd step calls `ssh-keygen` on the host | Image creation fails | Install `openssh-client` on the build host |
| `libffi6` only exists in bionic | NVIDIA multimedia libraries miss it | bionic `main` added, pinned to priority 100 |
| `<SOC>` placeholder in `nvidia-l4t-apt-source.list` is not filled in a chroot | `apt update` on the board fails | `sed s/<SOC>/t194/` after `apply_binaries.sh` |
| Empty hostname in the rootfs | No hostname on the board | `/etc/hostname` and `/etc/hosts` set to `jetson` |
| `jetson-disk-image-creator.sh` uses `losetup -P`/kpartx, `flash.sh` mounts vfat | Fails in containers and VMs without loop partitions, device-mapper or vfat | Partitions written with `dd seek=<GPT first sector>` (with a size check); ESP filled with mtools `mmd`/`mcopy` |
| `flash.sh` checks `$USER`, not the uid | Refuses to run under sudo in some setups | `USER=root` exported for the creator |
| `nv-apply-debs.sh` runs `mknod` and plain `dpkg -i` | Fails on a rootfs without device nodes, and on file conflicts with Ubuntu packages | `files/patches/nv-apply-debs.diff`: no `mknod`, `dpkg -i --force-overwrite` |
| `linux-firmware` is about 700 MB | Big image | Installed, then purged except the Intel 8265/8000C Wi-Fi blobs (the devkit's RTL8822CE firmware is built in / in nvidia-l4t-firmware) |
| NVIDIA's repo carries 35.6.5 | A rebuild would pull a newer L4T than the BSP | NVIDIA's apt source is kept out of the base `apt upgrade` |
| Every card would share the build's SSH host keys | Same host keys on every board | Keys deleted; `ssh-hostkeys.service` runs `ssh-keygen -A` on first boot |
| Initrd has no resolver | No DNS in the initrd | `nameserver 127.0.0.53` in `l4t_initrd.img` (upstream fix) |
| Root partition is only as big as the image | Card or SSD mostly unused | `resizerootfs.service` grows partition 1 on boot (no-op once full; APP is the last partition on the NVMe too) |

### Flashing to NVMe

| Problem | Symptom | Fix |
|---|---|---|
| Board not really in recovery mode, or Windows has no driver | APX device "not recognized" | FC REC to GND (pins 9-10) while powering on; data cable on the carrier's micro-USB, no hub. usbipd only needs it listed |
| The board changes USB id (7e19 → 7035) and re-enumerates several times | Timeouts, "USB communication failed", "Cannot Open USB" | usbipd `policy add ... AutoBind` for both ids and `attach --auto-attach --hardware-id` per id; the scripts pause at every reconnect and retry the QSPI write |
| 0955:7035 is named after its mass-storage driver in `usbipd list` | "Not reported by usbipd" | `usbipd list \| findstr 0955`, `bind --force`, `attach` |
| No QSPI config `flash_t194_qspi_p3668.xml` in R35.6.4 (it is `flash_l4t_t194_qspi_p3668.xml`) | "Error: missing cfgfile" | Use NVIDIA's Example 2 with the board conf, no `-c` for the QSPI |
| Newer OpenSSH removed DSA keys; `ota_make_recovery_img_dtb.sh` runs `ssh-keygen -t dsa` | "command is failed", then "flash.idx is not found" / "failed to relocate images" | `nvme-flash.sh` deletes that line (the DSA key is unused) |
| The WSL2 kernel has no `rndis_host`; the flashing initrd's USB network is RNDIS | "Waiting for device to expose ssh ... Timeout" after the board reaches initrd mode | Write the NVMe through the USB disk the board exposes (`--direct`), the QSPI with plain `flash.sh` / `flashcmd.txt` |
| No NFS server in the WSL kernel | `--network usb0` unusable | Not used |
| The exposed disk's model is "0", and the board also exposes 0-byte mmc disks | Script could not find the NVMe | Pick the only non-empty USB disk, show it, ask for `YES` |
| Image generation asked the board for its identity | Extra reconnects | `BOARDID/BOARDSKU/FAB/BOARDREV` passed, images generated offline |
| udev must find the board's disks | Initrd flash cannot see the disk | `nvme-deps.sh` enables systemd in WSL |
| NVIDIA's tools need many host commands | Repeated "command not found" | `nvme-deps.sh` installs them all and lists any it could not |
| The flash steps need root | A script started by an agent stalled on the sudo password | Run the scripts yourself with `sudo` in a terminal |

## Notes

- **Staying on 35.6.4:** NVIDIA's repo already carries 35.6.5, and `apt upgrade` on the board moves the L4T
  packages, bootloader included, which is NVIDIA's normal update path. Run `sudo apt-mark hold 'nvidia-l4t-*'`
  to stay put.
- **`Buffer I/O error on dev mmcblk...` at boot:** harmless on `mmcblk0boot0/boot1/rpmb`. On `mmcblk1` with
  `error -84` (CRC) or `-110` (timeout) the card is failing, fake-capacity or unstable at UHS speed; test it with
  H2testw or `f3probe --destructive` before reflashing.
- **AGX Orin** (L4T 36.4.3, Ubuntu 22.04, kernel 5.15 OOT) needs its own BSP, SoC (`t234`), package list and
  board name; the build is not done yet. AGX Xavier (`t194`, L4T 35.6.4) should need only `BOARD` changed.
- Recipe origin: https://github.com/pythops/jetson-image (`Containerfile.rootfs.20_04` +
  `Containerfile.image.l4t35`), reimplemented as one script.
