# Hardware decoding is slow on JetPack 5: every plane of every frame is mapped and unmapped for the CPU

| | |
|---|---|
| Id | `jetson-ffmpeg/planes-mapped-once` (this file: `fixes/jetson-ffmpeg/planes-mapped-once.md`) |
| Component | jetson-ffmpeg |
| Kind | improvement |
| Affected versions | jetson-ffmpeg at `8d70c17efeee57f4d956df500fec78a73f8c27d4` (v3.10.0), libnvmpi with NvUtils (`WITH_NVUTILS`); later revisions not checked |
| Platforms | measured on Jetson Xavier NX, L4T R35.6.4 (JetPack 5.1.4); the same patch is installed on Jetson AGX Orin, L4T R36.4.3 (not measured or re-checked there) |
| Found on | Tron Legacy MPF, 2026-10-09 (Tron-Legacy-MPF commit 042695c) |
| Fact | observed (decode speed and CPU time per frame on the Xavier NX) |
| Our fix | [`../../build/gozen/nvmpi_flush.patch`](../../build/gozen/nvmpi_flush.patch), `src/` part (`copyNvBufToFrame()` in `nvmpi_dec_api.cpp`, `nvmpi_frame_buffer::destroy()`) |
| Applied by | [`../../platforms/jetson/install_jetson_hwdec.sh`](../../platforms/jetson/install_jetson_hwdec.sh) |
| Upstream | jetson-ffmpeg, https://github.com/gjrtimmer/jetson-ffmpeg/issues; status: **draft, not filed** |

## Problem

On a Jetson Xavier NX, `h264_nvmpi` decoded 1080p at only 74 fps and spent 17 ms of CPU per frame, about 11 ms of it
kernel time. With three videos at once that left too little CPU for the app.

## Cause

`copyNvBufToFrame()` calls `NvBufSurfaceMap()` and `NvBufSurfaceSyncForCpu()` for each plane of every frame, copies
it, then `NvBufSurfaceUnMap()`. On L4T R35 each map and unmap costs kernel time; together about 11 ms per 1080p frame.

## Fix

A frame buffer's planes are mapped once and stay mapped until the buffer is destroyed:

- `copyNvBufToFrame()` maps a plane only when `mappedAddr.addr[plane]` is still NULL, and still calls
  `NvBufSurfaceSyncForCpu()` every frame;
- it no longer unmaps after the copy (NvUtils path only; the legacy `nvbuf_utils` path is unchanged);
- `nvmpi_frame_buffer::destroy()` unmaps the surface before `NvBufferDestroy()`.

Measured on the Xavier NX, 1080p H.264:

| | Stock | Mapped once |
|---|---|---|
| Decode speed | 74 fps | 203 fps |
| CPU per frame | 17 ms | 4 ms |

Together with two app-side changes (decoding ahead off the main thread, vsync on one window), an app with three videos
went from 5.4 to 55.5 FPS on the Xavier NX.

## How to check

Decode a 1080p H.264 file flat out with the stock and the patched libnvmpi and compare fps and CPU time:

    /usr/bin/time -v ffmpeg -c:v h264_nvmpi -i in.mp4 -f null -

(`install_jetson_hwdec.sh --test` and `jetson_selftest.sh` build such an ffmpeg, not installed system-wide).

## Upstream issue (draft, not filed)

**Title:** copyNvBufToFrame() maps and unmaps every plane of every frame: about 11 ms of kernel time per 1080p frame on JetPack 5

**Body:**

```markdown
## Environment

- Jetson Xavier NX Developer Kit (t194), L4T R35.6.4 (JetPack 5.1.4), Ubuntu 20.04
- jetson-ffmpeg at 8d70c17efeee57f4d956df500fec78a73f8c27d4, libnvmpi built with NvUtils (`WITH_NVUTILS`),
  `h264_nvmpi` in FFmpeg 7.1

## What happens

`h264_nvmpi` decodes 1080p H.264 at 74 fps and spends 17 ms of CPU per frame. Most of it is kernel time in
`copyNvBufToFrame()`: for each plane of every frame it calls `NvBufSurfaceMap()`, `NvBufSurfaceSyncForCpu()`, copies,
then `NvBufSurfaceUnMap()`. Mapping and unmapping cost about 11 ms per 1080p frame on L4T R35.

## Change we use

Map a frame buffer's planes once and keep them mapped until the buffer is destroyed:

- in `copyNvBufToFrame()`, call `NvBufSurfaceMap()` only when `surfaceList[0].mappedAddr.addr[plane]` is NULL; keep
  `NvBufSurfaceSyncForCpu()` per frame; drop the `NvBufSurfaceUnMap()` after the copy (NvUtils path only);
- in `nvmpi_frame_buffer::destroy()`, `NvBufSurfaceUnMap(surface, 0, -1)` before `NvBufferDestroy()`.

Result on the Xavier NX: 74 to 203 fps, CPU 17 to 4 ms per frame. Not measured on JetPack 6 (AGX Orin).

Patch (against 8d70c17, `src/` part): <link to build/gozen/nvmpi_flush.patch in MPF-Godot-Packaging>
```
