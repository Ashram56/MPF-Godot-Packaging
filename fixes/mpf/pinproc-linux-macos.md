# No P-ROC driver for MPF on Linux, nor on Apple silicon Macs

| | |
|---|---|
| Id | `mpf/pinproc-linux-macos` (this file: `fixes/mpf/pinproc-linux-macos.md`) |
| Component | MPF (its bundled pypinproc); pypinproc, libpinproc |
| Kind | packaging |
| Affected versions | MPF 0.80.1; pypinproc and libpinproc (no wheels or binary releases known to us); and later until fixed upstream |
| Platforms | Linux x86_64 and arm64 (Jetson included); macOS (Apple silicon: none; Intel: an old build) |
| Found on | a Stern SAM recreation (Tron Legacy MPF), 2026-10-03 |
| Fact | code (MPF 0.80.1 wheel: `mpf/platforms/pinproc/`, `p_roc_common.py`); the build tested as dry-run plans only, no run on a real board reported |
| Our fix | [`install/build_pinproc.sh`](../../install/build_pinproc.sh) (libpinproc `286c566`, pypinproc `71ad50c`, pinned), [`install/99-pinproc.rules`](../../install/99-pinproc.rules) (udev) |
| Applied by | `install/install_linux.sh --proc`, `install/install_macos.sh --proc`, `python -m mpf_godot setup --proc` |
| Upstream | pypinproc, https://github.com/missionpinball/pypinproc/issues (wheels); MPF, https://github.com/missionpinball/mpf/issues (docs); status: **draft, not filed** |

## Problem

`mpf game` with `platform: p_roc` stops on Linux and on Apple silicon Macs:

```
Could not import "pinproc". Either the library is not installed or is missing some of its dependencies.
```

## Cause

- MPF's wheel bundles pypinproc for two OSes only (`mpf/platforms/pinproc/`): `windows/pinproc.cp38..cp314-win32|win_amd64.pyd`
  and `osx/pinproc.so`. `p_roc_common.py` imports `pinproc`, then the bundled one for `darwin` or `win32`;
  on Linux it raises `ImportError`.
- `osx/pinproc.so` is a universal binary for i386 and x86_64 only, linked against `libpinproc.2.0.dylib`,
  `libftdi1.2.dylib` and `/usr/local/lib/libusb-0.1.4.dylib`, which the user must provide. It does not load in an
  arm64 Python.
- Neither pypinproc nor libpinproc publishes wheels or binaries, so the user must build both.
- On Linux, libftdi opens the board's FTDI chip through libusb: without a udev rule only root can.

## Fix

`install/build_pinproc.sh` builds libpinproc (shared library, CMake, into `/usr/local`) and pypinproc (the
Python 3 port, into the venv) from pinned commits; needs CMake, pkg-config, libusb-1.0, libusb-compat and
libftdi1 headers, which the installers add with `--proc`. Safe to re-run: nothing is built when `import pinproc`
works. On Linux `99-pinproc.rules` opens FTDI 0403:6001 (FT245RL, P-ROC) and 0403:6015 (FT240X) to local users.
These are FTDI's generic IDs, so the rule also opens other FTDI USB-serial adapters.

## How to check

`install/build_pinproc.sh --dry-run` prints the plan. After the build: `.venv/bin/python -c "import pinproc"`.
On a board: `mpf game . -c config,<proc overlay>` connects (not yet reported on real hardware).

## Upstream issue (draft, not filed)

**Title:** Publish pypinproc wheels for Linux (x86_64, aarch64) and macOS (arm64, x86_64)

**Body:**

```markdown
**Environment**
- MPF 0.80.1 with a P-ROC / P3-ROC; Linux x86_64 and aarch64, macOS on Apple silicon

**Problem**
MPF bundles pypinproc only for Windows (`mpf/platforms/pinproc/windows/*.pyd`) and an old macOS build
(`mpf/platforms/pinproc/osx/pinproc.so`: i386 + x86_64, linked against libpinproc 2.0, libftdi1 and
/usr/local/lib/libusb-0.1.4.dylib, which the user must install). On Linux and Apple silicon, MPF stops with
`Could not import "pinproc"` and users must build libpinproc and pypinproc themselves. Linux users also need a
udev rule for the FTDI chip, which no install page gives.

**What we do today** (works as a build, tested as a plan; not yet on a board)
- libpinproc (preble/libpinproc dev, commit 286c566) as a shared library: `cmake -DBUILD_SHARED_LIBS=ON
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON` then `cmake --install`
- pypinproc (missionpinball/pypinproc, commit 71ad50c): `pip install <checkout>`
- deps: cmake, pkg-config, libusb-1.0, libusb-compat (`libusb`), libftdi1 with headers (apt or Homebrew)
- udev: `SUBSYSTEM=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", MODE="0666", TAG+="uaccess"`
  (and 6015 for FT240X boards)

**Proposed**
1. pypinproc: build wheels with cibuildwheel (manylinux x86_64/aarch64, macOS arm64/x86_64) with libpinproc and
   libftdi/libusb vendored (auditwheel / delocate), published to PyPI as `pypinproc`.
2. MPF: depend on it as an extra (`pip install mpf[proc]`) instead of bundling, or bundle the new macOS arm64 build.
3. MPF docs: the udev rule above for Linux.
```
