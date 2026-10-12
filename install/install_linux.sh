#!/usr/bin/env bash
# Installs MPF, MPF Monitor, Godot and GMC with our fixes on Linux, and every system package they need.
# Debian/Ubuntu (apt), Fedora/RHEL (dnf) and Arch (pacman); x86_64 or arm64 (a Jetson too). Safe to re-run.
#
#   install/install_linux.sh                 # prerequisites, then python -m mpf_godot setup
#   install/install_linux.sh --no-monitor    # ... without MPF Monitor (installed by default, with its Qt libraries)
#   install/install_linux.sh --proc          # ... plus libpinproc/pypinproc (built) and the P-ROC udev rule
#   install/install_linux.sh --dry-run       # print the plan, change nothing
#   install/install_linux.sh -- --extra pillow   # arguments after -- go to python -m mpf_godot setup
#
# Options: --yes (no questions), --xvfb (Xvfb for running without a screen; automatic when there is no
# DISPLAY), --no-setup (prerequisites only), --no-jetson (no Jetson hardware video decoder on a Jetson),
# --python-any (accept any Python 3.10-3.14 already installed instead of 3.11). Python 3.11 comes from the
# distribution, the deadsnakes PPA on Ubuntu, or else a standalone build fetched with uv. platforms/linux.md.
set -euo pipefail

# Run from a clone, it sets up that clone. Run on its own (fetched with curl, README "Install"), it first
# clones the repository into $MPF_GODOT_DIR (default ~/MPF-Godot), branch $MPF_GODOT_BRANCH (default main),
# from $MPF_GODOT_REPO; an existing clone there gets a git pull.
SRC="${BASH_SOURCE[0]:-}"
if [ -n "$SRC" ] && [ -f "$(dirname "$SRC")/../mpf_godot/setup_toolchain.py" ]; then
    ROOT="$(cd "$(dirname "$SRC")/.." && pwd)" CLONE=0
else
    ROOT="${MPF_GODOT_DIR:-$HOME/MPF-Godot}" CLONE=1
fi
REPO_URL="${MPF_GODOT_REPO:-https://github.com/Ashram56/MPF-Godot-Packaging.git}"
REPO_BRANCH="${MPF_GODOT_BRANCH:-main}"
HERE="$ROOT/install"
OS_RELEASE="${MPF_GODOT_OS_RELEASE:-/etc/os-release}"     # tests point this at a fake one
UV_VERSION="${UV_VERSION:-0.12.22}"
UDEV_RULE=/etc/udev/rules.d/99-pinproc.rules

DRY=0 YES=0 MONITOR=1 PROC=0 XVFB=0 SETUP=1 PY_ANY=0 JETSON=1
SETUP_ARGS=()

usage() { sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY=1 ;;
        -y|--yes) YES=1 ;;
        --monitor) MONITOR=1 ;;
        --no-monitor) MONITOR=0 ;;
        --proc) PROC=1 ;;
        --xvfb) XVFB=1 ;;
        --no-setup) SETUP=0 ;;
        --python-any) PY_ANY=1 ;;
        --no-jetson) JETSON=0 ;;
        -h|--help) usage; exit 0 ;;
        --) shift; SETUP_ARGS=("$@"); break ;;
        *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
    shift
done

say() { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
run() {
    printf '    $ %s\n' "$*"
    if [ "$DRY" = 0 ]; then "$@"; fi
}

# ------------------------------------------------------------------ GitHub access (a private fork)
# This repository is public. A private fork of it ($MPF_GODOT_REPO) needs a GitHub token instead of a password:
# MPF_GODOT_GITHUB_TOKEN (or GITHUB_TOKEN / GH_TOKEN), or pasted when asked. It is used for this run only (git's
# url.insteadOf in the environment) and handed to git's credential helper, if one is set up, so later pulls work.
# platforms/linux.md "A private repository and its token" has why each step is there.
TOKEN="${MPF_GODOT_GITHUB_TOKEN:-${GITHUB_TOKEN:-${GH_TOKEN:-}}}"

public_repo() { GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=true git -c credential.helper= ls-remote "$1" HEAD >/dev/null 2>&1; }

github_auth() {
    AUTH_DONE=1
    [ "$CLONE" = 1 ] || return 0
    say "GitHub access"
    if [ "$DRY" = 1 ]; then
        note "(dry run) a private repository asks for a GitHub token here$([ -n "$TOKEN" ] && echo ': using the one given')"
        return
    fi
    # only a repository nobody can read without a login gets the token: a token that cannot read a public
    # repository (a fine-grained one for other repositories, an expired one) would make git fail on it
    if public_repo "$REPO_URL"; then
        note "$REPO_URL is public: no token needed"
        return
    fi
    if [ -z "$TOKEN" ]; then
        if GIT_TERMINAL_PROMPT=0 git ls-remote "$REPO_URL" HEAD >/dev/null 2>&1; then
            note "a private repository, readable with the GitHub credentials git already has"
            return
        fi
        [ "$YES" = 0 ] && [ -r /dev/tty ] || die "$REPO_URL is private: set MPF_GODOT_GITHUB_TOKEN to a GitHub token that can read it"
        note "Private: $REPO_URL"
        note "Paste a GitHub token that can read it (github.com > Settings > Developer settings > Personal access"
        note "tokens; a fine-grained token with Contents: read-only on this repository)."
        printf '    token (not shown): ' >/dev/tty
        IFS= read -rs TOKEN </dev/tty
        printf '\n' >/dev/tty
    fi
    # a token copied from a text editor can carry spaces or a line break; GitHub tokens have none
    TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
    [ -n "$TOKEN" ] || die "no token given"
    local prefix=unknown
    case "$TOKEN" in github_pat_*) prefix=github_pat_ ;; gh?_*) prefix="${TOKEN:0:4}" ;; esac
    note "token: ${#TOKEN} characters, type $prefix (a fine-grained token is about 93, a classic one 40)"
    export GIT_CONFIG_COUNT=1 "GIT_CONFIG_KEY_0=url.https://x-access-token:${TOKEN}@${REPO_URL#https://}.insteadOf" \
        "GIT_CONFIG_VALUE_0=$REPO_URL"
    GIT_TERMINAL_PROMPT=0 git ls-remote "$REPO_URL" HEAD >/dev/null 2>&1 \
        || die "the GitHub token cannot read $REPO_URL (check its repository access and expiry)"
    printf 'protocol=https\nhost=github.com\nusername=x-access-token\npassword=%s\n\n' "$TOKEN" \
        | git credential approve 2>/dev/null || true
    note "token accepted"
}

# first thing, so a token is asked before the long installs (later, once git is installed, if it is missing)
AUTH_DONE=0
if command -v git >/dev/null 2>&1; then github_auth; fi


if [ "$(id -u)" = 0 ]; then
    SUDO=()
else
    SUDO=(sudo)
    if [ "$DRY" = 0 ] && ! command -v sudo >/dev/null; then
        die "sudo is missing: run this as root, or install sudo"
    fi
fi
root() { run ${SUDO[@]+"${SUDO[@]}"} "$@"; }

# ------------------------------------------------------------------ distribution

[ "$(uname -s)" = Linux ] || [ "$DRY" = 1 ] || die "this script is for Linux (macOS: install_prereqs_macos.sh)"
[ -r "$OS_RELEASE" ] || die "cannot read $OS_RELEASE: unknown distribution"
# shellcheck disable=SC1090
DISTRO_ID="$(. "$OS_RELEASE"; echo "${ID:-}")"
# shellcheck disable=SC1090
DISTRO_LIKE="$(. "$OS_RELEASE"; echo "${ID_LIKE:-}")"
# shellcheck disable=SC1090
DISTRO_NAME="$(. "$OS_RELEASE"; echo "${PRETTY_NAME:-$DISTRO_ID}")"

case " $DISTRO_ID $DISTRO_LIKE " in
    *" debian "*|*" ubuntu "*) FAMILY=apt ;;
    *" fedora "*|*" rhel "*|*" centos "*) FAMILY=dnf ;;
    *" arch "*) FAMILY=pacman ;;
    *) die "unsupported distribution '$DISTRO_ID': install the packages in platforms/linux.md by hand, then run python3 -m mpf_godot setup" ;;
esac

case "$(uname -m)" in
    x86_64|amd64) ARCH=x86_64 ;;
    aarch64|arm64) ARCH=aarch64 ;;
    *) if [ "$DRY" = 1 ]; then ARCH=x86_64; else die "unsupported CPU $(uname -m): x86_64 or arm64 only"; fi ;;
esac

