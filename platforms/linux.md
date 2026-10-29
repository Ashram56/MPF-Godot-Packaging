# Linux

Debian and Ubuntu (apt), Fedora, RHEL and their rebuilds (dnf), Arch and its derivatives (pacman); x86_64 or
arm64. Installer: `install/install_linux.sh`. A Jetson runs the same installer, plus its own steps:
[jetson.md](jetson.md). Back to [all platforms](README.md).

## The one line

```sh
bash <(curl -fsSL https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/install/install_linux.sh)
```

Options go after the line: `bash <(curl ...) --no-monitor --proc`. Settings go in front:
`MPF_GODOT_GITHUB_TOKEN=github_pat_... bash <(curl ...)`. From a clone: `install/install_linux.sh [--dry-run]`.

## Requirements

| Item | Value |
|---|---|
| Distribution | glibc 2.28+: Ubuntu 20.04+, Debian 11+, Fedora 36+, current Arch; detected from `ID` / `ID_LIKE` in `/etc/os-release` |
| CPU | x86_64 or arm64 (aarch64) |
| Graphics | Vulkan 1.0 or OpenGL 3.3 (Mesa 20+; Mesa's software renderer works too) |
| Sound | PulseAudio or PipeWire (`pipewire-pulse`), else ALSA |
| Rights | root or `sudo` |
| Disk | about 2 GB free (3 GB with MPF Monitor) |
| MPF Monitor | PyQt6 wheels: Qt 6.11 needs glibc 2.34 on x86_64 (older systems get an older Qt from pip); arm64 takes PyQt6 < 6.8 (glibc 2.28) |

## What the installer does

| Step | What | How |
|---|---|---|
| 1 | GitHub access, first | when git is already there and the script clones (`github_auth`) |
| 2 | Distribution and CPU | apt, dnf or pacman family; x86_64 or aarch64; MPF Monitor left out on arm64 with glibc < 2.28 |
| 3 | Display | no `DISPLAY` and no `WAYLAND_DISPLAY`: Xvfb is added (or `--xvfb`) |
| 4 | Python 3.11 | already there (`python3.11`, `/usr/bin`, `/usr/local/bin`, `python3`, uv's), else planned: distro package, deadsnakes (Ubuntu), uv |
| 5 | System packages | the missing ones of the lists below, in one `apt-get` / `dnf` / `pacman` call |
| 6 | Python 3.11, if still missing | deadsnakes PPA (Ubuntu), then uv: the uv wheel from PyPI (`manylinux_2_17`), `uv python install 3.11` |
| 7 | Repository | clone into `MPF_GODOT_DIR`; an existing clone: `clear_untracked_in_update`, `git pull --ff-only`, or switch to `MPF_GODOT_BRANCH` when its branch is gone |
| 8 | Toolchain | `python -m mpf_godot setup` (Godot `linux.x86_64` or `linux.arm64`, with a `toolchain/godot/godot` link) |
| 9 | P-ROC (`--proc`) | `install/build_pinproc.sh` into `.venv`, then `install/99-pinproc.rules` to `/etc/udev/rules.d/` and a udev reload |
| 10 | Jetson | `/etc/nv_tegra_release` present: `platforms/jetson/install_jetson_hwdec.sh` ([jetson.md](jetson.md)); a failure there is a warning |
| 11 | Done | prints `.venv/bin/python -m mpf_godot info`, `addons`, `run` |

### Packages

| Group | apt (Debian, Ubuntu) | dnf (Fedora, RHEL) | pacman (Arch) |
|---|---|---|---|
| Base | `git ca-certificates curl unzip` | same | same |
| Godot | `libgl1 libegl1 libgl1-mesa-dri libglx-mesa0 libvulkan1 mesa-vulkan-drivers libx11-6 libxcursor1 libxinerama1 libxrandr2 libxi6 libxext6 libxrender1 libxkbcommon0 libwayland-client0 libwayland-cursor0 libwayland-egl1 libdecor-0-0 libfontconfig1 libasound2 libpulse0 libdbus-1-3 libudev1` | `mesa-libGL mesa-libEGL mesa-dri-drivers mesa-vulkan-drivers vulkan-loader libX11 libXcursor libXinerama libXrandr libXi libXext libXrender libxkbcommon libwayland-client libwayland-cursor libwayland-egl libdecor fontconfig alsa-lib pulseaudio-libs dbus-libs systemd-libs` | `libglvnd mesa vulkan-icd-loader libx11 libxcursor libxinerama libxrandr libxi libxext libxrender libxkbcommon wayland libdecor fontconfig alsa-lib libpulse dbus systemd-libs` |
| MPF Monitor (Qt) | `libglib2.0-0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1` | `glib2 libxkbcommon-x11 xcb-util-cursor xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm` | same names as dnf |
| Xvfb | `xvfb xauth` | `xorg-x11-server-Xvfb xorg-x11-xauth` | `xorg-server-xvfb xorg-xauth` |
| Python 3.11 | `python3.11 python3.11-venv python3.11-dev` | `python3.11 python3.11-devel` | none (uv) |
| P-ROC build | `build-essential cmake pkg-config libusb-1.0-0-dev libusb-dev libftdi1-dev` | `gcc-c++ make cmake pkgconf-pkg-config libusb1-devel libusb-compat-0.1-devel libftdi-devel` | `base-devel cmake pkgconf libusb libusb-compat libftdi` |

Where Python 3.11 comes from:

| Distribution | Source |
|---|---|
| Debian 12 | the distribution's `python3.11` |
| Ubuntu 22.04, 24.04 | deadsnakes PPA (22.04's own package is a 3.11.0 release candidate, 24.04 has none) |
| Fedora, RHEL 9 | `dnf install python3.11` |
| Arch, Debian 13, Ubuntu 20.04 (JetPack 5), anything else | uv's standalone CPython 3.11 in `~/.local/share/uv/python` (uv itself in `~/.local/share/mpf-godot/uv`): no compiler, nothing system-wide |

## Options

| Option | Effect |
|---|---|
| `--dry-run` | print the plan, change nothing |
| `--yes`, `-y` | no questions |
| `--no-monitor` | leave MPF Monitor and its Qt libraries out (`--monitor` accepted) |
| `--proc` | build libpinproc and pypinproc, install the udev rule |
| `--xvfb` | add Xvfb even with a display (automatic without one) |
| `--no-setup` | prerequisites only |
| `--no-jetson` | on a Jetson, skip the hardware video decoder |
| `--python-any` | accept any Python 3.10 to 3.14 already installed |
| `-- ARGS` | passed to `python -m mpf_godot setup` |

| Environment | Default | Meaning |
|---|---|---|
| `MPF_GODOT_DIR` | `~/MPF-Godot` | clone folder |
| `MPF_GODOT_BRANCH` | `main` | branch |
| `MPF_GODOT_REPO` | this repository | repository to clone |
| `MPF_GODOT_GITHUB_TOKEN` | unset (`GITHUB_TOKEN`, `GH_TOKEN`) | token for a private fork |
| `MPF_GODOT_HWDEC` | `1` | `0` skips the Jetson decoder install (as `--no-jetson`) |
| `UV_VERSION` | `0.12.22` | uv release used for the standalone Python |
| `MPF_GODOT_OS_RELEASE`, `MPF_GODOT_NV_RELEASE` | `/etc/os-release`, `/etc/nv_tegra_release` | for tests: a fake distribution or Jetson |
| `GODOT` | unset | a Godot 4.6.x installed by hand |
| `MPF_GODOT_PIN` | unset | at run time: `0` turns core pinning off |

## A private repository and its token

The repository is public, so none of this runs for it. A private fork (`MPF_GODOT_REPO`) needs a GitHub token,
never a password; `github_auth` in `install/install_linux.sh` and `install/install_macos.sh`, `Invoke-GitHubAuth`
in `install/install_windows.ps1`:

| Step | Why |
|---|---|
| Test anonymously first (`git -c credential.helper= ls-remote`) | a token that cannot read a public repository (fine-grained for other repositories, expired) would make git fail on it |
| Then try the credentials git already has | no question when the user is set up already |
| Token from `MPF_GODOT_GITHUB_TOKEN`, else asked on `/dev/tty` | a fine-grained token with Contents: read-only |
| Strip all whitespace, print its length and type, never the token | a paste from an editor carried spaces or a line break; a truncated paste shows (fine-grained about 93 characters, classic 40) |
| Token in the URL for this run only: `GIT_CONFIG_KEY_0=url.https://x-access-token:TOKEN@<repo>.insteadOf` | setup inherits it through the environment; nothing is written to `~/.gitconfig` |
| `git ls-remote` again; stop with a clear message if it fails | name the repository the token cannot read |
| `git credential approve` | the credential helper, if any, keeps it for later pulls |

`curl` and `irm` get a 404 for a private repository's raw file, so the one line cannot fetch itself there: clone
first, then run the installer from the clone. Found 2026-10-04 to 2026-10-07 on a Stern SAM recreation (observed).

## Findings

### 1. Ubuntu 24.04 renamed libraries (t64)
- **Problem:** `apt-get install libasound2` failed on Ubuntu 24.04.
- **Cause:** the 64-bit `time_t` transition renamed some libraries (`libasound2` to `libasound2t64`).
- **Fix:** `install/install_linux.sh`, `apt_name()`: when a name is not in the apt lists and `<name>t64` is, use the
  latter; `install_pkgs()` also counts an installed `<name>t64` as present. The lists are refreshed first.
- **Versions:** Ubuntu 24.04, Debian 13.
- **Found:** 2026-10-03, code.

### 2. `apt-cache | grep -q` fails under pipefail
- **Problem:** the package checks said a package was missing when it was there.
- **Cause:** with `set -o pipefail`, `grep -q` exits on the first match, `apt-cache` gets SIGPIPE, and the pipe fails.
- **Fix:** `apt_known()` captures `apt-cache show` in a variable, then greps it. Same pattern for `ldconfig -p` on
  the Jetson (`ld_cache()` in `platforms/jetson/install_jetson_hwdec.sh`).
- **Versions:** any bash with `set -o pipefail`.
- **Found:** 2026-10-03, code.

### 3. Python 3.11: distribution, deadsnakes, uv
- **Problem:** many distributions have no final Python 3.11 package.
- **Cause:** Ubuntu 22.04's is a release candidate, 24.04 and Arch only have newer ones, Ubuntu 20.04 has 3.8.
- **Fix:** `find_python()`, `apt_has_python311()` (rejects `~rc` and `~b` versions), `deadsnakes()`,
  `uv_python()`: the distribution's final 3.11, else the deadsnakes PPA on Ubuntu, else uv's standalone build.
- **Versions:** uv 0.12.22.
- **Found:** 2026-10-03, code.

### 4. deadsnakes failed silently and installed a release candidate
- **Problem:** on Ubuntu 22.04, the install got Python 3.11.0rc1.
- **Cause:** `set -e` is off inside a function called with `||`; `add-apt-repository` failed, the function went on,
  and apt installed Ubuntu's own `python3.11`.
- **Fix:** `deadsnakes()`: `|| return 1` after `add-apt-repository` and `apt-get update`, then
  `apt_has_python311 || return 1`, so uv takes over.
- **Versions:** Ubuntu 22.04 (JetPack 6).
- **Found:** 2026-10-05, observed.

### 5. A dead venv
- **Problem:** setup stopped when `.venv/bin/python` pointed to an interpreter that was gone.
- **Cause:** the Python the venv was made from (a deadsnakes or uv interpreter) was removed or replaced.
- **Fix:** `mpf_godot/setup_toolchain.py`, `Setup.venv()`: if the venv folder exists but its Python does not,
  `python -m venv --clear`.
- **Versions:** all.
- **Found:** 2026-10-05, observed.

### 6. libdecor missing on Ubuntu 20.04
- **Problem:** the apt step failed on Ubuntu 20.04 (JetPack 5).
- **Cause:** `libdecor-0-0` (Wayland window decorations, optional for Godot) does not exist in 20.04.
- **Fix:** `install_pkgs()` skips `libdecor-0-0` when apt does not know it, with a note.
- **Versions:** Ubuntu 20.04.
- **Found:** 2026-10-05, observed.

### 7. MPF Monitor on arm64: no PyQt6 wheel
- **Problem:** setup stopped installing MPF Monitor on JetPack 5 and 6.
- **Cause:** PyQt6 6.8+ ships Linux arm64 wheels for glibc 2.39+ only; pip fell back to the source package,
  which needs qmake.
- **Fix:** `mpf_godot/toolchain.py`, `MONITOR_REQUIREMENTS`: `PyQt6>=6.4.2,<6.8` on Linux aarch64 (glibc 2.28
  wheels); `install/install_linux.sh` leaves the monitor out below glibc 2.28.
  [../fixes/mpf-monitor/pyqt6-arm64-glibc.md](../fixes/mpf-monitor/pyqt6-arm64-glibc.md).
- **Versions:** PyQt6 6.7.1 checked on an emulated Ubuntu 22.04 (glibc 2.35); JetPack 5 has glibc 2.31.
- **Found:** 2026-10-05, observed.

### 8. No screen: Xvfb
- **Problem:** Godot cannot open a window on a server, in CI or in a container.
- **Cause:** no X or Wayland display.
- **Fix:** the installer adds `xvfb xauth` when `DISPLAY` and `WAYLAND_DISPLAY` are unset (or `--xvfb`);
  `mpf_godot/launcher.py`, `godot_command()`, starts Godot under `xvfb-run -a -s "-screen 0 1280x720x24"`
  (`toolchain.needs_virtual_display()`). It renders on the CPU (Mesa llvmpipe).
- **Versions:** all.
- **Found:** 2026-10-03, code.

### 9. Godot `--headless` draws nothing
- **Problem:** captures taken with `--headless` were blank.
- **Cause:** `--headless` uses a dummy renderer.
- **Fix:** a real window under Xvfb instead (finding 8); `--headless` only for `--version` in setup.
  [../fixes/godot/headless-draws-nothing.md](../fixes/godot/headless-draws-nothing.md).
- **Versions:** Godot 4.x.
- **Found:** 2026-10-02, observed.

### 10. OpenGL under Xvfb wrote no frames with the render thread
- **Problem:** captures with the `opengl3` renderer wrote no frames.
- **Cause:** Godot's separate render thread with `opengl3` under Xvfb.
- **Fix:** `launcher.godot_command()` adds `--render-thread safe` when `opengl3` is asked for, or with
  `--no-render-thread`. [../fixes/godot/render-thread-setting.md](../fixes/godot/render-thread-setting.md).
- **Versions:** Godot 4.6.3.
- **Found:** 2026-10-09, observed.

### 11. The screen blanks during play
- **Problem:** on a cabinet nobody touches the mouse or keyboard, and X blanked the screens after 5 minutes.
- **Cause:** X's screen saver and DPMS.
- **Fix:** `launcher.keep_screen_on()` runs `xset s off -dpms` on a real X display. GNOME's own idle blanking:
  [jetson.md](jetson.md), finding 8.
- **Versions:** X11.
- **Found:** 2026-10-05, observed (Jetson AGX Orin).

### 12. Godot's main thread waits for a core
- **Problem:** late frames on 4-core ARM boards.
- **Cause:** Godot's main thread (scripts and draw submission) shared cores with its workers and MPF.
- **Fix:** `launcher.core_pinning()`: on Linux with 4+ cores and a real display, Godot's main thread alone on the
  last core; `MPF_GODOT_PIN=0` turns it off.
  [../fixes/godot/core-pinning-main-thread.md](../fixes/godot/core-pinning-main-thread.md).
- **Versions:** measured on a Xavier NX: +1.5 FPS, a third fewer late frames.
- **Found:** 2026-10-09, observed.

### 13. The P-ROC on Linux
- **Problem:** MPF has no pypinproc for Linux, and libftdi needs USB access.
- **Cause:** MPF bundles pypinproc for Windows and an old Intel macOS build only.
- **Fix:** `--proc` builds libpinproc (preble, pinned commit) as a shared library into `/usr/local` and pypinproc
  (missionpinball's Python 3 port) into `.venv` (`install/build_pinproc.sh`), then installs
  `install/99-pinproc.rules` (FTDI 0403:6001 FT245RL and 0403:6015 FT240X, `MODE="0666"`, `uaccess`) and
  reloads udev. In a container without udev the rule applies on the host after a reload.
- **Versions:** the rule matches FTDI's generic IDs, so it also opens other FTDI adapters to local users.
- **Found:** 2026-10-03, code. Real board runs only as dry-run plans in tests.

### 14. `bash <(curl ...)`, not `curl ... | bash`
- **Problem:** piped into bash, the script would read its answers from the pipe.
- **Cause:** `curl | bash` makes the script stdin.
- **Fix:** process substitution in the one line; the token prompt reads `/dev/tty`.
- **Versions:** all.
- **Found:** inferred from the scripts' prompts (packaging agent, section 5).

### 15. Testing arm64 without an ARM machine
- **Problem:** the arm64 install path needs an ARM box.
- **Cause:** CI runners are x86_64.
- **Fix:** an arm64 Ubuntu root under qemu (binfmt) runs the whole install. When Docker Hub rate-limits, make the
  base image with `debootstrap focal` and `docker import`. Godot renders in the cloud with lavapipe
  (`VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json`, `--rendering-method mobile`, under `xvfb-run`).
- **Versions:** Ubuntu 20.04 and 22.04 arm64.
- **Found:** 2026-10-05 to 2026-10-09, observed (packaging agent, section 5a).
