# The GoZen build links libvpx, libaom and TLS that a player of local mp4 files never uses

| | |
|---|---|
| Id | `gde-gozen/lean-build-option` (this file: `fixes/gde-gozen/lean-build-option.md`) |
| Component | GDE GoZen |
| Kind | improvement |
| Affected versions | GDE GoZen at `f9448619324ad7d0d4e79d3bd501bde477ea4b7f` (`SConstruct`) |
| Platforms | Linux x86_64 and arm64 (glibc 2.31+), Windows x86_64 (MinGW-w64) |
| Found on | a Stern SAM recreation, 2026-10-04; Windows part 2026-10-09 |
| Fact | code (SConstruct links them unconditionally) |
| Our fix | [`../../build/gozen/gozen.patch`](../../build/gozen/gozen.patch) (SConstruct `lean=yes`); FFmpeg configured in [`../../build/gozen/build_in_docker.sh`](../../build/gozen/build_in_docker.sh) and [`../../build/gozen/build_windows_in_docker.sh`](../../build/gozen/build_windows_in_docker.sh) |
| Applied by | [`../../build/gozen/build_gozen.sh`](../../build/gozen/build_gozen.sh) (`scons ... lean=yes`) |
| Upstream | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are off on GitHub); status: **draft, not filed** |

## Problem

We needed an FFmpeg with only what plays local video files (and, on a Jetson, the nvmpi decoders), cross-built for
glibc 2.31 (JetPack 5 runs Ubuntu 20.04). GoZen's SConstruct always links `tls`, `ssl`, `crypto`, `vpx`, `aom` (and
`z` off arm64) on Linux, and `vpx`, `aom` on Windows, so an FFmpeg built without them does not link.

## Cause

SConstruct, `f9448619`: `env.Append(LIBS=["tls", "ssl", "crypto", "vpx", "aom"])` on Linux and
`env.Append(LIBS=["vpx", "aom"])` on Windows, with no option.

## Fix

`lean=yes` in SConstruct:

- Linux: none of those libraries; `-Wl,-Bsymbolic` instead (FFmpeg's assembly objects, linked statically into a
  shared library, need it).
- Windows: `ole32` and `user32` instead of libvpx and libaom (needed by the D3D11VA / DXVA2 hwaccels,
  [d3d11va-dxva2-windows.md](d3d11va-dxva2-windows.md)).

FFmpeg is then configured with `--disable-everything` and only: the file protocol; the mov, matroska, ogg, mp3, aac and
wav demuxers; the h264, hevc, mpeg4, vp8, vp9, theora, aac, mp3, opus, vorbis, flac and pcm_s16le decoders (plus the
nvmpi ones on Linux, the hwaccels on Windows); no network, no autodetect. VP8 and VP9 decode with FFmpeg's own decoders.

The default (`lean=no`) keeps upstream's behaviour.

## How to check

1. `bash build/gozen/build_gozen.sh arm64` (or `x86_64`, `windows`): it builds FFmpeg as above and runs
   `scons ... lean=yes`.
2. `ldd addons/gde_gozen/bin/libgozen.linux.template_release.x86_64.so`: no libvpx, libaom, libssl.
3. On Windows: the DLL imports only system DLLs.

## Upstream issue (draft, not filed)

**Title:** SConstruct option to build without libvpx, libaom and LibreSSL (a minimal FFmpeg)

**Body:**

```markdown
## Request

SConstruct links `tls ssl crypto vpx aom` (and `z` off arm64) on Linux, and `vpx aom` on Windows, unconditionally.
An app that only plays local files (or that builds FFmpeg with a hardware decoder for an embedded board) wants a
minimal FFmpeg: `--disable-everything` plus a few demuxers and decoders, FFmpeg's own VP8/VP9 decoders, no network.
That FFmpeg does not link with the current SConstruct.

## What we use (a patch on f9448619)

    if ARGUMENTS.get("lean", "no") == "yes":
        env.Append(LINKFLAGS=["-Wl,-Bsymbolic"])   # Linux: FFmpeg's static asm objects in a shared library
    else:
        env.Append(LIBS=["tls", "ssl", "crypto", "vpx", "aom"])
        ...

and on Windows `ole32`, `user32` in place of `vpx`, `aom` (for the D3D11VA / DXVA2 hwaccels).

Our FFmpeg configure line (Linux): `--disable-everything --disable-network --disable-autodetect`, the file protocol,
demuxers mov, matroska, ogg, mp3, aac, wav, decoders h264, hevc, mpeg4, vp8, vp9, theora, aac, mp3, opus, vorbis,
flac, pcm_s16le.

A `lean` option (or a list of extra libs to link) in SConstruct and a matching minimal configure in the FFmpeg build
script would cover it. Patch: <link to build/gozen/gozen.patch in MPF-Godot-Packaging>
```
