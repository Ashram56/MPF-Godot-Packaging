#!/bin/bash
# GDE GoZen for Linux arm64 with FFmpeg's V4L2 Request API hwaccel (Kwiboo's patch set on FFmpeg 7.1): hardware decoding of
# H.264 / HEVC / VP9 / VP8 / MPEG-2 on stateless V4L2 decoders (Radxa ROCK 4D: Rockchip rkvdec, mainline kernel). Cross-built on
# an x86_64 Ubuntu 24.04 / Debian 13 host (no Docker); linked against Debian trixie's libudev and kernel headers, so the .so loads
# on Debian 13 (glibc 2.41) and anything newer. Not for JetPack 5 (glibc 2.31): that one is build_gozen.sh.
#
#     bash build/gozen/build_rock4d.sh            # output: .cache/gozen-rock4d/libgozen.linux.template_release.arm64.so
#
# Host packages: git gcc g++ gcc-aarch64-linux-gnu g++-aarch64-linux-gnu make nasm pkg-config python3 python3-pip curl xz-utils binutils
# (scons 4.8.1 is installed with pip when missing). HTTPS access to github.com and deb.debian.org.
# Patches: gozen.patch, gozen_v4l2m2m*.patch, gozen_zerocopy.patch, gozen_v4l2_buffers_nv12.patch, gozen_vaapi.patch (as
# build_gozen.sh; the nvmpi/Jetson part is not used), then gozen_v4l2request.patch. Not checked on a ROCK 4D by the build.
set -euo pipefail
GOZEN_REV=f9448619324ad7d0d4e79d3bd501bde477ea4b7f
KWIBOO_REPO=https://github.com/Kwiboo/FFmpeg
KWIBOO_BASE=n7.1.3                                    # the tag the series is made on (FFmpeg 7.1.3)
KWIBOO_REV=fad85d9c76611c09b561167ab405c667a0dcdeb7    # head of the branch v4l2-request-n7.1.3 on 2026-11-19
DEB=https://deb.debian.org/debian
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${GOZEN_WORK:-$ROOT/.cache/gozen-rock4d}"
OUT="${GOZEN_OUT:-$WORK/out}"
mkdir -p "$WORK" "$OUT"
cd "$WORK"

if [ ! -d gde_gozen/.git ]; then git clone -q https://github.com/VoylinsGamedevJourney/gde_gozen gde_gozen; fi
cd gde_gozen
git checkout -q --force "$GOZEN_REV"
git submodule update --init --depth 1 ffmpeg godot_cpp
git -C ffmpeg checkout -q --force . && git -C ffmpeg clean -qfd
git checkout -q --force . && git clean -qfd -e ffmpeg -e godot_cpp
for p in gozen gozen_v4l2m2m gozen_v4l2m2m_flush gozen_zerocopy gozen_v4l2_buffers_nv12 gozen_vaapi gozen_v4l2request; do
    git apply "$ROOT/build/gozen/$p.patch"
done

# FFmpeg: Kwiboo's V4L2 Request API series (14 commits on the 7.1.3 tag) on top of the release/7.1 commit GoZen pins
cd ffmpeg
git remote get-url kwiboo >/dev/null 2>&1 || git remote add kwiboo "$KWIBOO_REPO"
git fetch -q --filter=blob:none kwiboo "$KWIBOO_REV" "refs/tags/$KWIBOO_BASE:refs/tags/$KWIBOO_BASE"
git -c user.name=build -c user.email=build@localhost cherry-pick $(git rev-list --reverse "$KWIBOO_BASE..$KWIBOO_REV") >/dev/null
cd ..

# arm64 sysroot pieces from Debian trixie: libudev (linked), libdrm and the kernel headers (V4L2 stateless controls)
SYS="$WORK/sysroot"
if [ ! -f "$SYS/.done" ]; then
    rm -rf "$SYS"; mkdir -p "$SYS" "$WORK/debs"
    curl -fsSL "$DEB/dists/trixie/main/binary-arm64/Packages.xz" | xz -dc > "$WORK/Packages-arm64"
    curl -fsSL "$DEB/dists/trixie-updates/main/binary-arm64/Packages.xz" | xz -dc >> "$WORK/Packages-arm64" || true
    for pkg in libudev-dev libudev1 libdrm-dev libdrm2 linux-libc-dev libcap2; do
        f="$(awk -v p="$pkg" '$0=="Package: "p {f=1} f&&/^Filename:/ {print $2; exit}' "$WORK/Packages-arm64")"
        [ -n "$f" ] || { echo "$pkg not found in trixie"; exit 1; }
        curl -fsSL -o "$WORK/debs/$pkg.deb" "$DEB/$f"
        dpkg-deb -x "$WORK/debs/$pkg.deb" "$SYS"
    done
    touch "$SYS/.done"