# MPF Monitor needs PyQt6. Its arm64 wheels need glibc 2.39 from 6.8 on, so mpf_godot/toolchain.py takes 6.7 on
# Linux arm64, whose wheels need glibc 2.28 (JetPack 5: 2.31, JetPack 6: 2.35). Older than that, pip falls back
# to a source build that fails, so the monitor is left out
GLIBC="$(getconf GNU_LIBC_VERSION 2>/dev/null | awk '{ print $2 }' || true)"
if [ "$MONITOR" = 1 ] && [ "$ARCH" = aarch64 ] && [ -n "$GLIBC" ] \
   && [ "$(printf '%s\n' 2.28 "$GLIBC" | sort -V | head -n 1)" != 2.28 ]; then
    MONITOR=0
    MONITOR_SKIPPED="glibc $GLIBC < 2.28 on arm64: PyQt6 has no wheel for it"
fi

# ------------------------------------------------------------------ packages per family

case "$FAMILY" in
apt)
    PKG_BASE=(git ca-certificates curl unzip)
    PKG_GODOT=(libgl1 libegl1 libgl1-mesa-dri libglx-mesa0 libvulkan1 mesa-vulkan-drivers libx11-6 libxcursor1
               libxinerama1 libxrandr2 libxi6 libxext6 libxrender1 libxkbcommon0 libwayland-client0
               libwayland-cursor0 libwayland-egl1 libdecor-0-0 libfontconfig1 libasound2 libpulse0 libdbus-1-3
               libudev1)
    PKG_QT=(libglib2.0-0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0
            libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1)
    PKG_XVFB=(xvfb xauth)
    PKG_PY=(python3.11 python3.11-venv python3.11-dev)
    PKG_PROC=(build-essential cmake pkg-config libusb-1.0-0-dev libusb-dev libftdi1-dev)
    ;;
dnf)
    PKG_BASE=(git ca-certificates curl unzip)
    PKG_GODOT=(mesa-libGL mesa-libEGL mesa-dri-drivers mesa-vulkan-drivers vulkan-loader libX11 libXcursor
               libXinerama libXrandr libXi libXext libXrender libxkbcommon libwayland-client libwayland-cursor
               libwayland-egl libdecor fontconfig alsa-lib pulseaudio-libs dbus-libs systemd-libs)
    PKG_QT=(glib2 libxkbcommon-x11 xcb-util-cursor xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm)
    PKG_XVFB=(xorg-x11-server-Xvfb xorg-x11-xauth)
    PKG_PY=(python3.11 python3.11-devel)
    PKG_PROC=(gcc-c++ make cmake pkgconf-pkg-config libusb1-devel libusb-compat-0.1-devel libftdi-devel)
    ;;
pacman)
    PKG_BASE=(git ca-certificates curl unzip)
    PKG_GODOT=(libglvnd mesa vulkan-icd-loader libx11 libxcursor libxinerama libxrandr libxi libxext libxrender
               libxkbcommon wayland libdecor fontconfig alsa-lib libpulse dbus systemd-libs)
    PKG_QT=(glib2 libxkbcommon-x11 xcb-util-cursor xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm)
    PKG_XVFB=(xorg-server-xvfb xorg-xauth)
    PKG_PY=()           # Arch only packages the newest Python: 3.11 comes from uv
    PKG_PROC=(base-devel cmake pkgconf libusb libusb-compat libftdi)
    ;;
esac

have_tool() { command -v "$1" >/dev/null 2>&1; }

installed() {       # is package $1 installed? (false when the package tool is not there, e.g. a dry run elsewhere)
    case "$FAMILY" in
        apt) have_tool dpkg-query && [ "$(dpkg-query -W -f='${Status}' "$1" 2>/dev/null)" = "install ok installed" ] ;;
        dnf) have_tool rpm && rpm -q --whatprovides "$1" >/dev/null 2>&1 ;;
        pacman) have_tool pacman && pacman -Qq "$1" >/dev/null 2>&1 ;;
    esac
}

apt_known() {       # a real (not purely virtual) package $1 in the apt lists. No grep -q in a pipe: with
    local out          # pipefail, apt-cache's SIGPIPE would fail the test
    out="$(apt-cache show "$1" 2>/dev/null || true)"
    printf '%s\n' "$out" | grep -x "Package: $1" >/dev/null
}

apt_name() {        # Ubuntu 24.04 renamed some libraries for the 64-bit time_t move (libasound2 -> libasound2t64)
    if have_tool apt-cache && ! apt_known "$1" && apt_known "${1}t64"; then
        echo "${1}t64"
    else
        echo "$1"
    fi
}

