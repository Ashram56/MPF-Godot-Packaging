#!/usr/bin/env bash
# NVIDIA Jetson (JetPack 5 or 6): installs libnvmpi, which GDE GoZen's FFmpeg loads to decode videos on
# the hardware decoder (addons/gde_gozen/README.md), and everything it and Godot need on the Jetson, so it
# also works from a minimal or stripped root image. Safe to re-run. install_prereqs_linux.sh runs it by itself on
# a Jetson (MPF_GODOT_HWDEC=0 or --no-jetson skips it); on its own:
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/platforms/jetson/install_jetson_hwdec.sh)
#
#   ... --test      also build a small ffmpeg (no system install) and decode a pack video with h264_nvmpi
#   ... --no-x      leave the X server alone (Godot's GPU driver is still checked)
#   ... --keep-blanking  leave GNOME's screen blanking, dimming and lock as they are (turned off by default)
#   ... --dry-run   print the checks and the plan, change nothing
#
# Steps: checks (root or sudo, apt, clock, disk), the build tools (Ubuntu apt), NVIDIA's L4T apt source if the
# image lost it, the Multimedia API and libraries, the decoder device and the video group, the NVIDIA
# GL/Vulkan/X driver and an X server for Godot, the loader path for NVIDIA's libraries, then jetson-ffmpeg at the revision GoZen was built with
# (build/gozen/build_gozen.sh) in ~/.cache/mpf-godot/, its libnvmpi built and installed in /usr/local/lib.
set -euo pipefail

JETSON_FFMPEG_URL=https://github.com/gjrtimmer/jetson-ffmpeg
JETSON_FFMPEG_REV=8d70c17efeee57f4d956df500fec78a73f8c27d4      # same as build/gozen/build_gozen.sh
NV_REPO=https://repo.download.nvidia.com/jetson
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/mpf-godot"
SRC="$CACHE/jetson-ffmpeg"
TEST_VIDEO="${MPF_GODOT_TEST_VIDEO:-}"      # an H.264 mp4 for --test
MMAPI=/usr/src/jetson_multimedia_api
# overridable for the tests (tests/test_installers.py)
NV_RELEASE="${MPF_GODOT_NV_RELEASE:-/etc/nv_tegra_release}"
DT="${MPF_GODOT_DEVICE_TREE:-/proc/device-tree}"
ARCH="${MPF_GODOT_ARCH:-$(uname -m)}"

DRY=0 TEST=0 X=1 BLANK=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY=1 ;;
        --test) TEST=1 ;;
        --no-x) X=0 ;;
        --keep-blanking) BLANK=1 ;;
        -h|--help) sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
    esac
done

