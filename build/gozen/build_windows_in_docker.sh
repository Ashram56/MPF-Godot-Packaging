#!/bin/bash
# Called by build/gozen/build_gozen.sh windows inside ubuntu:24.04: GDE GoZen for Windows x86_64, cross-built with
# MinGW-w64 (posix threads, everything linked statically: the DLL needs nothing but Windows itself).
# FFmpeg 7.1 trimmed as for Linux, plus the Direct3D 11 Video and DXVA2 hardware decoders (part of FFmpeg, LGPL,
# no vendor library; d3d11.dll, dxgi.dll, d3d9.dll and dxva2.dll are loaded at run time).
# The GoZen tree (its FFmpeg already patched by jetson-ffmpeg, whose nvmpi decoders stay off here) is at /src.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
if ! command -v scons >/dev/null; then
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends mingw-w64 make pkg-config python3 python3-pip git nasm \
    ca-certificates >/dev/null
  pip3 install -q --break-system-packages scons==4.8.1
fi
# posix thread model: godot-cpp and FFmpeg's C++-free parts both build with it (std::mutex in gozen_video.cpp)
update-alternatives --set x86_64-w64-mingw32-gcc /usr/bin/x86_64-w64-mingw32-gcc-posix >/dev/null
update-alternatives --set x86_64-w64-mingw32-g++ /usr/bin/x86_64-w64-mingw32-g++-posix >/dev/null
cd /src/ffmpeg
[ -f ffbuild/config.mak ] && make distclean >/dev/null 2>&1 || true
rm -rf bin
./configure --prefix="$PWD/bin" --arch=x86_64 --target-os=mingw32 --enable-cross-compile \
  --cross-prefix=x86_64-w64-mingw32- --pkg-config=pkg-config --pkg-config-flags=--static \
  --disable-shared --enable-static --extra-ldflags=-static \
  --disable-everything --disable-programs --disable-doc --disable-avdevice --disable-avfilter \
  --disable-network --disable-autodetect --disable-iconv --enable-w32threads \
  --enable-avcodec --enable-avformat --enable-swscale --enable-swresample \
  --enable-protocol=file \
  --enable-demuxer=mov,matroska,ogg,mp3,aac,wav \
  --enable-decoder=h264,hevc,mpeg4,vp8,vp9,theora,aac,mp3,mp3float,opus,vorbis,flac,pcm_s16le \
  --enable-parser=h264,hevc,mpeg4video,aac,vp8,vp9,opus,vorbis,mpegaudio \
  --enable-bsf=h264_mp4toannexb,hevc_mp4toannexb \
  --enable-d3d11va --enable-dxva2 \
  --enable-hwaccel=h264_d3d11va,h264_d3d11va2,h264_dxva2,hevc_d3d11va,hevc_d3d11va2,hevc_dxva2,vp9_d3d11va,vp9_d3d11va2,vp9_dxva2
for c in H264_D3D11VA2_HWACCEL HEVC_D3D11VA2_HWACCEL H264_DXVA2_HWACCEL; do
  grep -q "CONFIG_$c 1" config_components.h || { echo "$c not enabled"; exit 1; }
done
make -j"$(nproc)" >/dev/null
make install >/dev/null
grep -h "^Libs.private" bin/lib/pkgconfig/*.pc
cd /src
scons -j"$(nproc)" platform=windows arch=x86_64 target=template_release use_mingw=yes lean=yes
