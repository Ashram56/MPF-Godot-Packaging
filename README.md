# MPF + Godot: one-line install, with every fix we carry

Installs the [Mission Pinball Framework](https://missionpinball.org) (MPF), MPF Monitor, Godot and GMC (MPF's Godot
media controller) on Windows, macOS, Linux and NVIDIA Jetson boards, with one line, and applies every fix and
improvement our pinball projects needed. Game agnostic: any MPF game with a Godot display can use it.

Every fix is documented on its own in [fixes/](fixes/README.md) (problem, cause, our fix, affected versions,
platforms) with a draft issue for the upstream project. Every platform's set-up and what we learned there is in
[platforms/](platforms/README.md); quick tips for WSL, hosts without usbipd and the Xavier NX: [platforms/tips.md](platforms/tips.md).
All Godot / GoZen / MPF and platform findings of the Stern SAM recreations are kept here (what goes where: [CONTRIBUTING.md](CONTRIBUTING.md));
the ROM extraction and re-coding agents are in [Stern-SAM-Decryption](https://github.com/Ashram56/Stern-SAM-Decryption).

Flashable images (Raspberry Pi 4, Jetson Xavier NX, x86 mini PC) share their setup page, read-only production mode and game loader in
[common/](common/): [games and bundles, putting your own MPF code or a game in an image](common/games/README.md),
read-only mode, [setup page and network](common/netconfig/README.md).

| Pinned | Version | Why this one |
|---|---|---|
| Python | 3.11 (3.10 to 3.14 accepted) | every pin below is tested on it |
| MPF | 0.80.1 | GMC 1.0's MPF; plus `ruamel.yaml.clib==0.2.14` ([why](fixes/mpf/ruamel-yaml-clib-0.2.15.md)) |
| MPF Monitor | 1.0.0 | plus its missing window files ([why](fixes/mpf-monitor/missing-ui-files.md)) |
| Godot | 4.6.3, the official build for the host | the native_video add-on needs 4.6; GMC 1.0 needs 4.5+ |
| GMC | 1.0.0, patched | [fixes/gmc/](fixes/README.md#gmc) |

All pins live in one file, [`mpf_godot/toolchain.py`](mpf_godot/toolchain.py), each with its reason.

## Install

One line per platform, on a computer with nothing installed. It installs what is missing (Git, Python 3.11, the
system libraries Godot and Qt need), clones this repository into `~/MPF-Godot` (Windows: `%USERPROFILE%\MPF-Godot`),
then installs MPF, MPF Monitor, Godot and the patched GMC there. Run it again to update: it pulls and redoes only
what changed.

**Windows 10/11** (PowerShell; never as `irm ... | iex`, [why](platforms/windows.md)):

```powershell
powershell -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/install/install_windows.ps1) -join [char]10))"
```

**macOS 12+** (Intel or Apple silicon):

```sh
bash <(curl -fsSL https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/install/install_macos.sh)
```

**Linux** (Debian, Ubuntu, Fedora, RHEL, Arch; x86_64 or arm64; on a Jetson it also installs the hardware video
decoder):

```sh
bash <(curl -fsSL https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/install/install_linux.sh)
```

Options go at the end of the line (Windows: inside the quotes, after `-join [char]10))`):

| Option (Windows) | Linux and macOS | What it does |
|---|---|---|
| `-DryRun` | `--dry-run` | print the plan, change nothing |
| `-Yes` | `--yes` | no questions |
| `-NoMonitor` | `--no-monitor` | without MPF Monitor (and Qt) |
| `-Proc` | `--proc` | the P-ROC driver: Windows the VC++ runtime and a D2XX check; Linux and macOS build libpinproc and pypinproc ([why](fixes/mpf/pinproc-linux-macos.md)); Linux also the udev rule |
| `-NoSetup` | `--no-setup` | prerequisites only |
| | `--no-jetson` | Linux: no Jetson video decoder install on a Jetson |
| | `--python-any` | Linux: any Python 3.10 to 3.14 already there instead of 3.11 |
| `-NoWinget`, | `--python-org` (macOS) | the downloaded installers instead of winget / Homebrew |
| anything else | after `--` | passed to `python -m mpf_godot setup`, e.g. `--extra pillow` |

Environment: `MPF_GODOT_DIR` (install folder; keep it out of OneDrive), `MPF_GODOT_BRANCH`, `MPF_GODOT_REPO` (a fork),
`MPF_GODOT_GITHUB_TOKEN` (only for a private fork), `GODOT` (use a Godot you installed yourself).

From a clone instead: `bash install/install_linux.sh`, `bash install/install_macos.sh`, or
`powershell -ExecutionPolicy Bypass -File install\install_windows.ps1`. With Python and Git already there:
`python -m mpf_godot setup`.

## Use it in a game

From the install folder (`.venv\Scripts\python` on Windows):

```sh
.venv/bin/python -m mpf_godot info                    # paths and versions
.venv/bin/python -m mpf_godot addons GAME [--video]   # the patched GMC (and the video add-ons) into GAME/addons/
.venv/bin/python -m mpf_godot run GAME [--monitor]    # Godot (GMC) first, then MPF, optionally MPF Monitor
```

`GAME` is the folder with `project.godot` and MPF's `config/`; [`examples/minimal`](examples/minimal/) is the smallest
one and the smoke test. `run` takes `-c config,other` (MPF config files), `--seconds N`, `--text-ui`,
`--no-render-thread`, `--xvfb`, and Godot arguments after `--`. Logs: `GAME/logs/godot.log` and `GAME/logs/mpf.log`.

A game with its own launcher can use the toolchain directly: the venv's `mpf`, the Godot in `toolchain/godot/`
(or `GODOT`), and the patched GMC in `toolchain/addons/mpf-gmc/` (or `python -m mpf_godot patch-gmc DIR` on its own
copy).

`--video` adds [GDE GoZen](addons/gde_gozen/README.md) (FFmpeg video with GPU decoding: Direct3D 11 on Windows, the
Jetson's NVDEC on Linux arm64) and [native_video](addons/native_video/README.md) (Windows and macOS), each with our
fixes and prebuilt here; [build/](build/) rebuilds them from pinned sources.

## What is where

| Folder | What |
|---|---|
| [`install/`](install/) | the one-line installers per OS, and the P-ROC driver build |
| [`mpf_godot/`](mpf_godot/) | Python, standard library only: pins and paths (`toolchain.py`), the install (`setup_toolchain.py`), the GMC patch (`gmc_patch.py`), the launcher (`launcher.py`), Windows/OneDrive-safe file operations (`fsutil.py`) |
| [`fixes/`](fixes/README.md) | one document per fix or improvement, each with its upstream issue draft; test projects and repro programs in `fixes/repro/` |
| [`platforms/`](platforms/README.md) | per platform: what the installer does and every finding; the Jetson kit (`platforms/jetson/`: decoder install, self-test, a minimal Xavier NX image) |
| [`addons/`](addons/) | Godot video add-ons with our fixes, prebuilt |
| [`build/`](build/) | how those add-ons are rebuilt (patches, Docker builds) |
| [`examples/minimal/`](examples/minimal/) | the smallest MPF + GMC game |
| [`tests/`](tests/) | `python -m unittest discover -s tests`: installers in dry run (pwsh too when installed), the GMC patch, the launcher, and the smoke test once the toolchain is installed |

## Tests

`python -m unittest discover -s tests`. The installers run in their dry-run modes; `PWSH=/path/to/pwsh` adds the
Windows installer's. After a real install, `tests/test_smoke.py` starts `examples/minimal` and checks that MPF
connects to GMC. CI (`.github/workflows/test.yml`) runs on pushes to `main` only: test before pushing a branch.

Tested so far (2026-10-12): the Linux one line on Ubuntu 24.04 x86_64, both with Python 3.11 present and in a fresh
Docker container as a sudo user, where the deadsnakes PPA was unreachable and Python 3.11 came from uv; the smoke
test on both; the Windows installer's one-line form in dry run with pwsh 7.4 on Linux. The first CI run on `main`
installed the whole toolchain from a clone on GitHub's Windows (x86_64) and macOS (arm64) runners; a game has not
been played on a real Windows or macOS computer yet. Jetson results are in [platforms/jetson.md](platforms/jetson.md).

## Upstream

Each fix document ends with an issue draft. None is filed yet: they go upstream one issue per fix when the owner
says so. [fixes/README.md](fixes/README.md) lists them by project.

## Credits and licences

MPF, MPF Monitor and GMC: the Mission Pinball Framework team (MIT). Godot: the Godot Engine contributors (MIT). GDE
GoZen: Voylin (LGPL 2.1, with FFmpeg). godot-native-video: Clayton Kercek. jetson-ffmpeg: gjrtimmer. libpinproc and
pypinproc: Gerry Stellenberg, Adam Preble and the MPF team. Each add-on keeps its own licence file.