say() { printf '\n== %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }
run() { printf '   $ %s\n' "$*"; [ "$DRY" = 1 ] || "$@"; }
SUDO=""; [ "$(id -u)" = 0 ] || SUDO=sudo
root() { run $SUDO "$@"; }
# root_write FILE TEXT
root_write() {
    printf '   $ write %s: %s\n' "$1" "$2"
    [ "$DRY" = 1 ] || printf '%s\n' "$2" | $SUDO tee "$1" >/dev/null
}
# a failed check stops the install; a dry run reports it and goes on
fail() {
    echo "   ERROR: $*" >&2
    [ "$DRY" = 1 ] || exit 1
}
APT_UPDATED=0
# reinstalls too: on a stripped image a package can be "installed" with its files gone; a config file already on
# the system (/etc/nv_tegra_release, X config) is kept rather than asked about, which would stop a piped install
apt_install() {
    [ $# -gt 0 ] || return 0
    if [ "$APT_UPDATED" = 0 ]; then root apt-get update; APT_UPDATED=1; fi
    root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends --reinstall \
        -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold ${L4T_PIN:+-o "Dir::Etc::Preferences=$L4T_PIN"} "$@"
}
# NVIDIA's apt release (r36.4) carries every point release (36.4.0 ... 36.4.7) and its newest is the candidate,
# so a plain install would put newer NVIDIA libraries next to the installed BSP (kernel, firmware, nvidia-l4t-core).
# l4t_pin pins nvidia-l4t-* to the release in /etc/nv_tegra_release for this script's installs only; upgrading the
# BSP stays NVIDIA's apt upgrade.
L4T_PIN=""
l4t_pin() {
    [ -n "${L4T_FULL:-}" ] || return 0
    L4T_PIN="$CACHE/l4t-pin.pref"
    printf '   $ write %s: nvidia-l4t-* %s-*\n' "$L4T_PIN" "$L4T_FULL"
    [ "$DRY" = 1 ] && return 0
    mkdir -p "$CACHE"
    printf 'Package: nvidia-l4t-*\nPin: version %s-*\nPin-Priority: 1001\n' "$L4T_FULL" > "$L4T_PIN"
}
# need WHAT PACKAGE: WHAT is a command, or an absolute path that must exist; adds PACKAGE to $MISSING if not
MISSING=()
need() {
    local ok=0
    case "$1" in
        /*) compgen -G "$1" >/dev/null && ok=1 ;;
        *) command -v "$1" >/dev/null 2>&1 && ok=1 ;;
    esac
    if [ "$ok" = 0 ]; then
        note "missing: $1"
        case " ${MISSING[*]-} " in *" $2 "*) ;; *) MISSING+=("$2") ;; esac
    fi
}
install_missing() {   # install_missing LABEL
    if [ ${#MISSING[@]} -eq 0 ]; then note "$1: in place"; else apt_install "${MISSING[@]}"; fi
    MISSING=()
}

# ------------------------------------------------------------------ is this a Jetson with JetPack 5+?

if [ "${MPF_GODOT_HWDEC:-1}" = 0 ]; then
    echo "MPF_GODOT_HWDEC=0: skipping the Jetson hardware decoder (GoZen decodes in software)"
    exit 0
fi

say "Jetson"
if [ "$ARCH" != aarch64 ] || [ ! -f "$NV_RELEASE" ]; then
    echo "   not an NVIDIA Jetson (no /etc/nv_tegra_release): nothing to do, GoZen decodes in software here"
    exit 0
fi
L4T="$(sed -n 's/^# R\([0-9]*\) (release), REVISION: \([0-9.]*\).*/\1.\2/p' "$NV_RELEASE")"
L4T_MAJOR="${L4T%%.*}"
note "L4T R${L4T:-?} ($( (tr -d '\0' < "$DT/model") 2>/dev/null || echo unknown model))"
case "$L4T_MAJOR" in
    35|36|3[7-9]) ;;
    *) echo "   L4T R${L4T:-?} is JetPack 4 or older: Godot 4.6 needs JetPack 5 or newer (glibc 2.28+)" >&2; exit 1 ;;
esac
# NVIDIA's apt repos are per SoC and per L4T release (R35.4.1 -> r35.4)
COMPAT="$( (tr '\0' ' ' < "$DT/compatible") 2>/dev/null || true)"
case "$COMPAT" in
    *tegra194*) SOC=t194 ;;   # Xavier NX / AGX Xavier
    *tegra234*) SOC=t234 ;;   # Orin
    *) SOC="" ;;
esac
L4T_REL="r${L4T_MAJOR}.$(echo "${L4T#*.}" | cut -d. -f1)"
note "SoC ${SOC:-unknown}, NVIDIA apt release $L4T_REL"
# JetPack 6 moved the Tegra libraries from tegra/ to nvidia/
if [ "$L4T_MAJOR" -ge 36 ]; then TEGRA=/usr/lib/aarch64-linux-gnu/nvidia; else TEGRA=/usr/lib/aarch64-linux-gnu/tegra; fi
EGL_DIR=/usr/lib/aarch64-linux-gnu/tegra-egl   # both releases
case "$L4T" in *.*.*) L4T_FULL="$L4T"; l4t_pin ;; esac

