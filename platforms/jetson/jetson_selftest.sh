#!/usr/bin/env bash
# NVIDIA Jetson: checks the hardware video decoder fixes (platforms/jetson.md) on this board, with the repro programs in
# fixes/repro/. Run it after install_jetson_hwdec.sh, on a new board or a new L4T release:
#
#   bash platforms/jetson/jetson_selftest.sh                # build what is missing, run every check
#   bash platforms/jetson/jetson_selftest.sh --stock        # ... also against jetson-ffmpeg without our patch
#   bash platforms/jetson/jetson_selftest.sh --runs 20      # crash loop runs (default 100; concurrent: runs / 5)
#   bash platforms/jetson/jetson_selftest.sh --video F.mp4  # an H.264 mp4 (default: $MPF_GODOT_TEST_VIDEO)
#   bash platforms/jetson/jetson_selftest.sh --dry-run      # print the plan, change nothing
#
# Checks, each with a time limit so a hang shows as a failure instead of stopping the script:
#   flush       decode, flush, seek, three times (fix 1)        pass: "OK"
#   close       time to free a decoder (fix 2)                  pass: both closes under 300 ms
#   crash       free a decoder mid-stream, N runs (fix 3)       pass: no crash
#   concurrent  3 threads open, flush and free decoders (fix 4) pass: no hang
# The ffmpeg tree comes from install_jetson_hwdec.sh --test (built here when missing). --stock builds jetson-ffmpeg
# at the same revision without nvmpi_flush.patch in $CACHE/stock (nothing system-wide) and runs the same checks,
# which shows which bugs this L4T release has on its own. Exit status: 0 when every check of the patched build passed.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/mpf-godot"
NV_RELEASE="${MPF_GODOT_NV_RELEASE:-/etc/nv_tegra_release}"
REPRO="$ROOT/fixes/repro"
VIDEO="${MPF_GODOT_TEST_VIDEO:-}"
DRY=0 STOCK=0 RUNS=100
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY=1 ;;
        --stock) STOCK=1 ;;
        --runs) RUNS="${2:?--runs needs a number}"; shift ;;
        --video) VIDEO="${2:?--video needs a file}"; shift ;;
        -h|--help) sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
    shift
done

