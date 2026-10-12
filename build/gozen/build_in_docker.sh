#!/bin/bash
# Called by build/gozen/build_gozen.sh inside ubuntu:20.04 (its cross gcc targets glibc 2.31, as on JetPack 5).
# $1 = arm64 | x86_64; the GoZen tree (its FFmpeg already patched by jetson-ffmpeg) is mounted at /src.
# On an arm64 host (a Jetson) the arm64 build is native: no cross toolchain.
set -euo pipefail
ARCH="$1"
NATIVE=0
[ "$ARCH" = arm64 ] && [ "$(uname -m)" = aarch64 ] && NATIVE=1
CROSS_PKGS=(gcc-aarch64-linux-gnu g++-aarch64-linux-gnu)
[ "$NATIVE" = 1 ] && CROSS_PKGS=()
export DEBIAN_FRONTEND=noninteractive
if ! command -v scons >/dev/null; then
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends gcc g++ "${CROSS_PKGS[@]}" make \
    pkg-config python3 python3-pip git nasm ca-certificates >/dev/null
  pip3 install -q scons==4.8.1
fi
cd /src/ffmpeg
[ -f ffbuild/config.mak ] && make distclean >/dev/null 2>&1 || true
rm -rf bin
CROSS=()
if [ "$ARCH" = arm64 ] && [ "$NATIVE" = 0 ]; then
  CROSS=(--enable-cross-compile --cross-prefix=aarch64-linux-gnu- --arch=aarch64 --target-os=linux)
fi
./configure --prefix="$PWD/bin" "${CROSS[@]}" --disable-shared --enable-static --enable-pic \
  --extra-cflags=-fPIC --enable-pthreads \
  --disable-everything --disable-programs --disable-doc --disable-avdevice --disable-avfilter \
  --disable-network --disable-autodetect --disable-iconv \
  --enable-avcodec --enable-avformat --enable-swscale --enable-swresample \
  --enable-protocol=file \
  --enable-demuxer=mov,matroska,ogg,mp3,aac,wav \
  --enable-decoder=h264,hevc,mpeg4,vp8,vp9,theora,aac,mp3,mp3float,opus,vorbis,flac,pcm_s16le \
  --enable-parser=h264,hevc,mpeg4video,aac,vp8,vp9,opus,vorbis,mpegaudio \
  --enable-bsf=h264_mp4toannexb,hevc_mp4toannexb \
  --enable-nvmpi --enable-decoder=h264_nvmpi,hevc_nvmpi,mpeg4_nvmpi,vp8_nvmpi,vp9_nvmpi
grep -q "CONFIG_H264_NVMPI_DECODER 1" config_components.h || { echo "nvmpi decoder not enabled"; exit 1; }
make -j"$(nproc)" >/dev/null
make install >/dev/null
cd /src
if [ "$ARCH" = arm64 ] && [ "$NATIVE" = 0 ]; then
  # godot-cpp builds with the default gcc/g++/ar: point them at the cross toolchain
  mkdir -p /tmp/cross
  for t in gcc g++ ar ranlib; do ln -sf "/usr/bin/aarch64-linux-gnu-$t" "/tmp/cross/$t"; done
  export PATH="/tmp/cross:$PATH"
fi
scons -j"$(nproc)" platform=linux arch="$ARCH" target=template_release lean=yes