# ------------------------------------------------------------------ checks

say "Checks"
if [ -n "$SUDO" ] && ! command -v sudo >/dev/null 2>&1; then
    fail "not root and no sudo: run this as root (su -), or install sudo first"
fi
command -v apt-get >/dev/null 2>&1 && command -v dpkg >/dev/null 2>&1 \
    || fail "apt-get/dpkg not found: this needs JetPack's Ubuntu (apt) root file system"
# no RTC battery and no network time: TLS (apt, git, curl) refuses certificates "not yet valid"
if [ "$(date +%Y)" -lt 2025 ]; then
    fail "the clock says $(date): set it first (sudo date -s '2026-01-01 12:00', or enable systemd-timesyncd)"
fi
NEED_MB=1500; [ "$TEST" = 1 ] && NEED_MB=4000
FREE_MB="$(df -Pm "$HOME" 2>/dev/null | awk 'NR == 2 { print $4 }' || true)"
if [ -n "$FREE_MB" ] && [ "$FREE_MB" -lt "$NEED_MB" ]; then
    note "warning: ${FREE_MB} MB free in $HOME, the build wants about ${NEED_MB} MB"
else
    note "${FREE_MB:-?} MB free in $HOME"
fi
note "root: $([ -z "$SUDO" ] && echo yes || echo "through sudo")"

# ------------------------------------------------------------------ build tools (Ubuntu)

say "Build tools"
need /etc/ssl/certs/ca-certificates.crt ca-certificates
need curl curl
need git git
need cmake cmake
need make make
need gcc gcc
need g++ g++
need /usr/include/stdio.h libc6-dev
need pkg-config pkg-config
need awk mawk
need /usr/lib/aarch64-linux-gnu/libjpeg.so.8 libjpeg-turbo8    # libnvmpi's JPEG code links it
install_missing "build tools"

# ------------------------------------------------------------------ NVIDIA's apt source

say "NVIDIA L4T apt source ($NV_REPO)"
if grep -rqs 'repo.download.nvidia.com/jetson' /etc/apt/sources.list /etc/apt/sources.list.d/; then
    note "in place"
elif [ -z "$SOC" ]; then
    fail "no NVIDIA apt source and unknown SoC ($DT/compatible: ${COMPAT:-unreadable}); add JetPack's" \
         "/etc/apt/sources.list.d/nvidia-l4t-apt-source.list by hand"
else
    root curl -fsSL -o /etc/apt/trusted.gpg.d/jetson-ota-public.asc "$NV_REPO/jetson-ota-public.asc" \
        || fail "could not download NVIDIA's apt key from $NV_REPO: check the network"
    root_write /etc/apt/sources.list.d/nvidia-l4t-apt-source.list \
        "deb $NV_REPO/common $L4T_REL main"$'\n'"deb $NV_REPO/$SOC $L4T_REL main"
    APT_UPDATED=0
fi

# ------------------------------------------------------------------ Multimedia API and libraries

say "Jetson Multimedia API and libraries"
need "$MMAPI/include/NvVideoDecoder.h" nvidia-l4t-jetson-multimedia-api
need "$MMAPI/samples/common/classes/NvVideoDecoder.cpp" nvidia-l4t-jetson-multimedia-api
need "$TEGRA/libnvv4l2.so" nvidia-l4t-multimedia
need "$TEGRA/libnvjpeg.so" nvidia-l4t-multimedia
need "$TEGRA/libnvbufsurface.so*" nvidia-l4t-multimedia-utils
need "$TEGRA/libnvbufsurftransform.so*" nvidia-l4t-multimedia-utils
install_missing "Multimedia API and libraries"
if [ "$DRY" = 0 ]; then
    [ -f "$MMAPI/include/NvVideoDecoder.h" ] || fail "$MMAPI is still missing after apt"
    [ -f "$TEGRA/libnvv4l2.so" ] || fail "$TEGRA/libnvv4l2.so is still missing after apt"
