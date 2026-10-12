# NVIDIA Jetson

Jetson boards with JetPack 5 or 6 (L4T R35 or R36), as a cabinet PC: MPF, Godot and hardware video decoding
(NVDEC) for GDE GoZen. Installers: `install/install_linux.sh` (the Linux one line), which runs
`platforms/jetson/install_jetson_hwdec.sh` by itself on a Jetson, then `platforms/jetson/jetson_selftest.sh`.
Back to [all platforms](README.md); everything generic to Linux is in [linux.md](linux.md).

| Board | L4T / JetPack | Ubuntu | Tested (found on Tron Legacy MPF) |
|---|---|---|---|
| Jetson Xavier NX Developer Kit (t194) | R35.6.4 / JetPack 5.1.4 | 20.04.6 | X11 + openbox, no display manager, Godot 4.6.3, HDMI audio; decoder self-test and two game scenarios in five power modes (2026-10-09) |
| Jetson AGX Orin Developer Kit (t234) | R36.4.3 / JetPack 6.2 | 22.04 | `oot` kernel, Godot 4.6.3, one 1920x1080 DisplayPort screen with three video windows (2026-10-05) |

JetPack 4 (L4T R32) is refused: Godot 4.6 needs glibc 2.28+.

## Install order

1. The Linux one line ([linux.md](linux.md)). On arm64 it takes Python 3.11 from uv (Ubuntu 20.04 ships 3.8) or
   deadsnakes (22.04), PyQt6 6.7 for MPF Monitor, Godot `linux.arm64`. When `/etc/nv_tegra_release` exists it
   then runs `platforms/jetson/install_jetson_hwdec.sh` (`--no-jetson` or `MPF_GODOT_HWDEC=0` skips it; a
   failure there is a warning: videos then decode in software).
2. Log out and back in if the install added you to the `video` group.
3. `bash platforms/jetson/jetson_selftest.sh --stock --video <some H.264 .mp4>`: the patched build must pass every
   check (exit status 0). Run it on a new board or a new L4T release.
4. Set the power mode (`sudo nvpmodel -m 5`), an X11 session with automatic login, and the screens (below).

The decoder install alone, without the rest:
`bash <(curl -fsSL https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/platforms/jetson/install_jetson_hwdec.sh)`.

## What `install_jetson_hwdec.sh` does

Safe to re-run; it also works from a minimal or stripped root image.

| Step | What | How |
|---|---|---|
| 1 | Is it a Jetson | `aarch64` and `/etc/nv_tegra_release`; else nothing to do. L4T R35+ only. SoC from `/proc/device-tree/compatible` (t194 Xavier, t234 Orin); NVIDIA's apt release from L4T (R35.4.1 is `r35.4`) |
| 2 | Library folder | JetPack 6 keeps NVIDIA's libraries in `/usr/lib/aarch64-linux-gnu/nvidia/`, JetPack 5 in `.../tegra/`; EGL in `.../tegra-egl/` on both |
| 3 | L4T pin | `~/.cache/mpf-godot/l4t-pin.pref`: `nvidia-l4t-*` pinned to the board's own L4T version for this script's installs |
| 4 | Checks | root or sudo, apt and dpkg, the clock (year 2025 or later), free disk (1.5 GB; 4 GB with `--test`) |
| 5 | Build tools | each checked by file or command: CA certificates, curl, git, cmake, make, gcc, g++, libc6-dev, pkg-config, mawk, libjpeg-turbo8 |
| 6 | NVIDIA apt source | if missing: NVIDIA's key and `deb .../common <rel>` + `deb .../<soc> <rel>` |
| 7 | Multimedia API and libraries | `nvidia-l4t-jetson-multimedia-api`, `nvidia-l4t-multimedia`, `nvidia-l4t-multimedia-utils` when their files are missing |
| 8 | Decoder device | `/dev/nvhost-nvdec*` or `/dev/v4l2-nvdec` (a warning if absent); the user joins the `video` group |
| 9 | Godot's GPU driver and X | `nvidia-l4t-3d-core` (GLX, EGL, Vulkan ICD), `libglx0 libegl1 libvulkan1`; with X: `nvidia-l4t-x11`, `xserver-xorg-core`, `xserver-xorg-input-libinput`, `xinit`, `x11-xserver-utils` |
| 10 | Screen blanking | GNOME only: `idle-delay 0`, no lock, no idle screen saver, no dim, no suspend on AC, for the cabinet user |
| 11 | Sound | ALSA default on the APE card and no PulseAudio or PipeWire: `~/.asoundrc` to the HDMI output with a monitor, through dmix |
| 12 | Loader path | `tegra/` (or `nvidia/`) and `tegra-egl/` added to `/etc/ld.so.conf.d/` when not in the loader cache, then `ldconfig` |
| 13 | libnvmpi | jetson-ffmpeg at `8d70c17` in `~/.cache/mpf-godot/jetson-ffmpeg`, `build/gozen/nvmpi_flush.patch` applied (from this clone, else from GitHub on `MPF_GODOT_BRANCH`), `scripts/build.sh --no-stubs --install` into `/usr/local/lib`; checked in `ldconfig -p` |
| 14 | `--test` | an ffmpeg 7.1 with nvmpi in `~/.cache/mpf-godot/ffmpeg-src` (not installed) and a decode of `MPF_GODOT_TEST_VIDEO` |