APT_UPDATED=0
install_pkgs() {    # install the packages of "$@" that are missing
    local missing=() p
    for p in "$@"; do
        installed "$p" && continue
        [ "$FAMILY" = apt ] && installed "${p}t64" && continue
        missing+=("$p")
    done
    if [ ${#missing[@]} = 0 ]; then
        note "all in place"
        return 0
    fi
    if [ "$FAMILY" = apt ]; then    # fresh package lists first: they decide the t64 names
        if [ "$APT_UPDATED" = 0 ]; then root apt-get update -qq; APT_UPDATED=1; fi
        local i
        for i in "${!missing[@]}"; do missing[i]="$(apt_name "${missing[i]}")"; done
        # libdecor (Wayland window decorations, optional for Godot) is not in Ubuntu 20.04 / JetPack 5
        for i in "${!missing[@]}"; do
            case "${missing[i]}" in libdecor-0-0*)
                if have_tool apt-cache && ! apt_known "${missing[i]}"; then
                    note "${missing[i]} is not in this release: skipped (Godot only uses it on Wayland)"
                    unset 'missing[i]'
                fi ;;
            esac
        done
        missing=("${missing[@]}")
        [ ${#missing[@]} -gt 0 ] || return 0
    fi
    note "missing: ${missing[*]}"
    if [ "$DRY" = 0 ] && [ "$YES" = 0 ] && [ -t 0 ]; then
        local answer
        read -r -p "    Install them now? [Y/n] " answer
        case "$answer" in [nN]*) die "cancelled" ;; esac
    fi
    case "$FAMILY" in
        apt) root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "${missing[@]}" ;;
        dnf) root dnf install -y "${missing[@]}" ;;
        pacman) root pacman -S --needed --noconfirm "${missing[@]}" ;;
    esac
}

# ------------------------------------------------------------------ Python

python_ok() {       # python_ok EXE: Python 3.11 (3.10-3.14 with --python-any) with venv and ensurepip
    local want='sys.version_info[:2] == (3, 11)'
    [ "$PY_ANY" = 1 ] && want='(3, 10) <= sys.version_info[:2] <= (3, 14)'
    "$1" -c "import sys, venv, ensurepip; sys.exit(0 if $want else 1)" >/dev/null 2>&1
}

UV_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/mpf-godot/uv"

find_python() {     # prints the first suitable interpreter
    local c
    for c in python3.11 /usr/bin/python3.11 /usr/local/bin/python3.11 python3; do
        if have_tool "$c" && python_ok "$(command -v "$c")"; then command -v "$c"; return 0; fi
    done
    if [ -x "$UV_DIR/uv" ]; then
        c="$("$UV_DIR/uv" python find --managed-python 3.11 2>/dev/null || true)"
        if [ -n "$c" ] && python_ok "$c"; then echo "$c"; return 0; fi
    fi
    return 1
}

apt_has_python311() {   # a final (not release candidate) python3.11 in the configured apt sources
    have_tool apt-cache || return 1
    local v
    v="$(apt-cache policy python3.11 2>/dev/null | awk '/Candidate:/ {print $2}')"
    [ -n "$v" ] && [ "$v" != "(none)" ] && [[ "$v" != *"~rc"* ]] && [[ "$v" != *"~b"* ]]
}

deadsnakes() {
    say "Python 3.11 from the deadsnakes PPA (Ubuntu)"
    install_pkgs software-properties-common
    # set -e is off in a function called with ||: check each step, or Ubuntu 22.04's own python3.11
    # (3.11.0 release candidate) gets installed when the PPA could not be added
    root add-apt-repository -y ppa:deadsnakes/ppa || return 1
    APT_UPDATED=0
    if [ "$DRY" = 0 ]; then
        root apt-get update -qq || return 1
        APT_UPDATED=1
        apt_has_python311 || return 1
    fi
    install_pkgs "${PKG_PY[@]}"
}

uv_python() {
    say "Python 3.11: standalone build with uv $UV_VERSION (no system Python 3.11 available)"
    note "uv: $UV_DIR/uv; the interpreter goes to uv's Python directory (~/.local/share/uv/python)"
    if [ ! -x "$UV_DIR/uv" ]; then
        local tag url tmp
        tag="manylinux_2_17_$ARCH"
        if [ "$DRY" = 1 ]; then
            note "would fetch the uv $UV_VERSION wheel ($tag) from PyPI and unpack its uv binary"
        else
            local json
            json="$(curl -fsSL "https://pypi.org/pypi/uv/$UV_VERSION/json")" || die "cannot reach PyPI for uv $UV_VERSION"
            url="$(printf '%s' "$json" | grep -o "https://files.pythonhosted.org/[^\"]*-py3-none-${tag}[^\"]*\\.whl" || true)"
            url="${url%%$'\n'*}"
            [ -n "$url" ] || die "no uv $UV_VERSION wheel for $ARCH on PyPI"
            tmp="$(mktemp -d)"
            run curl -fsSL -o "$tmp/uv.whl" "$url"
            run mkdir -p "$UV_DIR"
            run unzip -q -o -j "$tmp/uv.whl" "uv-$UV_VERSION.data/scripts/uv" -d "$UV_DIR"
            rm -rf "$tmp"
        fi
    fi
    run "$UV_DIR/uv" python install 3.11
}

