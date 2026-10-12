# GDE GoZen for the PuP on Linux and Windows (GPU decoding)

[GDE GoZen](https://github.com/VoylinsGamedevJourney/gde_gozen) is a Godot add-on that plays videos with FFmpeg.
On Linux and Windows, `scripts/setup.py` copies this folder to `game/addons/gde_gozen/` and the PuP plays the
pack's mp4s as they are (no Theora conversion). Each PuP screen uses GoZen's `VideoPlayback` node through
`game/pup/gozen_player.gd`.

This build differs from upstream GoZen in three ways (`scripts/gozen/gozen.patch`, rebuilt by
`scripts/build_gozen.sh`):

- Its FFmpeg 7.1 carries [jetson-ffmpeg](https://github.com/gjrtimmer/jetson-ffmpeg)'s `*_nvmpi` decoders, and
  GoZen asks for `<codec>_nvmpi` (`h264_nvmpi` for this pack) before the software decoder. Those decoders load
  `libnvmpi.so` when a video opens: without it (any PC that is not a Jetson), GoZen falls back to FFmpeg's
  software decoder. `GOZEN_HWDEC=0` in the environment forces software decoding.
- On Windows, FFmpeg's own decoders run on the GPU through Direct3D 11 Video, else DXVA2 (FFmpeg's hwaccels,
  LGPL, no vendor library: NVIDIA, AMD and Intel alike). Each decoded frame is copied back to memory as NV12
  and takes the same NV12 path as the Jetson's. One D3D11 device serves every video. A GPU that cannot decode a
  video (its codec, profile or size) makes FFmpeg fall back to software for that video. `GOZEN_HWDEC=0` forces
  software, `GOZEN_HWDEC=d3d11va` or `dxva2` allows only that one. The log says `GoZen: hardware decoding h264
  (d3d11va)` or `GoZen: the GPU cannot decode this h264 video, using software`. There is no decoder-side scaling
  on Windows (`set_target_size()` is the Jetson's only).
- FFmpeg is trimmed to what a PuP Pack uses (mp4/mkv/ogg; H.264, HEVC, MPEG-4, VP8, VP9, Theora; AAC, MP3,
  Vorbis, Opus, FLAC), with no libvpx, libaom or TLS.

`scripts/gozen/nvmpi_flush.patch` changes jetson-ffmpeg, for this FFmpeg and for the libnvmpi the Jetson install
builds: a flush (a seek, a loop) recreates the decoder, which JetPack 6 cannot reset in place, and libnvmpi closes a
decoder in about 50 ms instead of about 1 s, without crashing when it is closed mid-video.

`video_playback.gd` is upstream's with three changes, so that switching videos does not stall Godot's main
thread (every PuP screen and the DMD) with the Jetson's decoder: the audio stream opens on the worker thread with
the video and the main thread only takes the result once that is done; a closed video is freed on a worker thread;
`restart()` goes back to the first frame on a worker thread (looping, and `gozen_player.gd`'s `play()`).

| File | Built for |
|---|---|
| `bin/libgozen.linux.template_release.arm64.so` | Linux arm64 (Jetson, Raspberry Pi), glibc 2.31+ (JetPack 5, Ubuntu 20.04+) |
| `bin/libgozen.linux.template_release.x86_64.so` | Linux x86_64, glibc 2.31+ |
| `bin/libgozen.windows.template_release.x86_64.dll` | Windows 10/11 x86_64 (MinGW-w64 cross build, everything static: no DLL beside it) |

All are release builds; `gozen.gdextension` maps the debug entries (the Godot editor binary that `run.py`
starts) to them as well.

## Hardware decoding on the Jetson (JetPack 5 or 6)

`scripts/install/install_prereqs_linux.sh` (the README's Linux line) installs libnvmpi by itself on a Jetson.
On its own, one line on the Jetson:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Ashram56/Tron-Legacy-MPF/main/scripts/install/install_jetson_hwdec.sh)
```

It works from a minimal or stripped JetPack root image: it checks that it can get root (directly or through
sudo), that apt is there, that the clock is set (TLS fails otherwise) and that there is disk space, then installs
whatever is missing among the build tools, NVIDIA's L4T apt source (for the board's SoC and L4T release), the
Jetson Multimedia API and libraries, the Tegra loader path, the video group for your user, NVIDIA's GL/EGL/Vulkan
and X driver and an X server (`--no-x` leaves X alone). Then it builds jetson-ffmpeg's libnvmpi (at the revision
this GoZen was built with) into `/usr/local/lib`. `--dry-run` prints every check and step without changing
anything. `--test` also builds a small ffmpeg (not installed system-wide) and decodes a pack video with
`h264_nvmpi` to prove the hardware path.

**Tested platform: Jetson AGX Orin (t234), L4T R36.4.3 / JetPack 6.2** (hardware decoding of all three PuP
screens, loops and video switches). Xavier NX / AGX Xavier (t194, L4T R35, JetPack 5) is handled by the same
script but not tested on a board yet. The script handles Xavier (libraries in `tegra/`) and Orin (libraries in
`nvidia/`). NVIDIA's apt release (for example `r36.4`) carries every point release and its newest is apt's
default, so the NVIDIA packages it installs are pinned to the board's own release from `/etc/nv_tegra_release`
(R36.4.3 installs 36.4.3, not 36.4.7). Upgrading the board's BSP stays a separate `sudo apt upgrade`.

Every Jetson fix (this add-on, the FFmpeg wrapper, libnvmpi), why and how it was checked, and the checklist for
another board: [`docs/jetson/README.md`](../../docs/jetson/README.md).

When the game starts, Godot's log (`game/logs/` or the terminal) says for each video either
`GoZen: hardware decoder h264_nvmpi` or `GoZen: hardware decoder h264_nvmpi unavailable, using software`.
`sudo tegrastats` shows `NVDEC` busy while videos play.

## Licence

GDE GoZen and FFmpeg are LGPL 2.1 (`LICENSE`); FFmpeg is built without `--enable-gpl` or `--enable-nonfree`
and linked statically into `libgozen*.so` and `libgozen*.dll` (the Windows DLL also carries MinGW-w64's runtime,
under its own permissive licences and the GCC runtime exception). The sources are
the pinned revisions in `scripts/build_gozen.sh` plus `scripts/gozen/gozen.patch` and `scripts/gozen/nvmpi_flush.patch`.
