# ZeDMD does not start with MPF's zedmd platform (library fails to load, wrong architecture on a Pi)

| | |
|---|---|
| Id | `mpf/zedmd-native-serial` (this file: `fixes/mpf/zedmd-native-serial.md`) |
| Component | MPF (its `zedmd` platform, libzedmd Python extension) |
| Kind | bug |
| Affected versions | MPF 0.80.1; and later until fixed upstream |
| Platforms | Linux arm64 (Raspberry Pi, Jetson); any Python other than the one the extension was built for |
| Found on | a Stern SAM recreation (Tron Legacy MPF), 2026-10-25 |
| Fact | observed (Python 3.13 on Linux x64: the extension does not import); code (`mpf/platforms/zedmd.py`) for the architecture test |
| Our fix | [`mpf_godot/zedmd_native.py`](../../mpf_godot/zedmd_native.py): an MPF platform that speaks the ZeDMD serial protocol with pyserial |
| Applied by | a game's config: `mpf: platforms: zedmd_native: mpf_godot.zedmd_native.ZedmdNativePlatform`, `hardware: rgb_dmd: zedmd_native` |
| Upstream | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, not filed** |

## Problem

With `hardware: rgb_dmd: zedmd`, MPF stops with `Failed to load ZeDMD libraries.`; the import error under it reads
`.../zedmd_lib/linux_x64/extending.so: undefined symbol: _PyThreadState_UncheckedGet` (Python 3.13).

## Cause

- The pybind11 extensions in `mpf/platforms/zedmd_lib/` are compiled for one Python build each.
- `zedmd.py` chooses the library with `if platform.machine in ("arm64", "aarch64")`: `platform.machine` is the function,
  never called, so the test is always false and a Raspberry Pi loads `linux_x64`.

## Fix

A platform in this repository that does not need the compiled library. It follows libzedmd's `ZeDMDComm` (PPUC/libzedmd):
handshake (`FRAME` `ZeDMD` 0x0c), reply of 64 bytes (width, height, write size), zone packets (8x4 pixels, RGB888,
index, black zones as index + 128), render (0x06), clear (0x0a), every write acknowledged `ZeDMD` `A`. USB serial only.

For less CPU and latency, [`native/zedmd_feed/zedmd_feed.c`](../../native/zedmd_feed/zedmd_feed.c) does the same in C (libc only, Linux/macOS): it reads raw RGB888 frames on stdin, so a Godot or other front end can pipe the DMD to it without MPF. Tested on a pty only (`tests/test_zedmd_feed.py`).
Not tried on a real ZeDMD yet; the protocol was read from libzedmd's source, not captured.

## How to check

`python -m pytest tests/test_zedmd_native.py` (a fake device). On hardware: start MPF with the config above and the
game sending `rgb_dmd_frame`; the log shows `ZeDMD 128x32 firmware ...`.

## Upstream issue (draft, not filed)

**Title:** zedmd platform: `platform.machine` is not called, so arm64 loads the x64 library

**Body:**

```markdown
mpf/platforms/zedmd.py: `if platform.machine in ("arm64", "aarch64"):` compares the function object, never its result,
so ARCH is always "x64" (Raspberry Pi, Jetson, Linux arm64). Expected `platform.machine()`. Also the extensions in
zedmd_lib are built for one Python version only (Python 3.13: "undefined symbol: _PyThreadState_UncheckedGet").
Proposed: call `platform.machine()`.
```