| Option | Effect |
|---|---|
| `--dry-run` | print the checks and the plan, change nothing |
| `--test` | also build the test ffmpeg and decode a video with `h264_nvmpi` |
| `--no-x` | leave the X server alone (Godot's GPU driver is still checked) |
| `--keep-blanking` | leave GNOME's blanking, dimming and lock as they are |

| Environment | Meaning |
|---|---|
| `MPF_GODOT_HWDEC=0` | skip everything (GoZen decodes in software) |
| `MPF_GODOT_TEST_VIDEO` | an H.264 mp4 for `--test` and the self-test |
| `MPF_GODOT_BRANCH` | branch the patch is fetched from when run outside a clone |
| `MPF_GODOT_NV_RELEASE`, `MPF_GODOT_DEVICE_TREE`, `MPF_GODOT_ARCH`, `MPF_GODOT_ASOUND_CONF`, `MPF_GODOT_PROC_ASOUND`, `MPF_GODOT_ASOUNDRC` | for tests: a fake board |
| `GOZEN_HWDEC=0` | at run time: GoZen decodes in software |

The game's log then says `GoZen: hardware decoder h264_nvmpi` per video, and `sudo tegrastats` shows the decoder
clock while videos play.

## Self-test

`platforms/jetson/jetson_selftest.sh` builds the two repro programs of `fixes/repro/` (`nvmpi_seek_close.c`,
`nvmpi_concurrent.c`) against the patched ffmpeg tree, and with `--stock` against jetson-ffmpeg at the same
revision without the patch (in `~/.cache/mpf-godot/stock`, nothing system-wide). Each check has a time limit, so a
hang shows as a failure. Logs: `~/.cache/mpf-godot/selftest/`. Options: `--stock`, `--runs N` (default 100),
`--video F.mp4`, `--dry-run`. Without a decoder device it only builds.

| Check | What | Pass |
|---|---|---|
| flush | decode, flush, seek, three times | prints `OK` |
| close | time to free a decoder | both closes under 300 ms |
| crash | free a decoder mid-stream, N runs | no crash |
| concurrent | 3 threads open, flush and free decoders, N/5 runs | no hang |

Results (1080p30 H.264):

| Check | Xavier NX, R35.6.4, patched | Xavier NX, stock `8d70c17` | AGX Orin, R36.4.3, stock |
|---|---|---|---|
| flush | pass | hang (killed after 60 s) | hang on the first loop or seek |
| close | 59 ms / 48 ms | 1086 ms / 24 ms (no packet / after 30 frames) | 1061 ms |
| crash, 100 runs | 0 crashed | 0 crashed | 9 crashed |
| concurrent | 0 failed of 20 | 5 segfaults | 4 of 6 hung |

The Xavier NX run had no nvpmodel mode set (6 CPUs at 1.9 GHz), a minimal image. The Orin column comes from the
fix reports, not from this script.

## Video decoding fixes

| Fix | Layer | Page |
|---|---|---|
| A loop or seek hung the next decode: the decoder is recreated on a flush | jetson-ffmpeg wrapper | [../fixes/jetson-ffmpeg/flush-hang.md](../fixes/jetson-ffmpeg/flush-hang.md) |
| Closing a decoder took about 1 s (now about 50 ms) | libnvmpi | [../fixes/jetson-ffmpeg/slow-close.md](../fixes/jetson-ffmpeg/slow-close.md) |
| Closing a decoder mid-video crashed | libnvmpi | [../fixes/jetson-ffmpeg/close-crash.md](../fixes/jetson-ffmpeg/close-crash.md) |
| Several decoders created and closed at once hung | libnvmpi | [../fixes/jetson-ffmpeg/concurrent-decoders-hang.md](../fixes/jetson-ffmpeg/concurrent-decoders-hang.md) |
| Every plane mapped and unmapped per frame (11 ms per 1080p frame on R35) | libnvmpi | [../fixes/jetson-ffmpeg/planes-mapped-once.md](../fixes/jetson-ffmpeg/planes-mapped-once.md) |
| Video opens, closes and restarts stalled Godot's main thread | GoZen `video_playback.gd` | [../fixes/gde-gozen/main-thread-stalls.md](../fixes/gde-gozen/main-thread-stalls.md) |
| A catch-up `seek_frame()` retried for minutes on a low-priority thread | GoZen | [../fixes/gde-gozen/seek-frame-retry-loop.md](../fixes/gde-gozen/seek-frame-retry-loop.md) |
| `<codec>_nvmpi` asked first, software as the fallback | GoZen | [../fixes/gde-gozen/hwdec-nvmpi-first.md](../fixes/gde-gozen/hwdec-nvmpi-first.md) |
| Frames decoded at the shown size, as NV12 | GoZen | [../fixes/gde-gozen/set-target-size-nv12.md](../fixes/gde-gozen/set-target-size-nv12.md) |
| Frames decoded ahead on worker threads | GoZen | [../fixes/gde-gozen/decode-ahead.md](../fixes/gde-gozen/decode-ahead.md) |
| FFmpeg trimmed to what video packs use | GoZen build | [../fixes/gde-gozen/lean-build-option.md](../fixes/gde-gozen/lean-build-option.md) |
| Each vsync'd window waits for its own vblank | Godot | [../fixes/godot/vsync-one-window-multiwindow.md](../fixes/godot/vsync-one-window-multiwindow.md) |
| Godot's main thread alone on a core | Godot, `mpf_godot/launcher.py` | [../fixes/godot/core-pinning-main-thread.md](../fixes/godot/core-pinning-main-thread.md) |
| Separate render thread on by default | Godot | [../fixes/godot/render-thread-setting.md](../fixes/godot/render-thread-setting.md) |

`build/gozen/build_gozen.sh` and `install_jetson_hwdec.sh` apply the whole `nvmpi_flush.patch` to the same
jetson-ffmpeg revision, so GoZen's FFmpeg and the board's libnvmpi carry the same fixes. A change to its `src/` part
needs a new install on the board only; a change to its `ffmpeg/` part (or `gozen.patch`) needs a GoZen rebuild from
a clean work folder. The arm64 `.so` needs glibc 2.29 at most.

## Session, power, screens

**Session.** X11: Godot places one window per monitor only on X11. On the Xavier NX: X11 with openbox, automatic
login on tty1, no display manager. With GNOME, in `/etc/gdm3/custom.conf` (no comments at the end of a line):

```ini
[daemon]
AutomaticLoginEnable=true
AutomaticLogin=cabinet
WaylandEnable=false
```

**Power (Xavier NX).** `sudo nvpmodel -m 5` (10 W desktop, 4 cores at 1.91 GHz, the module's default) or 8 (20 W).
Measured with all fixes, L4T R35.6.4, a 120 s clip (`hurryup`) and a 620 s full game; every run: 0 black screens,
0 Godot errors, hardware decoding on every video, CPU at most 47.5 °C. Modes 0, 1, 6, 7 not run.

| Mode (CPUs / GPU max MHz) | Test | FPS avg | Worst 1 s | Median ms | Frames > 50 / > 100 ms | Video frames skipped | Video lag avg | A/V drift avg / max ms | CPU / GPU / NVDEC % | W avg |
|---|---|---|---|---|---|---|---|---|---|---|
| 3: 10W 2-core (2 × 1.50 GHz / 803) | hurryup | 19.8 | 9 | 38.9 | 437 / 67 | 1788 | 1084 ms | - | 87 / 17 / 81 | 5.2 |
| | full game | 20.3 | 1 | 37.5 | 3049 / 456 | 11685 | 475 ms | 186 / 1122 | 86 / 19 / 95 | 5.3 |
| 4: 10W 4-core (4 × 1.19 GHz / 803) | hurryup | 32.0 | 5 | 33.3 | 93 / 21 | 655 | 142 ms | 92 / 301 | 62 / 25 / 91 | 5.6 |
| | full game | 36.9 | 3 | 22.2 | 334 / 121 | 2776 | 183 ms | 113 / 910 | 53 / 27 / 97 | 5.6 |
| **5: 10W desktop (4 × 1.91 GHz / 510)** | hurryup | 54.4 | 29 | 16.7 | 26 / 9 | 146 | 47 ms | 138 / 163 | 46 / 35 / 94 | 6.6 |
| | full game | 52.6 | 8 | 16.7 | 161 / 68 | 856 | 68 ms | 91 / 521 | 43 / 36 / 98 | 6.5 |
| 2: 15W 6-core (6 × 1.42 GHz / 1109) | hurryup | 49.5 | 23 | 18.1 | 35 / 14 | 198 | 58 ms | 59 / 109 | 44 / 31 / 93 | 6.1 |
| | full game | 49.4 | 4 | 16.9 | 214 / 100 | 1274 | 122 ms | 192 / 1811 | 35 / 34 / 98 | 5.9 |
| 8: 20W 6-core (6 × 1.42 GHz / 1109) | hurryup | 52.9 | 26 | 17.1 | 25 / 12 | 173 | 69 ms | 48 / 261 | 39 / 34 / 93 | 6.5 |
| | full game | 50.7 | 3 | 16.7 | 218 / 96 | 1181 | 116 ms | 189 / 1749 | 34 / 35 / 98 | 6.4 |

Per-core speed matters more than the number of cores: Godot's main thread is the critical path, and mode 5 is the
only one with the top CPU clock. Modes 3 and 4 are not playable. `jetson_clocks` gains nothing (47.8 / 52.9 FPS
with it, 48.3 / 53.4 without). A later full game (2026-10-12, after more game-side fixes): mode 5 56.9 FPS, 70
frames over 100 ms, 8.8 W; mode 8 56.9 FPS, 87 over 100 ms, 8.7 W. The A/V drift maxima are single samples right
after a video switch.

**Screens (Xavier NX devkit).**

| Item | Fact |
|---|---|
| DisplayPort | no DP++ dual mode: a passive DP to HDMI adapter fails (AUX errors, "edid read prepare failed", output disconnected). Use a native DP monitor or an active adapter |
| USB-C | no video |
| Forced modes | the NVIDIA driver refuses a mode on a disconnected output (`xrandr --addmode`: BadMatch) |
| Refresh rate | a panel's EDID rate cannot be overridden: an EDID with a raised pixel clock loaded with `CustomEDID` was accepted by X and ignored; only a device-tree change could do it |
| Example bar panel | LTA149B780F (14.9", 1280x390) on HDMI: EDID reads fine, 1280x390 at 59.60 Hz. With vsync on a 60 Hz main monitor, it shows one frame twice about every 2.5 s |
| Window placement | per cabinet, in an untracked local config of the game, never in its tracked defaults |

**Standby between runs.** The launcher turns DPMS off for play, so backlights stay on after it exits. Sleep them
with `xset +dpms; xset dpms force off`. Before the next run, redo the session's `xrandr --auto` layout
([finding 13](#13-a-sleeping-monitor-loses-its-mode)).

## Minimal Xavier NX image

[jetson/image/README.md](jetson/image/README.md) builds a minimal Xavier NX devkit image (L4T 35.6.4, Ubuntu 20.04
`minbase`, no desktop) on an x86_64 Linux host (`build/build-native.sh`, 30 to 45 minutes), with optional groups:
NVIDIA's GStreamer and FFmpeg, Docker with the NVIDIA runtime, and Xorg with openbox spanning all outputs. It
flashes to an SD card (`flash/sd-flash.sh`, or balenaEtcher) or to an NVMe SSD with the QSPI bootloader
(`flash/nvme-flash.sh`, from WSL2 with usbipd or from native Linux). It boots from SD and from NVMe (2026-10-08);
every fix to NVIDIA's tools is listed there. Then run the install order above on it.

## Testing without the board

An arm64 Ubuntu 20.04 root under qemu, posing as a Xavier NX with L4T R35.4.1 (a fake `/etc/nv_tegra_release`
and NVIDIA's r35.4 apt packages), ran the full Linux install with `--yes` (Python 3.11 from uv, MPF Monitor, Godot
arm64), applied `nvmpi_flush.patch`, built libnvmpi against R35.4.1 (linking NVIDIA's `libv4l2.so.0`), and built
the self-test's ffmpeg and both repro programs. When Docker Hub rate-limits, make the base image with
`debootstrap focal` and `docker import`. Godot renders headless in the cloud with lavapipe
(`VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json`, `--rendering-method mobile`, under `xvfb-run`).
Decoding itself needs the board. The install scripts' dry runs take fake boards through the `MPF_GODOT_*`
variables above.

## Findings

### 1. NVIDIA packages newer than the board's BSP
- **Problem:** installing the Multimedia API or the GL driver on an R36.4.3 Orin would have put 36.4.7 libraries
  next to a 36.4.3 kernel and firmware.
- **Cause:** NVIDIA's apt release `r36.4` carries every point release (36.4.0 to 36.4.7), and apt picks the newest.
- **Fix:** `install_jetson_hwdec.sh`, `l4t_pin()`: a preferences file pins `nvidia-l4t-*` to the version in
  `/etc/nv_tegra_release`, used by this script's `apt_install()` only. Upgrading the BSP stays NVIDIA's `apt upgrade`.
- **Versions:** L4T R36.4 (the R35.6 repo also carries 35.6.5).
- **Found:** 2026-10-05, observed (found on Tron Legacy MPF, commit 38c8728).

### 2. A dpkg config-file question stopped the install
- **Problem:** the apt run failed on a piped install.
- **Cause:** dpkg asked about a config file already on the system (for example a hand-made
  `/etc/nv_tegra_release` on a stripped image), and a piped install has no stdin.
- **Fix:** `apt_install()`: `-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold`, which keeps
  the existing file.
- **Versions:** all.
- **Found:** 2026-10-05, observed (found on Tron Legacy MPF, commit 58e39bc).

### 3. A package "installed" with its files gone
- **Problem:** on a stripped image, packages counted as installed but their libraries were missing.
- **Cause:** images trimmed by deleting files leave dpkg's database as it was.
- **Fix:** `need()` checks each dependency by file or command, and `apt_install()` uses `--reinstall`.
- **Versions:** minimal and stripped L4T root images.
- **Found:** 2026-10-05, code (found on Tron Legacy MPF, commit 1dd72f6).

### 4. libnvmpi not found in the loader cache
- **Problem:** the check for libnvmpi failed on a full JetPack image although it was installed.
- **Cause:** with `pipefail`, `ldconfig -p | grep -q` fails: `grep` stops on the match and `ldconfig`, with more
  output left than a pipe holds, dies of SIGPIPE.
- **Fix:** `ld_cache()` reads the whole cache into a variable before searching it.
- **Versions:** full JetPack images (a long loader cache).
- **Found:** 2026-10-05, observed (found on Tron Legacy MPF, commit 95965ca).

### 5. `tegra/` or `nvidia/`, and `tegra-egl/`
- **Problem:** `nvidia-l4t-3d-core` was reinstalled on every run, and `nvidia-tegra.conf` rewritten every time.
- **Cause:** JetPack 6 moved NVIDIA's libraries from `tegra/` to `nvidia/`; `libEGL_nvidia.so.0` is in
  `tegra-egl/` on both; `libnvv4l2.so` is cached under its soname `libv4l2.so.0`, so a search by file name never
  matched. The package does not put `tegra-egl/` in the loader path (glvnd loads the library by name).
- **Fix:** `$TEGRA` by L4T major version, `$EGL_DIR` for EGL, and `loader_dir()` checks each folder in the cache
  (not a library name) after the GPU driver install.
- **Versions:** L4T R35 and R36.
- **Found:** 2026-10-05, observed against NVIDIA's R35.4 apt repository under qemu (found on Tron Legacy MPF,
  commit 76acfe3).

### 6. No decoder device: NVIDIA's libraries crash
- **Problem:** without the decoder device nodes, opening an nvmpi decoder crashed instead of failing.
- **Cause:** NVIDIA's libraries assume `/dev/nvmap` and `/dev/nvhost-nvdec*` (or `/dev/v4l2-nvdec`) exist.
- **Fix:** the install warns when the device is missing; the self-test only builds then; the game's player must
  check the same devices and decode in software without them (`GOZEN_HWDEC=0`).
  [../fixes/gde-gozen/hwdec-nvmpi-first.md](../fixes/gde-gozen/hwdec-nvmpi-first.md).
- **Versions:** any L4T without JetPack's kernel and device tree (a container, a custom kernel).
- **Found:** 2026-10-05, code (found on Tron Legacy MPF, commit 9e70e63).

### 7. A board without a clock battery
- **Problem:** apt, git and curl refused every certificate.
- **Cause:** no RTC battery and no network time: the clock starts in the past and certificates are "not yet valid".
- **Fix:** the checks step stops when the year is before 2025 and says to set the clock (`sudo date -s ...` or
  `systemd-timesyncd`).
- **Versions:** devkits without an RTC battery.
- **Found:** code.

### 8. The screens blanked mid-game
- **Problem:** on the Orin the video screens went black after 5 minutes of play.
- **Cause:** GNOME's idle blanking and lock, and X's DPMS: nobody touches a keyboard or mouse while playing.
- **Fix:** step 10 of `install_jetson_hwdec.sh` sets the cabinet user's GNOME settings (also over SSH or through
  sudo, with `dbus-run-session`); `--keep-blanking` leaves them. `mpf_godot/launcher.py`, `keep_screen_on()`,
  runs `xset s off -dpms`.
- **Versions:** GNOME on JetPack 6; X11.
- **Found:** 2026-10-05, observed (found on Tron Legacy MPF, commit 4f3332d).

### 9. No sound on the Xavier NX devkit
- **Problem:** Godot found no sound device and the game was silent.
- **Cause:** the devkit's `/etc/asound.conf` makes the APE card (I2S on the 40-pin header, nothing attached) ALSA's
  default.
- **Fix:** step 11 writes `~/.asoundrc`: the default to `hw:HDA,<n>` (the HDMI output whose ELD says a monitor is
  present; `hw:HDA,7` on the tested board) through dmix at 48 kHz. Skipped with PulseAudio or PipeWire, and an
  existing `~/.asoundrc` is kept.
- **Versions:** Xavier NX devkit image, L4T R35.6.4, minimal image without PulseAudio.
- **Found:** 2026-10-09, observed (found on Tron Legacy MPF).

### 10. Several monitors need X11
- **Problem:** on Wayland, Godot could not put one window per monitor.
- **Cause:** Godot places windows on a chosen screen only on X11.
- **Fix:** an X11 session ("Ubuntu on Xorg", `WaylandEnable=false`, or X11 with openbox); the install adds an X
  server unless `--no-x`.
- **Versions:** Godot 4.6.3.
- **Found:** 2026-10-05, observed (found on Tron Legacy MPF).

### 11. Four vsync'd windows: 15 FPS
- **Problem:** with four Godot windows each frame took four refreshes (67 ms).
- **Cause:** on the R35 X11 Vulkan driver each vsync'd window waits for its own vertical blank.
- **Fix:** vsync on one window only (the main one); the others redraw every frame anyway.
  [../fixes/godot/vsync-one-window-multiwindow.md](../fixes/godot/vsync-one-window-multiwindow.md).
- **Versions:** L4T R35, X11, Vulkan.
- **Found:** 2026-10-09, observed (found on Tron Legacy MPF).

### 12. Power mode
- **Problem:** the 2- and 4-core 10 W modes ran the game at 20 to 37 FPS.
- **Cause:** Godot's main thread is the critical path; per-core speed matters more than cores.
- **Fix:** `sudo nvpmodel -m 5` (or 8); no reboot needed. `jetson_clocks` adds nothing. Table above.
- **Versions:** Xavier NX, L4T R35.6.4.
- **Found:** 2026-10-09, observed (found on Tron Legacy MPF).

### 13. A sleeping monitor loses its mode
- **Problem:** after `xset dpms force off` between runs, the next run had every window on one screen at 39 FPS
  instead of 58.
- **Cause:** with the NVIDIA X driver and no desktop environment, a sleeping monitor loses its output's mode, and
  `xset dpms force on` does not bring it back; Godot then sees one screen.
- **Fix:** redo the session's `xrandr --auto` layout before the next run (in the cabinet's start script).
- **Versions:** Xavier NX, L4T R35.6.4, X11 + openbox.
- **Found:** 2026-10-12, observed (a lost one-hour soak, found on Tron Legacy MPF).

### 14. Passive DisplayPort adapters
- **Problem:** a monitor on a passive DP to HDMI adapter stayed disconnected.
- **Cause:** the Xavier NX devkit's DisplayPort has no DP++ dual mode.
- **Fix:** a native DP monitor, or an active adapter (one with a converter chip). Forcing a mode does not work.
- **Versions:** Xavier NX devkit.
- **Found:** 2026-10-09, observed (found on Tron Legacy MPF).

### 15. A submodule pointed at a local path
- **Problem:** syncing a game's submodule on a board reused across sessions failed with
  `transport 'file' not allowed`.
- **Cause:** an earlier session had pointed the submodule's remote at a local checkout.
- **Fix:** fetch from the GitHub URL directly (`git -C <sub> fetch <url> main`, then check out `FETCH_HEAD`)
  instead of rewriting the remote; copy a private submodule's content from the old checkout when the board has no
  credentials for it.
- **Versions:** git 2.38+ (`protocol.file.allow`).
- **Found:** 2026-10-12, observed (Xavier NX, found on Tron Legacy MPF).

### 16. `tegrastats` shows the decoder's clock, not its load
- **Problem:** NVDEC looked 95% busy with three videos.
- **Cause:** on L4T R35, `tegrastats` prints only the NVDEC clock; the figure is the share of samples with the clock on.
- **Fix:** measure headroom with parallel `ffmpeg -c:v h264_nvmpi` decodes instead: three 1080p30 videos use about
  a fifth of NVDEC on the Xavier NX (430 to 446 fps in total flat out).
- **Versions:** L4T R35.
- **Found:** 2026-10-09, observed (found on Tron Legacy MPF).
