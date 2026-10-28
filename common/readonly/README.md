# Read-only production mode: no wear on the flash

A cabinet runs for years on an SD card, an eMMC or an SSD. Flash cells wear out with writes, and a power cut during a
write can corrupt a file system. So once an image is in production (after debugging) **nothing is written to the root or
the boot partition**, and the few things that must survive a reboot go to **one small read/write partition**.

Shared by every image (Raspberry Pi 4, Jetson Xavier NX, x86 mini PC). Nothing here depends on what an image contains:
each build script makes one call (`mpf_readonly_install`) and everything else is a list in `/etc/mpf-readonly.conf`.

## The idea

| Where | Mode | What lives there |
|---|---|---|
| Root partition (`/`) | **read-only** (`ro` in fstab and on the kernel command line) | the system, MPF, Godot, the setup page |
| Boot partition (FAT: `/boot/firmware`, `/boot/efi`) | **read-only** | kernel, bootloader, `mpf-network.txt` |
| RAM (tmpfs) | writable, lost at power-off | `/tmp`, `/var/log` (journal in RAM), `/var/tmp`, `/var/cache`, `/var/lib/systemd`, `/var/spool`, the game's `logs/`, Godot's `user://`, the X server's log and cookie |
| **Data partition** `mpfdata`, mounted on `/data` | **read/write**, ext4 with its journal | the game and everything it writes (settings `options.json`, `data/` with scores and machine variables, `audits/`, `pup.local.cfg`, `scorbit.local.cfg`, the PuP Pack), uploads, Wi-Fi, SSH host keys and `authorized_keys`, and what a platform adds (Docker on the Jetson) |

The data partition is **created at the first boot** in the free space at the end of the disk (`mpf-persist`, a systemd unit
that runs before `local-fs.target`): the image does not change size, the card keeps its free space for it. If it is
already there it is checked (`e2fsck -p`) and mounted. If it cannot be made (no free space, a broken file system), a
tmpfs takes its place so that the system still boots, the page says so in bold, and settings are lost at power-off.

