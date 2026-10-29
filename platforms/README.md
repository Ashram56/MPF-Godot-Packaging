# Platforms

What the installers put on each platform, how, and what has been tested where. One page per platform has the
installer step by step, its options and every lesson learned (numbered "Findings"):

| Page | Installer | Platforms |
|---|---|---|
| [windows.md](windows.md) | `install/install_windows.ps1` | Windows 10 (1809+) / 11, x86_64 and ARM64 |
| [macos.md](macos.md) | `install/install_macos.sh` | macOS 12+, Intel and Apple silicon |
| [linux.md](linux.md) | `install/install_linux.sh` | Debian/Ubuntu (apt), Fedora/RHEL (dnf), Arch (pacman); x86_64 and arm64 |
| [jetson.md](jetson.md) | `install/install_linux.sh`, then `platforms/jetson/install_jetson_hwdec.sh` | Jetson Xavier NX (L4T R35, JetPack 5), AGX Orin (L4T R36, JetPack 6) |
| [raspberrypi.md](raspberrypi.md) | `install/install_linux.sh`, then the cabinet settings | Raspberry Pi 4 (Raspberry Pi OS, Debian 13): measured settings for 30 FPS with videos, and its limits (DMD external, or overlay in 256x64 dots only) |
| [x86.md](x86.md) | `install/install_linux.sh`, or the image | x86_64 mini PC with an Intel / AMD GPU (Nipogi AK2PLUS, Intel N100): VAAPI hardware decoding |
| [x86/image/README.md](x86/image/README.md) | `platforms/x86/image/build/` | a minimal Debian 13 UEFI image for such a mini PC, USB stick or internal disk |
| [jetson/image/README.md](jetson/image/README.md) | `platforms/jetson/image/build/`, `flash/` | a minimal Xavier NX image (L4T 35.6.4), SD card or NVMe |
| [frame-rate-method.md](frame-rate-method.md) | any board | the checks, the V4L2 decoder, measuring and cross-building before promising a frame rate (Raspberry Pi 4 as the example) |
| [godot-performance.md](godot-performance.md) | any slow target | GMC + Godot stalls, node pooling, a display drawn from data |
| [video-playback.md](video-playback.md) | all | GDE GoZen and native video: switching, the Windows build, checking the decoder |
| [dmd_devices.md](dmd_devices.md) | `addons/dmd_out/`, `examples/dmd_devices/` | PIN2DMD and ZeDMD RGB LED DMDs, any OS (feeder: Linux, macOS) |
| [pup-remote-topper.md](pup-remote-topper.md) | `mpf_godot/pup_remote/` | PuP screens on a Raspberry Pi (a topper): server for the game, agent and installer for the Pi |
| [limits.md](limits.md) | none | what each platform cannot run, and how the settings page, the installer and each start enforce it |
| [tips.md](tips.md) | none | short tips for WSL, Linux hosts without usbipd, and the Xavier NX |

Every installer ends by running `python -m mpf_godot setup` (`mpf_godot/setup_toolchain.py`), which is the same
on every OS: the `.venv` with MPF 0.80.1 (and MPF Monitor 1.0.0), Godot 4.6.3 in `toolchain/godot/`, the GMC 1.0.0
add-on in `toolchain/addons/mpf-gmc/`, patched. Pins and their reasons: `mpf_godot/toolchain.py`.

## The one line

| OS | Line |
|---|---|
| Windows | `powershell -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/install/install_windows.ps1) -join [char]10))"` |
| macOS | `bash <(curl -fsSL https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/install/install_macos.sh)` |
| Linux, Jetson | `bash <(curl -fsSL https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/install/install_linux.sh)` |

Settings read from the environment by all three installers:

| Variable | Default | Meaning |
|---|---|---|
| `MPF_GODOT_DIR` | `~/MPF-Godot` (Windows `%USERPROFILE%\MPF-Godot`) | where the one line clones the repository; keep it out of OneDrive |
| `MPF_GODOT_BRANCH` | `main` | branch to clone, or to switch to when the clone's branch is gone from GitHub |
| `MPF_GODOT_REPO` | `https://github.com/Ashram56/MPF-Godot-Packaging.git` | repository to clone (a fork) |
| `MPF_GODOT_GITHUB_TOKEN` | unset (`GITHUB_TOKEN`, `GH_TOKEN` also read) | token for a private fork, so the installer does not ask |
| `MPF_GODOT_HWDEC` | `1` | Linux on a Jetson: `0` skips the hardware video decoder install |

Run from a clone, an installer sets up that clone and does not clone again.

## What is installed, and how

