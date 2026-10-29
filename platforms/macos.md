# macOS

macOS 12 Monterey or newer, Intel or Apple silicon. Installer: `install/install_macos.sh`. Back to
[all platforms](README.md).

## The one line

```sh
bash <(curl -fsSL https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/install/install_macos.sh)
```

Options go after the line: `bash <(curl ...) --no-monitor --proc`. Settings go in front:
`MPF_GODOT_DIR=~/mpf bash <(curl ...)`. From a clone: `install/install_macos.sh [--dry-run]`.

## Requirements

| Item | Value |
|---|---|
| OS | macOS 12 or newer (the installer warns on 10.x and 11.x) |
| CPU | Intel or Apple silicon: Godot's universal build runs natively on both |
| Graphics | Metal (directly, or through MoltenVK) |
| Rights | an admin password for the python.org `.pkg` or the Command Line Tools; none with Homebrew in place |
| Disk | about 2 GB free (3 GB with MPF Monitor) |
| P-ROC | Homebrew (`--proc` refuses to run without it) |

## What the installer does

| Step | What | How |
|---|---|---|
| 1 | GitHub access, first | only when cloning and when a real git is there (`/usr/bin/git` counts only once `xcode-select -p` succeeds) |
| 2 | Check the OS | not macOS: only `--dry-run`, which prints the macOS plan (`setup --os macos`) |
| 3 | Homebrew | `brew` on the PATH, `/opt/homebrew/bin/brew` or `/usr/local/bin/brew`; ignored with `--python-org` |
| 4 | Git | in place; else `brew install git`; else `xcode-select --install`, and the installer stops: run it again once the Command Line Tools are in |
| 5 | Python 3.11 | `python3.11` on the PATH, Homebrew's, or the python.org framework (`/Library/Frameworks/Python.framework/Versions/3.11`); else `brew install python@3.11`; else the python.org 3.11.9 universal2 `.pkg` (`sudo installer`), then its `Install Certificates.command` |
| 6 | P-ROC build tools (`--proc`) | `brew install cmake pkg-config libusb libusb-compat libftdi` |
| 7 | Repository | clone into `MPF_GODOT_DIR`; an existing clone: `clear_untracked_in_update`, `git pull --ff-only`, or switch to `MPF_GODOT_BRANCH` when its branch is gone |
| 8 | Toolchain | `python -m mpf_godot setup`: Godot's `macos.universal` zip unpacked with `ditto` into `toolchain/godot/Godot.app` |
| 9 | P-ROC (`--proc`) | `install/build_pinproc.sh --python .venv/bin/python --prefix $(brew --prefix)` |
| 10 | Done | prints `.venv/bin/python -m mpf_godot info`, `addons`, `run` |

## Options

| Option | Effect |
|---|---|
| `--dry-run` | print the plan, change nothing |
| `--yes`, `-y` | no questions |
| `--no-monitor` | leave MPF Monitor out (`--monitor` accepted) |
| `--proc` | build libpinproc and pypinproc (needs Homebrew) |
| `--no-setup` | prerequisites only |
| `--python-org` | the python.org installer even when Homebrew is there |
| `-- ARGS` | passed to `python -m mpf_godot setup` |