fi

# ------------------------------------------------------------------ decoder device and permissions

say "Decoder device"
if compgen -G "/dev/nvhost-nvdec*" >/dev/null || [ -e /dev/v4l2-nvdec ]; then
    note "$(ls -d /dev/nvhost-nvdec* /dev/v4l2-nvdec 2>/dev/null | tr '\n' ' ')"
else
    note "warning: no /dev/nvhost-nvdec* or /dev/v4l2-nvdec: the hardware decoder needs JetPack's kernel and"
    note "device tree (check 'lsmod | grep nvhost' / dmesg); GoZen falls back to software decoding until then"
fi
USER_NAME="${SUDO_USER:-$(id -un)}"
if [ "$USER_NAME" != root ] && getent group video >/dev/null; then
    if id -nG "$USER_NAME" | tr ' ' '\n' | grep -qx video; then
        note "$USER_NAME is in the video group"
    else
        root usermod -aG video "$USER_NAME"
        note "$USER_NAME added to the video group: log out and back in before starting the game"
    fi
fi

# ------------------------------------------------------------------ Godot's GPU driver and X server

say "Godot's GPU driver (NVIDIA GL, EGL, Vulkan)$([ "$X" = 1 ] && echo ' and X server')"
need "$TEGRA/libGLX_nvidia.so.0" nvidia-l4t-3d-core
need "$EGL_DIR/libEGL_nvidia.so.0" nvidia-l4t-3d-core
need "/etc/vulkan/icd.d/nvidia_icd.json" nvidia-l4t-3d-core
need "/usr/lib/aarch64-linux-gnu/libGLX.so.0" libglx0
need "/usr/lib/aarch64-linux-gnu/libEGL.so.1" libegl1
need "/usr/lib/aarch64-linux-gnu/libvulkan.so.1" libvulkan1
if [ "$X" = 1 ]; then
    # Godot places one window per monitor only on X11 (platforms/jetson.md)
    need "/usr/lib/xorg/modules/drivers/nvidia_drv.so" nvidia-l4t-x11
    need Xorg xserver-xorg-core
    need "/usr/lib/xorg/modules/input/libinput_drv.so" xserver-xorg-input-libinput
    need xinit xinit
    need xrandr x11-xserver-utils
fi
install_missing "GPU driver$([ "$X" = 1 ] && echo ' and X server')"

# ------------------------------------------------------------------ screen blanking (GNOME)