say() { printf '\n== %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }
run() { printf '   $ %s\n' "$*"; [ "$DRY" = 1 ] || "$@"; }

say "Board"
if [ ! -f "$NV_RELEASE" ]; then
    echo "   not an NVIDIA Jetson (no $NV_RELEASE): nothing to check"
    exit 0
fi
L4T="$(sed -n 's/^# R\([0-9]*\) (release), REVISION: \([0-9.]*\).*/\1.\2/p' "$NV_RELEASE")"
note "L4T R${L4T:-?}, $( (tr -d '\0' < /proc/device-tree/model) 2>/dev/null || echo unknown model)"
# JetPack 6 moved the Tegra libraries from tegra/ to nvidia/
if [ "${L4T%%.*}" -ge 36 ] 2>/dev/null; then TEGRA=/usr/lib/aarch64-linux-gnu/nvidia; else TEGRA=/usr/lib/aarch64-linux-gnu/tegra; fi
note "NVIDIA libraries: $TEGRA"
if [ ! -f "$VIDEO" ] && [ "$DRY" = 0 ]; then
    echo "   no video at $VIDEO: pass --video with any H.264 mp4" >&2
    exit 1
fi
note "video: $VIDEO"
# without these NVIDIA's libraries crash rather than fail (a game should check the same before using the hardware decoder)
NO_DEVICE=0
if [ ! -e /dev/nvmap ] || ! { compgen -G "/dev/nvhost-nvdec*" >/dev/null || [ -e /dev/v4l2-nvdec ]; }; then
    note "no decoder device (/dev/nvmap, /dev/nvhost-nvdec* or /dev/v4l2-nvdec): building only, nothing can decode"
    NO_DEVICE=1
fi

# build_tree NAME SRC FFDIR: the ffmpeg 7.1 tree with nvmpi in FFDIR, from the jetson-ffmpeg checkout SRC
build_tree() {
    local name="$1" src="$2" ffdir="$3" prefix="$4"
    if [ -f "$ffdir/ffmpeg7.1/ffbuild/config.mak" ] && [ -f "$ffdir/ffmpeg7.1/libavcodec/libavcodec.a" ]; then
        note "$name ffmpeg tree: $ffdir/ffmpeg7.1"
        return 0
    fi
    say "Building the $name ffmpeg tree (takes a while)"
    if [ "$name" = patched ]; then
        # its decode test failing is reported by the checks below; only a missing tree stops here
        run bash "$HERE/install_jetson_hwdec.sh" --test --no-x --keep-blanking \
            || note "install_jetson_hwdec.sh --test did not finish cleanly: checking the ffmpeg tree"
        [ "$DRY" = 1 ] || [ -f "$ffdir/ffmpeg7.1/libavcodec/libavcodec.a" ] || return 1
    else
        [ -d "$src/.git" ] || run git clone --quiet https://github.com/gjrtimmer/jetson-ffmpeg "$src" || return 1
        local rev
        rev="$(sed -n 's/^JETSON_FFMPEG_REV=\([0-9a-f]*\).*/\1/p' "$HERE/install_jetson_hwdec.sh")"
        run git -C "$src" checkout --quiet --force "$rev" || return 1
        # its own prefix and build dir: the system's (patched) libnvmpi stays as it is
        run "$src/scripts/build.sh" --no-stubs --build-dir "$src/build" --prefix "$prefix" \
            --ffmpeg 7.1 --ffmpeg-dir "$ffdir" --no-libx264 --no-libx265 || return 1
    fi
}

# build_repros FFDIR OUT: the two repro programs, linked against that tree's static FFmpeg
build_repros() {
    local ff="$1/ffmpeg7.1" out="$2" libs extra
    run mkdir -p "$out"
    libs="$ff/libavformat/libavformat.a $ff/libavcodec/libavcodec.a $ff/libswresample/libswresample.a $ff/libavutil/libavutil.a"
    extra="$( (grep -E '^EXTRALIBS[-_A-Za-z]*=' "$ff/ffbuild/config.mak" | cut -d= -f2- | tr '\n' ' ') 2>/dev/null)"
    for prog in nvmpi_seek_close nvmpi_concurrent; do
        # shellcheck disable=SC2086
        run gcc -O1 -I"$ff" "$REPRO/$prog.c" -o "$out/$prog" $libs -L"$3/lib" -L/usr/local/lib -L"$TEGRA" $extra -lpthread \
            || return 1
    done
}

# check NAME LIMIT CMD...: runs CMD with a time limit, prints PASS/FAIL, keeps the output in $LOGS
FAILED=0
check() {
    local name="$1" limit="$2"; shift 2
    if [ "$DRY" = 1 ]; then printf '   $ timeout %s %s\n' "$limit" "$*"; return 0; fi
    local log="$LOGS/$name.log" rc
    timeout -s KILL "$limit" "$@" > "$log" 2>&1; rc=$?
    case "$rc" in
        0) RESULT=pass ;;
        137) RESULT="hang (killed after ${limit}s)" ;;
        139) RESULT="crash (SIGSEGV)" ;;
        *) RESULT="exit $rc" ;;
    esac
}