# ------------------------------------------------------------------ plan

say "MPF + Godot prerequisites on $DISTRO_NAME ($FAMILY, $ARCH)$([ "$DRY" = 1 ] && echo ', dry run')"

if [ "$XVFB" = 0 ] && [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    note "no DISPLAY: adding Xvfb (Godot runs under xvfb-run without a screen)"
    XVFB=1
fi

WANT=("${PKG_BASE[@]}" "${PKG_GODOT[@]}")
[ "$MONITOR" = 1 ] && WANT+=("${PKG_QT[@]}")
[ "$XVFB" = 1 ] && WANT+=("${PKG_XVFB[@]}")
[ "$PROC" = 1 ] && WANT+=("${PKG_PROC[@]}")

PY=""
PY_FROM=""
if PY="$(find_python)"; then
    note "Python: $PY ($("$PY" -c 'import platform; print(platform.python_version())'))"
else
    PY=""
    case "$FAMILY" in
        apt) if apt_has_python311; then WANT+=("${PKG_PY[@]}"); PY_FROM=pkg
             elif [ "$DISTRO_ID" = ubuntu ]; then PY_FROM=deadsnakes
             else PY_FROM=uv; fi ;;
        dnf) WANT+=("${PKG_PY[@]}"); PY_FROM=pkg ;;
        pacman) PY_FROM=uv ;;
    esac
    note "Python 3.11 is missing: it will come from $PY_FROM"
fi

say "System packages"
install_pkgs "${WANT[@]}"

if [ -z "$PY" ]; then
    if [ "$PY_FROM" = deadsnakes ]; then
        deadsnakes || note "the deadsnakes PPA did not work, falling back to uv"
    fi
    if [ "$DRY" = 0 ]; then PY="$(find_python || true)"; fi
    if [ -z "$PY" ]; then
        uv_python
        if [ "$DRY" = 0 ]; then PY="$(find_python || true)"; fi
    fi
    if [ "$DRY" = 1 ]; then
        PY="${PY:-python3.11}"
    elif [ -z "$PY" ]; then
        die "no usable Python 3.11 after installing it (see the messages above)"
    fi
    note "Python: $PY"
fi

[ "$AUTH_DONE" = 1 ] || github_auth    # git was missing at the start

# ------------------------------------------------------------------ repository (run on its own: clone it)

# Before a pull: files the update adds that are already here, untracked, would stop `git pull` ("untracked
# working tree files would be overwritten"). Godot writes a .uid next to every script it opens, so a new
# script's .uid is often on disk before the commit that adds it. Remove those, and any copy identical to the
# update's; move anything else aside as <file>.local so nothing of the player's is lost.
clear_untracked_in_update() {
    local up f
    up="$(git -C "$ROOT" rev-parse -q --verify '@{u}' 2>/dev/null)" || return 0
    while IFS= read -r -d '' f; do
        [ -e "$ROOT/$f" ] || [ -L "$ROOT/$f" ] || continue
        git -C "$ROOT" ls-files --error-unmatch -- "$f" >/dev/null 2>&1 && continue
        case "$f" in
            *.uid|*.import) run rm -f -- "$ROOT/$f" ;;
            *)  if [ -f "$ROOT/$f" ] && [ "$(git -C "$ROOT" hash-object -- "$f")" = "$(git -C "$ROOT" rev-parse "$up:$f")" ]; then
                    run rm -f -- "$ROOT/$f"
                else
                    note "kept your copy of $f as $f.local (the update adds its own)"
                    run mv -- "$ROOT/$f" "$ROOT/$f.local"
                fi ;;
        esac
    done < <(git -C "$ROOT" diff -z --name-only --no-renames --diff-filter=A HEAD "$up" --)
}