| Environment | Default | Meaning |
|---|---|---|
| `MPF_GODOT_DIR` | `~/MPF-Godot` | clone folder |
| `MPF_GODOT_BRANCH` | `main` | branch |
| `MPF_GODOT_REPO` | this repository | repository to clone |
| `MPF_GODOT_GITHUB_TOKEN` | unset (`GITHUB_TOKEN`, `GH_TOKEN`) | token for a private fork ([linux.md](linux.md#a-private-repository-and-its-token) has the flow) |
| `GODOT` | unset | a Godot 4.6.x installed by hand |

`MPF_GODOT_HWDEC` is for the Jetson only and has no effect here.

## Findings

### 1. python.org Python cannot download over HTTPS
- **Problem:** downloads from Python failed with certificate errors after installing the python.org build.
- **Cause:** python.org's macOS builds bring no CA certificates; its `Install Certificates.command` installs
  certifi's.
- **Fix:** `install/install_macos.sh` runs `/Applications/Python 3.11/Install Certificates.command` after the
  `.pkg`. Should that be skipped, `mpf_godot/setup_toolchain.py`, `download()`, retries with `curl` when urllib
  fails.
- **Versions:** python.org 3.11.9 (`python-3.11.9-macos11.pkg`), the last 3.11 release with a macOS installer.
- **Found:** 2026-10-03, code.

### 2. `/usr/bin/git` is a stub
- **Problem:** calling `git` on a Mac without the Command Line Tools opens Apple's installer instead of running.
- **Cause:** `/usr/bin/git` is a shim until the Xcode Command Line Tools are installed.
- **Fix:** `install/install_macos.sh` uses `/usr/bin/git` only when `xcode-select -p` succeeds; otherwise
  Homebrew's git, or it runs `xcode-select --install` and stops with "run this script again".
- **Versions:** every macOS.
- **Found:** 2026-10-03, code.

### 3. Godot.app must be unpacked with `ditto`
- **Problem:** unpacking the Godot zip with Python's `zipfile` loses the app bundle's symlinks, permissions and
  code signature.
- **Cause:** `zipfile` does not restore macOS metadata.
- **Fix:** `mpf_godot/setup_toolchain.py`, `unzip()`: on macOS, `ditto -x -k`, which keeps the signature (the
  build is signed by the Godot project).
- **Versions:** Godot 4.6.3 `macos.universal`.
- **Found:** 2026-10-03, code.

### 4. MPF's bundled P-ROC module does not load on Apple silicon
- **Problem:** `--hw proc` could not import `pinproc` on a current Mac.
- **Cause:** MPF bundles `mpf/platforms/pinproc/osx/pinproc.so`, an old i386/x86_64 build linked against
  `libpinproc`, `libftdi1` and `libusb-0.1` dylibs.
- **Fix:** `--proc` builds libpinproc (pinned commit) and pypinproc (the Python 3 port) with
  `install/build_pinproc.sh` against Homebrew's `libusb`, `libusb-compat` and `libftdi`, into `$(brew --prefix)`.
- **Versions:** MPF 0.80.1.
- **Found:** 2026-10-03, code. No run on a real P-ROC from a Mac in the sources.

### 5. macOS claims the P-ROC as a serial port
- **Problem:** the board shows as `/dev/tty.usbserial*` and libftdi cannot open it.
- **Cause:** macOS' own FTDI serial driver takes the device.
- **Fix:** install FTDI's D2xxHelper and reboot; the installer prints this after the `--proc` build.
- **Versions:** not stated.
- **Found:** inferred (libpinproc's README); not tried.

### 6. native_video on macOS: rebuilt dylibs
- **Problem:** the native_video add-on crashed or failed to open videos (heap overrun in gdzig, seen on Windows).
- **Cause:** gdzig's `engine_allocator` under-allocates aligned blocks (`addons/native_video/FIX.md`).
- **Fix:** `addons/native_video/libnative_video.macos.{debug,release}.dylib` rebuilt with the gdzig heap fix by a
  macOS CI workflow (`macos-15` runner). Do not replace them with an upstream zip.
- **Versions:** native_video v0.3.1, Godot 4.6 (the add-on needs 4.6).
- **Found:** 2026-10-04, code. Playback on a Mac is
  not reported in the sources.

### 7. No GoZen on macOS
- **Problem:** GDE GoZen (FFmpeg) has no macOS build here.
- **Cause:** only Linux x86_64, Linux arm64 and Windows x86_64 are built (`build/gozen/`).
- **Fix:** `python -m mpf_godot addons GAME --video` copies native_video only on macOS
  (`toolchain.gozen_supported()`, `native_video_supported()`); it decodes with AVFoundation.
- **Versions:** all.
- **Found:** code.

### 8. `bash <(curl ...)`, not `curl ... | bash`
- **Problem:** piped into bash, the script would read its own questions' answers from the pipe.
- **Cause:** `curl | bash` makes the script stdin; `bash <(curl)` keeps the terminal as stdin and lets options
  follow the line.
- **Fix:** the one line uses process substitution. The token prompt reads `/dev/tty`.
- **Versions:** bash 3.2 (macOS) and later.
- **Found:** inferred from the scripts' prompts (packaging agent, section 5).