# run_checks LABEL BIN LD_PATH
run_checks() {
    local label="$1" bin="$2" ldp="$3" crashes=0 hangs=0 i result
    LOGS="$CACHE/selftest/$label"; [ "$DRY" = 1 ] || mkdir -p "$LOGS"
    say "Checks, $label build (logs: $LOGS)"
    local env=(env LD_LIBRARY_PATH="$ldp${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}")

    check flush 60 "${env[@]}" "$bin/nvmpi_seek_close" "$VIDEO" flush
    if [ "$DRY" = 0 ]; then
        [ "$RESULT" = pass ] && ! grep -qx OK "$LOGS/flush.log" && RESULT="no OK"
        note "flush:      $RESULT"; [ "$RESULT" = pass ] || [ "$label" = stock ] || FAILED=1
    fi

    check close 60 "${env[@]}" "$bin/nvmpi_seek_close" "$VIDEO" close
    if [ "$DRY" = 0 ]; then
        if [ "$RESULT" = pass ]; then
            local slow
            slow="$(awk '/^close after/ && $NF == "ms" && $(NF - 1) + 0 >= 300' "$LOGS/close.log")"
            [ -z "$slow" ] || RESULT="slow: $(grep '^close after' "$LOGS/close.log" | tr '\n' ';')"
        fi
        note "close:      $RESULT $(grep '^close after' "$LOGS/close.log" 2>/dev/null | sed 's/close after //' | tr '\n' ' ')"
        [ "$RESULT" = pass ] || [ "$label" = stock ] || FAILED=1
    fi

    if [ "$DRY" = 1 ]; then
        printf '   %s runs of:\n' "$RUNS"
        check crash 60 "${env[@]}" "$bin/nvmpi_seek_close" "$VIDEO" crash
    else
        for ((i = 1; i <= RUNS; i++)); do
            check "crash-$i" 60 "${env[@]}" "$bin/nvmpi_seek_close" "$VIDEO" crash
            case "$RESULT" in pass) rm -f "$LOGS/crash-$i.log" ;; hang*) hangs=$((hangs + 1)) ;; *) crashes=$((crashes + 1)) ;; esac
        done
        result="$crashes crashed, $hangs hung, of $RUNS runs"
        note "crash:      $result"
        [ $((crashes + hangs)) = 0 ] || [ "$label" = stock ] || FAILED=1
    fi

    local cruns=$(( RUNS / 5 )); [ "$cruns" -ge 1 ] || cruns=1
    if [ "$DRY" = 1 ]; then
        printf '   %s runs of:\n' "$cruns"
        check concurrent 180 "${env[@]}" "$bin/nvmpi_concurrent" "$VIDEO" 3 40 10
    else
        hangs=0 crashes=0
        for ((i = 1; i <= cruns; i++)); do
            check "concurrent-$i" 180 "${env[@]}" "$bin/nvmpi_concurrent" "$VIDEO" 3 40 10
            case "$RESULT" in pass) rm -f "$LOGS/concurrent-$i.log" ;; hang*) hangs=$((hangs + 1)) ;; *) crashes=$((crashes + 1)) ;; esac
        done
        note "concurrent: $hangs hung, $crashes failed otherwise, of $cruns runs"
        [ $((crashes + hangs)) = 0 ] || [ "$label" = stock ] || FAILED=1
    fi
}

PATCHED_FF="$CACHE/ffmpeg-src"
build_tree patched "$CACHE/jetson-ffmpeg" "$PATCHED_FF" /usr/local || { echo "   ERROR: the patched build failed" >&2; exit 1; }
say "Repro programs (patched)"
build_repros "$PATCHED_FF" "$CACHE/selftest/bin-patched" /usr/local || { echo "   ERROR: could not build the repro programs" >&2; exit 1; }
if [ "$NO_DEVICE" = 1 ] && [ "$DRY" = 0 ]; then
    say "Result"
    note "the ffmpeg tree and the repro programs build; run this on the board with JetPack's kernel to check decoding"
    exit 0
fi
run_checks patched "$CACHE/selftest/bin-patched" /usr/local/lib

if [ "$STOCK" = 1 ]; then
    STOCK_DIR="$CACHE/stock"
    if build_tree stock "$STOCK_DIR/jetson-ffmpeg" "$STOCK_DIR/ffmpeg-src" "$STOCK_DIR/prefix" \
       && { say "Repro programs (stock)"; build_repros "$STOCK_DIR/ffmpeg-src" "$CACHE/selftest/bin-stock" "$STOCK_DIR/prefix"; }; then
        run_checks stock "$CACHE/selftest/bin-stock" "$STOCK_DIR/prefix/lib"
    else
        echo "   warning: the stock build failed, no stock results" >&2
    fi
fi

say "Result"
if [ "$DRY" = 1 ]; then
    note "dry run: nothing was built or run"
elif [ "$FAILED" = 0 ]; then
    note "every check of the patched build passed on L4T R${L4T:-?}"
else
    note "a check of the patched build FAILED on L4T R${L4T:-?}: see the logs above and platforms/jetson.md"
fi
[ "$STOCK" = 0 ] || [ "$DRY" = 1 ] || note "stock results show which bugs this L4T release has without our patch (expected to fail)"
exit "$FAILED"
