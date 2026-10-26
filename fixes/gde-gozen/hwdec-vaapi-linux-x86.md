# Videos decode on the CPU on a Linux PC: GoZen has no VAAPI (Intel Quick Sync, AMD)

| | |
|---|---|
| Id | `gde-gozen/hwdec-vaapi-linux-x86` (this file: `fixes/gde-gozen/hwdec-vaapi-linux-x86.md`) |
| Component | GDE GoZen |
| Kind | improvement |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` with FFmpeg 7.1 |
| Platforms | Linux x86_64 with an Intel (iHD, `intel-media-va-driver`) or AMD (Mesa `radeonsi`) GPU; arm64 builds are unchanged |
| Found on | Nipogi AK2PLUS (Intel N100) evaluation, 2026-10-26 |
| Fact | code (the library loads in Godot 4.6.3, takes the VAAPI path, and falls back to software when there is no device); **not yet measured on a GPU** |
| Our fix | [`../../build/gozen/gozen_vaapi.patch`](../../build/gozen/gozen_vaapi.patch) (`GoZenVideo::open()`, `_hw_device()`, `SConstruct`); FFmpeg `--enable-vaapi --enable-hwaccel=h264_vaapi,hevc_vaapi,vp9_vaapi,vp8_vaapi,mpeg4_vaapi` in [`../../build/gozen/build_in_docker.sh`](../../build/gozen/build_in_docker.sh) (x86_64 only, `libva-dev` in the container) |
| Applied by | the committed binary `addons/gde_gozen/bin/libgozen.linux.template_release.x86_64.so` (rebuilt by `build/gozen/build_gozen.sh x86_64`); `install/install_linux.sh` installs `libva2` and `libva-drm2` on x86_64, which the library is linked to |
| Upstream | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues; status: **draft, not filed** (same request as [d3d11va-dxva2-windows](d3d11va-dxva2-windows.md)) |

## Problem

On a Linux PC GoZen decodes every video in software, with the CPU cores the game and MPF also need. An Intel N100
(4 cores, no hyper-threading) decodes one 1080p H.264 stream in software at the price of a large part of a core,
while its Quick Sync engine could do several streams.

## Cause

Windows already has a GPU path (`_open_hwaccel()` with Direct3D 11 Video / DXVA2, [d3d11va-dxva2-windows](d3d11va-dxva2-windows.md)),
but it is compiled only for `_WIN32`, and the Linux FFmpeg is built with `--disable-autodetect` and no VAAPI.

## Fix

The same path on Linux with `AV_HWDEVICE_TYPE_VAAPI`: FFmpeg's own decoder with a VAAPI device (one for all videos, the first
render node, or `GOZEN_VAAPI_DEVICE=/dev/dri/renderD129`), frames copied to memory as NV12 by `_hw_download()` and shown by the
existing NV12 path. A video the GPU cannot decode (profile, 10-bit on an old GPU) falls back to software on its own.
`GOZEN_HWDEC=0` turns it off, `GOZEN_HWDEC=vaapi` asks for VAAPI only. The log says `GoZen: hardware decoding h264 (vaapi)` or
`GoZen: no vaapi device on this PC`. The Jetson and Pi decoders (`_nvmpi`, `_v4l2m2m`) are tried first, as before.

Not done: zero-copy (VAAPI surface to DRM PRIME to an EGL/Vulkan texture, as [v4l2m2m-zero-copy](v4l2m2m-zero-copy.md) does for the
Pi 4). The copy of a 1080p NV12 frame out of a VAAPI surface costs a few milliseconds on an iGPU: to measure.

The game must not force `GOZEN_HWDEC=0`: Tron's `game/pup/gozen_player.gd` does that on a Linux PC without `/dev/nvmap` unless `GOZEN_HWDEC`
is already set, so the x86 image sets `GOZEN_HWDEC=1` for the services.

## How to check

1. `vainfo` lists `VAProfileH264High : VAEntrypointVLD` (and HEVC); `ffmpeg -hwaccel vaapi -i video.mp4 -f null -` works.
2. `GOZEN_HWDEC=1 godot ...`: the log says `GoZen: hardware decoding h264 (vaapi)` for each video; `intel_gpu_top` shows the Video engine busy.
3. `GOZEN_HWDEC=0`: software decoding. Compare the CPU in `top`.
4. `python scripts/pup/video_check.py` of the game (Tron-Legacy-MPF) prints GPU or software per video and the speed.

## Upstream issue (draft, not filed)

**Title:** Linux: VAAPI hardware decoding (Intel Quick Sync, AMD) like the Windows D3D11VA path

**Body:**

```markdown
GoZen decodes in software on Linux. FFmpeg's VAAPI hwaccel (--enable-vaapi) with av_hwdevice_ctx_create(AV_HWDEVICE_TYPE_VAAPI),
a get_format callback that picks AV_PIX_FMT_VAAPI and av_hwframe_transfer_data() to NV12 gives GPU decoding on Intel and AMD
with the code used for D3D11VA. Needs libva and libva-drm at run time. Patch attached.
```