# A cabinet has no keyboard or mouse in use while people play, so GNOME blanked and locked the screens mid-game
# on the Orin. Turned off for the cabinet user (their dconf settings, so a GNOME session started later keeps it):
# the values checked on the board, plus no suspend on idle. Without GNOME (no gsettings schema) nothing to do.
if [ "$X" = 1 ] && [ "$BLANK" = 0 ]; then
    say "Screen blanking, dimming and lock (GNOME, user $USER_NAME)"
    if ! command -v gsettings >/dev/null 2>&1 || ! gsettings list-schemas 2>/dev/null | grep -x org.gnome.desktop.session >/dev/null; then
        note "no GNOME settings here: nothing to change"
    else
        GS=(gsettings)
        if [ "$USER_NAME" != "$(id -un)" ]; then
            GS=(sudo -u "$USER_NAME" env HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)" dbus-run-session -- gsettings)
        elif [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && command -v dbus-run-session >/dev/null 2>&1; then
            GS=(dbus-run-session -- gsettings)   # over SSH: no session bus, dconf is written all the same
        fi
        for kv in "org.gnome.desktop.session idle-delay 0" \
                  "org.gnome.desktop.screensaver lock-enabled false" \
                  "org.gnome.desktop.screensaver idle-activation-enabled false" \
                  "org.gnome.settings-daemon.plugins.power idle-dim false" \
                  "org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type nothing"; do
            read -r schema key value <<< "$kv"
            run "${GS[@]}" set "$schema" "$key" "$value" || note "warning: could not set $schema $key"
        done
        note "--keep-blanking leaves these alone; for a cabinet also turn on automatic login (platforms/jetson.md)"
    fi
fi

# ------------------------------------------------------------------ sound output (ALSA default -> HDMI)

# The Xavier NX devkit image makes the APE card (I2S on the 40-pin header, nothing attached) ALSA's default in
# /etc/asound.conf: Godot found no sound device and the game was silent. Without PulseAudio or PipeWire (a minimal
# image), the cabinet user's ~/.asoundrc sends the default to the HDMI monitor instead; an existing one is kept.
ASOUND_CONF="${MPF_GODOT_ASOUND_CONF:-/etc/asound.conf}"
PROC_ASOUND="${MPF_GODOT_PROC_ASOUND:-/proc/asound}"
if [ "$X" = 1 ] && grep -qs 'hw:APE' "$ASOUND_CONF" && [ -d "$PROC_ASOUND/HDA" ]; then
    say "Sound output (the ALSA default is the APE card; user $USER_NAME)"
    ASOUNDRC="${MPF_GODOT_ASOUNDRC:-$(getent passwd "$USER_NAME" | cut -d: -f6)/.asoundrc}"
    if command -v pulseaudio >/dev/null 2>&1 || command -v pipewire >/dev/null 2>&1; then
        note "PulseAudio or PipeWire is installed: sound goes through it, nothing to change"
    elif [ -e "$ASOUNDRC" ]; then
        note "$ASOUNDRC exists: kept as it is"
    else
        # the HDMI card's playback devices and their ELD files (one per output) come in the same order: take the
        # device of the output with a monitor connected, else the first
        devs=($(ls "$PROC_ASOUND/HDA/" | sed -n 's/^pcm\([0-9]*\)p$/\1/p' | sort -n))
        elds=($(ls "$PROC_ASOUND/HDA/" | sed -n 's/^eld#\([0-9]*\)\.0$/\1/p' | sort -n))
        dev="${devs[0]:-3}"
        for i in "${!elds[@]}"; do
            if grep -qs 'monitor_present[[:space:]]*1' "$PROC_ASOUND/HDA/eld#${elds[$i]}.0"; then
                dev="${devs[$i]:-$dev}"
                break
            fi
        done
        printf '   $ write %s: default -> hw:HDA,%s (dmix)\n' "$ASOUNDRC" "$dev"
        if [ "$DRY" = 0 ]; then
            asoundrc="# Written by install_jetson_hwdec.sh: ALSA's default to the HDMI monitor (hw:HDA,$dev), mixed with dmix.
# /etc/asound.conf points it at the APE card, which has nothing attached on the devkit.
pcm.!default {
	type plug
	slave.pcm \"hdmi_dmix\"
}
pcm.hdmi_dmix {
	type dmix
	ipc_key 4242
	slave {
		pcm \"hw:HDA,$dev\"
		rate 48000
		channels 2
	}
}
ctl.!default {
	type hw
	card HDA
}"
            if [ "$USER_NAME" = "$(id -un)" ]; then
                printf '%s\n' "$asoundrc" > "$ASOUNDRC"
            else
                printf '%s\n' "$asoundrc" | sudo -u "$USER_NAME" tee "$ASOUNDRC" >/dev/null
            fi
        fi
    fi
fi

say "Loader path"
# nvidia-l4t-core and -3d-core ship these directories but not always the loader config for them (tegra-egl's
# link is made when the image is built, not by the package); look for a library from each in the cache, by
# directory, since libnvv4l2.so is cached under its soname libv4l2.so.0
loader_dir() {   # loader_dir DIR CONF
    [ -d "$1" ] || [ "$DRY" = 1 ] || return 0
    if ld_cache | grep -F "=> $1/" >/dev/null; then
        note "$1 is in the loader cache"
    else
        note "$1 is not in the loader cache"
        root_write "$2" "$1"
        LDCONFIG=1
    fi
}
# the loader cache, read whole: with pipefail, "ldconfig -p | grep -q" fails when grep stops early on a match and
# ldconfig, with more output left than a pipe holds (a full JetPack image), dies of SIGPIPE
ld_cache() {
    local out
    out="$( (command -v ldconfig >/dev/null 2>&1 && ldconfig -p || /sbin/ldconfig -p) 2>/dev/null || true)"
    printf '%s\n' "$out"
}
LDCONFIG=0
loader_dir "$TEGRA" /etc/ld.so.conf.d/nvidia-tegra.conf
loader_dir "$EGL_DIR" /etc/ld.so.conf.d/aarch64-linux-gnu_EGL.conf
[ "$LDCONFIG" = 0 ] || root ldconfig

# ------------------------------------------------------------------ libnvmpi

say "libnvmpi (jetson-ffmpeg ${JETSON_FFMPEG_REV:0:7})"
if [ -d "$SRC/.git" ]; then
    run git -C "$SRC" fetch --quiet origin
else
    run mkdir -p "$CACHE"
    run git clone --quiet "$JETSON_FFMPEG_URL" "$SRC"
fi
run git -C "$SRC" checkout --quiet --force "$JETSON_FFMPEG_REV"
# build/gozen/nvmpi_flush.patch, as in GoZen's build: libnvmpi closes a decoder in ~50 ms instead of ~1 s and
# without crashing mid-stream, and the FFmpeg wrapper (the --test ffmpeg below) recreates the decoder on a flush.
# In this clone, else from GitHub ($MPF_GODOT_BRANCH).
NVMPI_PATCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/../../build/gozen/nvmpi_flush.patch"
if [ ! -f "$NVMPI_PATCH" ]; then
    NVMPI_PATCH="$CACHE/nvmpi_flush.patch"
    run curl -fsSL -o "$NVMPI_PATCH" \
        "https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/${MPF_GODOT_BRANCH:-main}/build/gozen/nvmpi_flush.patch"
fi
run git -C "$SRC" apply "$NVMPI_PATCH"
# --no-stubs: fail rather than build the non-working stub library when the Multimedia API is missing
run "$SRC/scripts/build.sh" --no-stubs --install
if [ "$DRY" = 0 ]; then
    NVMPI="$(ld_cache | grep 'libnvmpi\.so ' | sed 's/.*=> //' || true)"
    if [ -n "$NVMPI" ]; then
        note "installed: $NVMPI"
    else
        fail "libnvmpi.so is not in the loader cache (ldconfig -p): GoZen would decode in software"
    fi
fi

# ------------------------------------------------------------------ optional decode test

if [ "$TEST" = 1 ]; then
    FFMPEG="$CACHE/ffmpeg-src/ffmpeg7.1/ffmpeg"
    say "Decode test: an ffmpeg with nvmpi at $FFMPEG (not installed system-wide; takes a while)"
    run "$SRC/scripts/build.sh" --no-stubs --ffmpeg 7.1 --ffmpeg-dir "$CACHE/ffmpeg-src" --no-libx264 --no-libx265
    if [ -n "$TEST_VIDEO" ] && [ -f "$TEST_VIDEO" ]; then
        run "$FFMPEG" -hide_banner -benchmark -c:v h264_nvmpi -i "$TEST_VIDEO" -f null -
        note "a 'speed=' well above 1x and no error above: the hardware decoder works"
    else
        note "no test video (set MPF_GODOT_TEST_VIDEO to an H.264 mp4); try:"
        note "$FFMPEG -benchmark -c:v h264_nvmpi -i <some H.264 .mp4> -f null -"
    fi
fi

say "Done$([ "$DRY" = 1 ] && echo ' (dry run: nothing was changed)')"
note "Start the game (python -m mpf_godot run GAME) from an X session (startx, or a display manager): Godot's log"
note "says 'GoZen: hardware decoder h264_nvmpi' per video, and 'sudo tegrastats' shows NVDEC busy while they play."