| | Windows x86_64 | Windows ARM64 | macOS Intel / Apple silicon | Linux x86_64 (apt, dnf, pacman) | Linux arm64 | Jetson Xavier NX (L4T R35) | Jetson AGX Orin (L4T R36) |
|---|---|---|---|---|---|---|---|
| Python 3.11 | winget `Python.Python.3.11` (user), else python.org 3.11.9 amd64 | same, python.org 3.11.9 arm64 | Homebrew `python@3.11`, else python.org 3.11.9 universal2 `.pkg` | distro package, else deadsnakes (Ubuntu), else uv standalone build (Arch: uv only) | same as x86_64 | uv (Ubuntu 20.04 ships 3.8) | deadsnakes or uv (22.04's own 3.11 is an RC) |
| Git | winget `Git.Git`, else Git for Windows 2.47.1 | same | in place, Homebrew, else Xcode Command Line Tools | distro package | distro package | distro package | distro package |
| Godot 4.6.3 | `win64.exe` | `windows_arm64.exe` | `macos.universal` (unpacked with `ditto`) | `linux.x86_64` + system libraries | `linux.arm64` + system libraries | `linux.arm64` + NVIDIA GL/EGL/Vulkan/X driver | same as Xavier NX |
| MPF Monitor (PyQt6) | wheels | wheels | wheels | wheels + xcb/Qt libraries | PyQt6 < 6.8 (glibc 2.28+), else left out | PyQt6 6.7 | PyQt6 6.7 |
| P-ROC driver (`--proc`) | MPF's bundled pypinproc + VC++ runtime + FTDI D2XX (by hand) | none (no pypinproc build) | built: libpinproc + pypinproc (Homebrew libs) | built + udev rule | built + udev rule | built + udev rule | built + udev rule |
| Video add-on | GDE GoZen; native_video as fallback | native_video only (no GoZen build) | native_video | GDE GoZen | GDE GoZen | GDE GoZen | GDE GoZen |
| Hardware video decoding | GoZen: Direct3D 11 Video, else DXVA2 | the OS decoder (Media Foundation) | the OS decoder (AVFoundation) | none (GoZen decodes in software) | none (software) | NVDEC through libnvmpi (`h264_nvmpi`) | same as Xavier NX |

Video add-ons are copied into a game with `python -m mpf_godot addons <game> --video`
(`mpf_godot/__main__.py`, `toolchain.gozen_supported()` and `native_video_supported()`).

## Tested where

Only what the sources report. "The game" is the first game ported with this kit (a Stern SAM recreation).

| Platform | What was run | Result | Source |
|---|---|---|---|
| Windows x86_64 | the game's CI (`windows-latest`): setup and tests, Python 3.11 from `actions/setup-python`, not the installer | pass | the game's `.github/workflows/test.yml` |
| Windows x86_64 | the installer for real, by the owner (token prompt) | Ctrl+V did not paste the token; fixed by right-click advice | packaging agent, section 5 |
| Windows x86_64 | GoZen with GPU decoding (Ryzen 7800X3D, d3d11va) | pass | the game's repository, merged 2026-10-10 |
| Windows (pwsh 7.4 on Linux) | the one line as a dry run; `PositionalBinding` check | pass | the game's repository, 2026-10-10 |
| Windows ARM64 | nothing reported | - | - |
| macOS | the game's CI (`macos-latest`): setup and tests; the installer only as a dry-run plan in tests | pass | the game's `test.yml`, `tests/test_install.py` |
| Linux x86_64 (Ubuntu) | the game's CI: setup, tests, render check under Xvfb | pass | the game's `test.yml` |
| Linux dnf, pacman, Debian, Mint, Rocky, EndeavourOS | installer dry runs with fake `/etc/os-release` only | pass | the game's `tests/test_install.py` |
| Linux arm64, Ubuntu 20.04 (qemu, posing as a Xavier NX on R35.4.1) | full install with `--yes`: Python 3.11 from uv, MPF Monitor, Godot arm64; libnvmpi builds | pass | the game's `docs/jetson/README.md` |
| Linux arm64, Ubuntu 22.04 (emulated JetPack 6) | PyQt6 6.7.1 and Qt 6.7.1 from wheels, `mpfmonitor` imports | pass | the game's repository, 2026-10-05 |
| Jetson AGX Orin, L4T R36.4.3 | game with three video windows, hardware decoding | pass (fixes needed) | the game's `docs/jetson/README.md` |
| Jetson Xavier NX, L4T R35.6.4 | decoder self-test, two game scenarios in five power modes | pass (fixes needed) | the game's `docs/jetson/README.md`, `xavier_nx.md` |
| P-ROC (`--proc`), any OS | `build_pinproc.sh` and the udev step as dry-run plans in tests; no run on a real board reported | plan only | the game's `tests/test_install.py` |
| Xavier NX minimal image | boots from SD and from NVMe | pass | [jetson/image/README.md](jetson/image/README.md) |

The installers of this repository were renamed from the first game's (`install_prereqs_*` to `install_*`, its own variable prefix to
`MPF_GODOT_*`); the one lines above have not been run from this repository yet.

## Common to the three installers

| Problem | Fix | Found |
|---|---|---|
| A clone whose branch was deleted on GitHub (a merged pull request) could not be pulled | the installer fetches and switches to `MPF_GODOT_BRANCH` (`checkout -B ... --track`) | 2026-10-04, code |
| `git pull` aborts on untracked files the update adds: Godot writes a `.uid` next to each script it opens, often before the commit that tracks it | `clear_untracked_in_update` (bash) / `Clear-UntrackedInUpdate` (PowerShell): remove `.uid`/`.import` and identical copies, move any other file to `<file>.local` | 2026-10-10, observed on Windows |
| A private fork: `curl`/`irm` get 404 without a token, and git needs a token, not a password | token flow: [linux.md, "A private repository and its token"](linux.md#a-private-repository-and-its-token) | 2026-10-04 to 10-07 |
| Godot downloads from downloads.tuxfamily.org failed on some networks | Godot from GitHub releases (`toolchain.GODOT_RELEASES`) | code |
| Release tags cannot be pushed from a cloud session (git proxy answers 403) | the owner creates the tag on GitHub or from a clone | observed |
| A board without GitHub credentials (Remote Control) cannot push | it hands changes back as `git format-patch` files; a cloud session applies and pushes them | observed on the AGX Orin |
| Release tags cannot be pushed from a cloud session (git proxy answers 403) | the owner creates the tag on GitHub or from a clone | observed, Tron PuP fork |
| A board without GitHub credentials (Remote Control) cannot push | it hands changes back as `git format-patch` files; a cloud session applies and pushes them | observed, Tron on the AGX Orin |

- [game-bundles.md](game-bundles.md): how a game builds its universal bundle (code and multimedia, no binary) and how this platform installs it.
