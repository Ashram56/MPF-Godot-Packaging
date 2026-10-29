# MPF Monitor does not install on Jetson / arm64 Linux (PyQt6 builds from source and fails)

| | |
|---|---|
| Id | `mpf-monitor/pyqt6-arm64-glibc` (this file: `fixes/mpf-monitor/pyqt6-arm64-glibc.md`) |
| Component | MPF Monitor (its PyQt6 requirement) |
| Kind | packaging |
| Affected versions | mpf-monitor 1.0.0 (`PyQt6>=6.4.2`, no upper bound) with PyQt6 6.8 and later; and later until fixed upstream |
| Platforms | Linux arm64 with glibc older than 2.39 (Jetson L4T R35 / JetPack 5: glibc 2.31; L4T R36 / JetPack 6: 2.35; Ubuntu 22.04 arm64) |
| Found on | a Stern SAM recreation on a Jetson, 2026-10-05 |
| Fact | observed (the sdist build failed on JetPack 5/6); the fix checked on an emulated JetPack 6 (Ubuntu 22.04, glibc 2.35): PyQt6 6.7.1 installs from a wheel and `mpfmonitor` imports. The monitor window on a real Jetson: not reported |
| Our fix | [`mpf_godot/toolchain.py`](../../mpf_godot/toolchain.py) `MONITOR_REQUIREMENTS`: `PyQt6>=6.4.2,<6.8; sys_platform == "linux" and platform_machine == "aarch64"`; [`install/install_linux.sh`](../../install/install_linux.sh) leaves the monitor out on arm64 with glibc older than 2.28 |
| Applied by | `python -m mpf_godot setup`, `install/install_linux.sh` |
| Upstream | MPF Monitor, https://github.com/missionpinball/mpf-monitor/issues; status: **draft, not filed** |

## Problem

`pip install mpf-monitor` on a Jetson tries to build PyQt6 from its source package and fails (it needs `qmake`
and a Qt 6 development install).

## Cause

- mpf-monitor 1.0.0 requires `PyQt6>=6.4.2`, so pip takes the newest PyQt6.
- PyQt6 6.8 and later publish Linux arm64 wheels for glibc 2.39+ only (`manylinux_2_39_aarch64`); 6.7's arm64
  wheels need glibc 2.28.
- On an older glibc no 6.8+ wheel fits, and pip falls back to the sdist instead of an older wheel.

## Fix

Cap PyQt6 below 6.8 on Linux aarch64 only; every other platform keeps the newest. Below glibc 2.28 there is no
wheel at all: the Linux installer leaves MPF Monitor out with a note.

## How to check

On arm64 Linux with glibc 2.28 to 2.38: `python -m mpf_godot setup` installs PyQt6 6.7.x from a wheel, and
`.venv/bin/python -c "import mpfmonitor"` works. Without the pin, pip downloads `PyQt6-6.x.tar.gz`
and stops in its build step.

## Upstream issue (draft, not filed)

**Title:** Install fails on arm64 Linux with glibc < 2.39 (PyQt6 6.8+ has no wheel there)

**Body:**

```markdown
**Environment**
- mpf-monitor 1.0.0, Python 3.11, NVIDIA Jetson (Ubuntu 20.04 / L4T R35, glibc 2.31; Ubuntu 22.04 / L4T R36,
  glibc 2.35), aarch64

**Steps to reproduce**
`pip install mpf-monitor==1.0.0` on aarch64 Linux with glibc older than 2.39.

**Expected:** PyQt6 from a wheel.

**Actual:** pip picks the newest PyQt6, whose aarch64 wheels need glibc 2.39 (6.8 and later), falls back to the
source package and fails (no qmake).

**Proposed fix**
In the requirements, cap PyQt6 on aarch64 Linux, where 6.7 still has manylinux_2_28 wheels:

    "PyQt6>=6.4.2,<6.8; sys_platform == 'linux' and platform_machine == 'aarch64'",
    "PyQt6>=6.4.2; sys_platform != 'linux' or platform_machine != 'aarch64'",

or say on the install page: on arm64 Linux with glibc < 2.39, `pip install "PyQt6<6.8"` first. With the cap,
PyQt6 6.7.1 installs from a wheel on Ubuntu 22.04 aarch64 (glibc 2.35) and mpfmonitor imports.
```