fi
LIBDIR="$SYS/usr/lib/aarch64-linux-gnu"
INC="-isystem $SYS/usr/include -isystem $SYS/usr/include/aarch64-linux-gnu"
export PKG_CONFIG_LIBDIR="$LIBDIR/pkgconfig:$SYS/usr/share/pkgconfig" PKG_CONFIG_SYSROOT_DIR="$SYS"
# the -dev package's libudev.so is a link into the library package, which is in the same tree: make it resolvable
[ -e "$LIBDIR/libudev.so" ] || ln -s libudev.so.1 "$LIBDIR/libudev.so"

cd ffmpeg
[ -f ffbuild/config.mak ] && make distclean >/dev/null 2>&1 || true
rm -rf bin
./configure --prefix="$PWD/bin" --enable-cross-compile --cross-prefix=aarch64-linux-gnu- --pkg-config=pkg-config --arch=aarch64 --target-os=linux \
  --disable-shared --enable-static --enable-pic --extra-cflags="-fPIC $INC" --extra-ldflags="-L$LIBDIR -Wl,-rpath-link,$LIBDIR" \
  --enable-pthreads \
  --disable-everything --disable-programs --disable-doc --disable-avdevice --disable-avfilter \
  --disable-network --disable-autodetect --disable-iconv \
  --enable-avcodec --enable-avformat --enable-swscale --enable-swresample \
  --enable-protocol=file \
  --enable-demuxer=mov,matroska,ogg,mp3,aac,wav \
  --enable-decoder=h264,hevc,mpeg4,vp8,vp9,theora,aac,mp3,mp3float,opus,vorbis,flac,pcm_s16le \
  --enable-parser=h264,hevc,mpeg4video,aac,vp8,vp9,opus,vorbis,mpegaudio \
  --enable-bsf=h264_mp4toannexb,hevc_mp4toannexb \
  --enable-v4l2-m2m --enable-decoder=h264_v4l2m2m,hevc_v4l2m2m,mpeg4_v4l2m2m,vp8_v4l2m2m,vp9_v4l2m2m \
  --enable-v4l2-request --enable-libdrm --enable-libudev \
  --enable-hwaccel=h264_v4l2request,hevc_v4l2request,vp9_v4l2request,vp8_v4l2request,mpeg2_v4l2request
for c in H264 HEVC VP9 VP8; do
    grep -q "CONFIG_${c}_V4L2REQUEST_HWACCEL 1" config_components.h || { echo "${c}_v4l2request hwaccel not enabled"; exit 1; }
done
make -j"$(nproc)" >/dev/null
make install >/dev/null
cp -L "$LIBDIR/libudev.so.1" bin/lib/libudev.so    # scons -ludev finds it through LIBPATH ffmpeg/bin/lib
cd ..

command -v scons >/dev/null || pip3 install -q scons==4.8.1 || pip3 install -q --break-system-packages scons==4.8.1
mkdir -p "$WORK/cross"
for t in gcc g++ ar ranlib; do ln -sf "/usr/bin/aarch64-linux-gnu-$t" "$WORK/cross/$t"; done
export PATH="$WORK/cross:$PATH"
scons -j"$(nproc)" platform=linux arch=arm64 target=template_release lean=yes v4l2request=yes
cp test_room/addons/gde_gozen/bin/libgozen.linux.template_release.arm64.so "$OUT/"
aarch64-linux-gnu-readelf -d "$OUT/libgozen.linux.template_release.arm64.so" | grep NEEDED
aarch64-linux-gnu-objdump -T "$OUT/libgozen.linux.template_release.arm64.so" | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -1
(cd "$OUT" && sha256sum libgozen.linux.template_release.arm64.so | tee SHA256SUMS)