The folders that must be written are not moved, they are **bind-mounted** from the data partition over the image's own
(`/opt/games`, `/etc/ssh`, `/etc/wpa_supplicant`, `/home/<user>/.ssh`, and a platform's extra ones): first boot copies the
image's content there once, every later boot finds what the system wrote. Programs see their usual paths and need no change.
Caveat of a bind: a change of the image under such a folder (for example a new `/etc/ssh/sshd_config` from `apt` in
maintenance mode) is hidden by the persistent copy, edit it there.

Writes that remain on the data partition are only the ones that carry information: a changed setting, a score, an audit, an
installed game or pack, a Wi-Fi network. The game's logs (written all the time) are redirected to RAM: after the install,
`game/logs` is a link to `/var/log/mpf-game` (`mpf_netconfig.py`, `volatile_game_dirs`).

## Production and maintenance mode

| | Production | Maintenance |
|---|---|---|
| Root and boot partition | read-only | writable |
| Data partition | writable | writable |
| Installing or updating the **game** from the page (port 8080) | works | works |
| Wi-Fi, SSH key, game settings, scores | work | work |
| Changing the operating system (`apt`, a kernel, a file in `/etc`, a new GoZen build in the image) | refused (read-only file system) | works |

Switch (all of them end in `/usr/local/sbin/mpf-mode`):

- the **page** `http://<address>:8080`, section *Mode*: "Maintenance mode until the next reboot", "Maintenance mode, also
  after reboots", "Back to production";
- by SSH: `sudo mpf-mode maintenance [--stay]`, `sudo mpf-mode production`, `mpf-mode status`;
- with no network and no SSH: edit **`mpf-network.txt`** on the FAT boot partition from any computer (`MODE=maintenance`),
  reboot. The key is emptied after it was read. (On the Jetson the file is on the ext4 root, so this works from WSL or Linux only.)

*Until the next reboot* is the default: a forgotten maintenance session ends by itself at the next power cycle. `--stay`
puts a flag on the data partition (`/data/mpf/maintenance`) and the system comes back writable at every boot until
`mpf-mode production`. Going back to production remounts read-only; if a program still holds a file open for writing the
remount is refused and a reboot does it (the flag is cleared first). `mpf_netconfig.py` also opens the root for one write
in a short window where it must (`writable()`: emptying the Wi-Fi password in `mpf-network.txt` on the FAT partition, enabling
or disabling the game at power-on), then closes it again.

The build option is `READONLY=1` (default) or `READONLY=0` (an ordinary writable image whose root grows at the first boot, as before)
on every platform's `build-native.sh`.

## Checking it

`sudo mpf-ro-check` after the game has run for a while shows the mode, every writable mount on real storage, the failed
units (a service that wanted to write to a read-only place), **how many MB each partition has been written since boot** (the root and
boot partitions must show 0), the processes that wrote most, and the journal's "Read-only file system" errors. Look for a program
that writes where it should not and add its folder to `MPF_PERSIST` (the data partition) or `MPF_VOLATILE` (RAM): it is a line in
`/etc/mpf-readonly.conf` of the running image (in maintenance mode) and in `common/readonly/mpf-readonly.conf.default` or the
platform's `mpf_readonly_install` call for the next build.

`tests/test_readonly.py` checks the scripts' syntax, the build helper on a fake root, the page's side, and (as root, with a loop
device) the creation, reuse and seeding of the data partition.

## Files

| File | Role |
|---|---|
| `mpf-readonly.conf.default` | installed as `/etc/mpf-readonly.conf`: data label and mount, boot mount, user, `MPF_PERSIST`, `MPF_VOLATILE` |
| `install-readonly.sh` | `mpf_readonly_install ROOTFS USER BOOT_MOUNT ["name:target ..."]`, sourced by a build script: scripts, unit, fstab (`ro` appended, tmpfs lines), journald in RAM, DHCP identity by MAC (there is no persistent `/etc/machine-id`), X log and cookie in RAM, masked timers that write (apt, man-db, e2scrub, logrotate, alsa state) |
| `mpf-persist.sh` / `.service` | data partition and persistent folders at every boot, maintenance flag |
| `mpf-mode.sh` | `mpf-mode status | maintenance [--stay] | production` |
| `mpf-ro-check.sh` | the check above |

What a platform does besides the call: the kernel command line gets `ro` (Raspberry Pi `cmdline.txt`, GRUB `linux` line, Jetson
`extlinux.conf`), the first-boot root resize is not installed (the free space at the end belongs to the data partition), and
`mpf-game.service` is enabled in the image (the page toggles its link in a writable window). x86: `mpf-install-to-disk` makes
the system partition the size of the system plus 1.5 GB and the rest of the disk the data partition, and copies the system
as built (not the stick's current state). Per platform:

| Platform | Status | To verify on the hardware |
|---|---|---|
| x86 (AK2PLUS) | build script and installer done, the bare image booted in QEMU (see the pull request) | the full image on the mini PC: `mpf-ro-check` after a game |
| Raspberry Pi 4 | build script done, not built | `cmdline.txt` really read-only, units failing on a read-only root |
| Jetson Xavier NX | build script done, not built | `cat /proc/cmdline` has `ro` (the build edits NVIDIA's `extlinux.conf`); NVIDIA's services (`nvpmodel`, `nvfancontrol`, `nvphs`, camera) that write; on an NVMe flash the APP partition must leave free space at the end (the flash tooling may fill the whole drive: then there is no data partition) |

## Not covered

- Package upgrades and kernel updates: maintenance mode, then back to production.
- A game that writes elsewhere than its own folder: find it with `mpf-ro-check` and add the folder to `MPF_PERSIST`.
- Wear of the data partition itself is small by construction (a few KB per score or audit change, one write per setting) but not nil; it is
  an ext4 with a journal, so a power cut loses at most the last seconds.
- `/etc/machine-id` is not persistent (it is generated in RAM at each boot); the DHCP lease is stable anyway (identifier by MAC).