if [ "$CLONE" = 1 ]; then
    say "Repository: $REPO_URL ($REPO_BRANCH) in $ROOT"
    if [ -d "$ROOT/.git" ]; then
        # an existing clone: update its branch, or move to $REPO_BRANCH when that branch is gone from GitHub
        # (a deleted pull-request branch) or none is checked out
        CUR="$(git -C "$ROOT" symbolic-ref --short -q HEAD 2>/dev/null || true)"
        if [ -n "$CUR" ] && git -C "$ROOT" ls-remote --exit-code --heads origin "$CUR" >/dev/null 2>&1; then
            run git -C "$ROOT" fetch origin
            clear_untracked_in_update
            run git -C "$ROOT" pull --ff-only
        else
            note "branch '${CUR:-none}' is no longer on GitHub: switching to $REPO_BRANCH"
            run git -C "$ROOT" fetch --prune origin
            run git -C "$ROOT" checkout -B "$REPO_BRANCH" --track "origin/$REPO_BRANCH"
        fi
    else
        run git clone --branch "$REPO_BRANCH" "$REPO_URL" "$ROOT"
    fi
fi

# ------------------------------------------------------------------ toolchain

if [ "$SETUP" = 1 ]; then
    say "MPF, MPF Monitor, Godot and GMC (python -m mpf_godot setup)"
    [ -z "${MONITOR_SKIPPED:-}" ] || note "MPF Monitor left out: $MONITOR_SKIPPED"
    ARGS=()
    [ "$MONITOR" = 1 ] || ARGS+=(--no-monitor)
    [ "$DRY" = 1 ] && ARGS+=(--dry-run)
    ARGS+=(${SETUP_ARGS[@]+"${SETUP_ARGS[@]}"})
    if [ "$DRY" = 1 ] && { ! have_tool "$PY" || [ ! -d "$ROOT/mpf_godot" ]; }; then
        note "\$ (cd $ROOT && $PY -m mpf_godot setup ${ARGS[*]-})"
    else
        printf '    $ %s\n' "(cd $ROOT && $PY -m mpf_godot setup ${ARGS[*]-})"
        (cd "$ROOT" && "$PY" -m mpf_godot setup ${ARGS[@]+"${ARGS[@]}"})
    fi
else
    note "skipping the toolchain (--no-setup): run  (cd $ROOT && $PY -m mpf_godot setup)  when ready"
fi

if [ "$PROC" = 1 ]; then
    say "P-ROC: libpinproc + pypinproc"
    if [ "$SETUP" = 1 ] || [ "$DRY" = 1 ] || [ -x "$ROOT/.venv/bin/python" ]; then
        BUILD=("$HERE/build_pinproc.sh" --python "$ROOT/.venv/bin/python")
        [ "$DRY" = 1 ] && BUILD+=(--dry-run)
        if [ "$DRY" = 1 ]; then printf '    $ %s\n' "${BUILD[*]}"; else "${BUILD[@]}"; fi
    else
        note "no .venv yet: run install/build_pinproc.sh after python -m mpf_godot setup"
    fi
    say "P-ROC: USB access (udev rule $UDEV_RULE)"
    if [ -f "$UDEV_RULE" ] && cmp -s "$HERE/99-pinproc.rules" "$UDEV_RULE"; then
        note "in place"
    else
        root install -D -m 0644 "$HERE/99-pinproc.rules" "$UDEV_RULE"
        if have_tool udevadm && [ -d /run/udev ]; then
            root udevadm control --reload-rules
            root udevadm trigger --subsystem-match=usb
        else
            note "no running udev (container?): the rule applies on the host after a reload or reboot"
        fi
    fi
fi

# a Jetson: the hardware video decoder for GDE GoZen (platforms/jetson.md); MPF_GODOT_HWDEC=0 or --no-jetson skips it
if [ -f "${MPF_GODOT_NV_RELEASE:-/etc/nv_tegra_release}" ] && [ "$JETSON" = 1 ]; then
    "$ROOT/platforms/jetson/install_jetson_hwdec.sh" $([ "$DRY" = 1 ] && echo --dry-run) || note "warning: the Jetson decoder install failed (videos decode in software)"
fi
say "Done$([ "$DRY" = 1 ] && echo ' (dry run: nothing was changed)')"
if [ "$SETUP" = 1 ]; then
    note "Toolchain in $ROOT:"
    note "Paths and versions:  $ROOT/.venv/bin/python -m mpf_godot info"
    note "Into a game:         $ROOT/.venv/bin/python -m mpf_godot addons <game folder> [--video]"
    note "Start a game:        $ROOT/.venv/bin/python -m mpf_godot run <game folder>$([ "$MONITOR" = 1 ] && echo ' [--monitor]')"
fi
