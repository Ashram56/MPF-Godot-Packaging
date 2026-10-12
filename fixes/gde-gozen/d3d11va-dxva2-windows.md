# Videos decode on the CPU on Windows: GPU decoding through Direct3D 11 Video or DXVA2

| | |
|---|---|
| Id | `gde-gozen/d3d11va-dxva2-windows` (this file: `fixes/gde-gozen/d3d11va-dxva2-windows.md`) |
| Component | GDE GoZen |
| Kind | improvement |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` (`src/gozen_video.cpp`, `SConstruct`) |
| Platforms | Windows 10/11 x86_64 (MinGW-w64 cross build); NVIDIA, AMD and Intel GPUs through FFmpeg's hwaccels |
| Found on | Tron Legacy MPF, 2026-10-09 (Tron-Legacy-MPF commit 9f547e5); tested on a Windows PC (Ryzen 7 7800X3D) with d3d11va, merged 2026-10-10 (commit 79a3fff) |
| Fact | observed (d3d11va on one Windows PC; the DLL loads under Wine with system imports only, software decoding 2.3 ms per frame there); DXVA2 compiled in, not seen in use |
| Our fix | [`../../build/gozen/gozen.patch`](../../build/gozen/gozen.patch) (`_hw_device()`, `_get_hw_format()`, `_open_hwaccel()`, `_hw_download()`, the `_WIN32` block of `open()`, SConstruct `lean=yes` Windows libs); built by [`../../build/gozen/build_gozen.sh`](../../build/gozen/build_gozen.sh) `windows` ([`../../build/gozen/build_windows_in_docker.sh`](../../build/gozen/build_windows_in_docker.sh)) |
| Applied by | the committed `addons/gde_gozen/bin/libgozen.windows.template_release.x86_64.dll`, copied by `python -m mpf_godot addons GAME --video` |
| Upstream | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are off on GitHub); status: **draft, not filed** |

## Problem

On Windows, GoZen decodes every video in software. An app playing several videos at once spends CPU cores on it. The
other Windows video add-on we tried (native_video, Media Foundation) stuttered.

## Cause

GoZen opens FFmpeg's software decoder and sets no `hw_device_ctx`. Its Windows build links libvpx and libaom but no
hwaccel.

## Fix

`gozen.patch`, Windows only (`#ifdef _WIN32`; the Linux builds are unchanged):

- FFmpeg 7.1 is built with its Direct3D 11 Video and DXVA2 hwaccels for H.264, HEVC and VP9 (LGPL, no vendor
  library: FFmpeg loads
  `d3d11.dll`, `dxgi.dll`, `d3d9.dll` and `dxva2.dll` at run time).
- `open()` tries the software decoder with `hw_device_ctx` set to a D3D11VA device, else a DXVA2 device
  (`_open_hwaccel()`). One device per type serves every video (`_hw_device()`, made on first use under a mutex, so
  opening a video does not make a device).
- `get_format` (`_get_hw_format()`) takes the GPU's format when FFmpeg offers it, else the first software format: a
  GPU that cannot decode this video (codec, profile, size) falls back to software by itself.
- Each GPU frame is copied back to memory (`av_hwframe_transfer_data()`, NV12 for 8-bit video) in `_hw_download()`,
  then takes the NV12 path of [set-target-size-nv12.md](set-target-size-nv12.md).
- `thread_count = 1` for a GPU decoder: one thread feeds it, and fewer frames are held in flight.
- `GOZEN_HWDEC=0` forces software, `GOZEN_HWDEC=d3d11va` or `dxva2` allows only that one.
- The log says `GoZen: hardware decoding h264 (d3d11va)`, or `GoZen: the GPU cannot decode this h264 video, using
  software`.
- SConstruct `lean=yes` on Windows links `ole32` and `user32` instead of libvpx and libaom
  ([lean-build-option.md](lean-build-option.md)).

There is no decoder-side scaling on Windows: `set_target_size()` only acts with the Jetson decoder.

## How to check

1. On Windows, play a video: the log says `GoZen: hardware decoding h264 (d3d11va)`; Task Manager shows "Video Decode"
   load on the GPU.
2. `GOZEN_HWDEC=dxva2`: the log names dxva2. `GOZEN_HWDEC=0`: software.
3. The DLL's imports are system DLLs only (`objdump -p`: bcrypt, kernel32, msvcrt, ole32, user32).

## Upstream issue (draft, not filed)

**Title:** GPU decoding on Windows through FFmpeg's D3D11VA / DXVA2 hwaccels

**Body:**

```markdown
## Request

On Windows GoZen decodes in software. FFmpeg's own hwaccels decode on any GPU vendor with no extra library, and the
Windows build could use them.

## What we did (a patch on f9448619, Windows only)

- FFmpeg 7.1 configured with `--enable-d3d11va --enable-dxva2` and their H.264, HEVC and VP9 hwaccels; MinGW-w64 cross
  build, everything static. FFmpeg loads d3d11.dll, dxgi.dll, d3d9.dll and dxva2.dll at run time; the DLL imports
  only system DLLs.
- `open()` opens the decoder with `hw_device_ctx` set to a D3D11VA device, else DXVA2. One device per type, made on
  first use, serves every video.
- A `get_format` callback takes the GPU format when offered, else the first software format, so a GPU that cannot
  decode a given video falls back to software by itself.
- Each GPU frame is copied to system memory with `av_hwframe_transfer_data()` (NV12 for 8-bit), then uploaded as
  NV12 (Y as R8, UV as RG8; the YUV shaders take an `nv12` switch).
- `thread_count = 1` with a GPU decoder.
- `GOZEN_HWDEC=0` forces software; `GOZEN_HWDEC=d3d11va` or `dxva2` picks one.

Tested on one Windows PC (d3d11va). Our patch: <link to build/gozen/gozen.patch in MPF-Godot-Packaging>

## Possible next step

Keep the frame on the GPU (a D3D11 texture shared with Godot's D3D12 or Vulkan driver) instead of copying it back.
```
