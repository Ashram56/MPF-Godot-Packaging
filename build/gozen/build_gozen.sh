#!/bin/bash
# Rebuilds addons/gde_gozen/bin/ (GDE GoZen for Linux x86_64 and arm64, FFmpeg 7.1 with the Jetson's nvmpi
# decoders; Windows x86_64, FFmpeg 7.1 with Direct3D 11 Video / DXVA2 decoding) from pinned sources, in Docker.
# Not part of setup: the binaries are committed. Needs docker and git.
#
#     bash build/gozen/build_gozen.sh [arm64] [x86_64] [windows]     # default all three
#     GOZEN_NATIVE=1 bash build/gozen/build_gozen.sh arm64            # on an arm64 machine, no Docker
#
# - GDE GoZen (github.com/VoylinsGamedevJourney/gde_gozen) at GOZEN_REV, with build/gozen/gozen.patch: asks
#   FFmpeg for <codec>_nvmpi first and falls back to the software decoder (GOZEN_HWDEC=0 forces software);
#   gozen_v4l2m2m.patch then also tries FFmpeg's <codec>_v4l2m2m (Raspberry Pi 4: bcm2835-codec H.264 on /dev/video10);
#   SConstruct lean=yes (no libvpx/libaom/LibreSSL);
# - jetson-ffmpeg (github.com/gjrtimmer/jetson-ffmpeg) at JETSON_FFMPEG_REV patches GoZen's FFmpeg 7.1. Its
#   decoders load libnvmpi.so at run time, so nothing NVIDIA is needed here; on the Jetson, libnvmpi is built
#   from the same repository (platforms/jetson.md). build/gozen/nvmpi_flush.patch makes its
#   decoders recreate the hardware decoder on flush: flushing in place hangs the next decode on JetPack 6, and
#   GoZen flushes on every seek, so every looping video froze.
set -euo pipefail
GOZEN_REV=f9448619324ad7d0d4e79d3bd501bde477ea4b7f
JETSON_FFMPEG_REV=8d70c17efeee57f4d956df500fec78a73f8c27d4
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${GOZEN_WORK:-$ROOT/.cache/gozen}"
ARCHS=("$@")
[ ${#ARCHS[@]} -eq 0 ] && ARCHS=(arm64 x86_64 windows)

mkdir -p "$WORK"
if [ ! -d "$WORK/gde_gozen/.git" ]; then
  git clone https://github.com/VoylinsGamedevJourney/gde_gozen "$WORK/gde_gozen"
fi
if [ ! -d "$WORK/jetson-ffmpeg/.git" ]; then
  git clone https://github.com/gjrtimmer/jetson-ffmpeg "$WORK/jetson-ffmpeg"
fi
cd "$WORK/gde_gozen"
git checkout -q --force "$GOZEN_REV"
git submodule update --init --depth 1 ffmpeg godot_cpp
git -C ffmpeg checkout -q --force . && git -C ffmpeg clean -qfd
git apply "$ROOT/build/gozen/gozen.patch"
git apply "$ROOT/build/gozen/gozen_v4l2m2m.patch"
git apply "$ROOT/build/gozen/gozen_v4l2m2m_flush.patch"
git -C "$WORK/jetson-ffmpeg" checkout -q --force "$JETSON_FFMPEG_REV"
git -C "$WORK/jetson-ffmpeg" apply "$ROOT/build/gozen/nvmpi_flush.patch"
"$WORK/jetson-ffmpeg/scripts/ffpatch.sh" "$WORK/gde_gozen/ffmpeg"

# Docker runs as root: whatever it wrote into the work tree (also when a build fails half-way) goes back to us
trap 'docker run --rm -v "$WORK:/w" ubuntu:20.04 chown -R "$(id -u):$(id -g)" /w >/dev/null 2>&1 || true' EXIT

for arch in "${ARCHS[@]}"; do
  if [ "$arch" = windows ]; then
    # MinGW-w64 cross build (build/gozen/build_windows_in_docker.sh); ubuntu:24.04 for its newer MinGW
    docker run --rm -e PIP_CERT -v "$WORK/gde_gozen:/src" -v "$ROOT/build/gozen:/b:ro" ubuntu:24.04 \
      bash /b/build_windows_in_docker.sh
    cp "test_room/addons/gde_gozen/bin/libgozen.windows.template_release.x86_64.dll" "$ROOT/addons/gde_gozen/bin/"
    continue
  fi
  if [ "${GOZEN_NATIVE:-0}" = 1 ] && [ "$arch" = "$(uname -m | sed s/aarch64/arm64/)" ]; then
    # no Docker: build on this machine (a Raspberry Pi 4 to test quickly; the glibc is the machine's, not 2.31)
    sudo env SRC="$WORK/gde_gozen" bash "$ROOT/build/gozen/build_in_docker.sh" "$arch"
  else
    docker run --rm -e PIP_CERT -v "$WORK/gde_gozen:/src" -v "$ROOT/build/gozen:/b:ro" ubuntu:20.04 \
      bash /b/build_in_docker.sh "$arch"
  fi
  cp "test_room/addons/gde_gozen/bin/libgozen.linux.template_release.$arch.so" "$ROOT/addons/gde_gozen/bin/"
done
ls -l "$ROOT/addons/gde_gozen/bin/"
