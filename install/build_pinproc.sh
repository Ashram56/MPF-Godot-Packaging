#!/usr/bin/env bash
# Builds libpinproc and pypinproc (the P-ROC driver library and its Python module) and installs pypinproc
# into a Python environment. Linux and macOS. Only needed to drive a real machine through a P-ROC: MPF has
# no pypinproc for Linux and its macOS one is an old Intel-only build (fixes/mpf/pinproc-linux-macos.md).
#
#   install/build_pinproc.sh                       # into .venv (run python -m mpf_godot setup first)
#   install/build_pinproc.sh --python /opt/venv/bin/python --prefix /usr/local
#   install/build_pinproc.sh --dry-run             # print the plan, change nothing
#
# Needs a C++ compiler, CMake, pkg-config, git, libusb-1.0, libusb-compat (pkg-config name "libusb") and
# libftdi1 with their headers: the install_*.sh scripts install them with --proc.
# Safe to re-run: nothing is built when the Python environment can already `import pinproc` (--force rebuilds).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Pinned sources. libpinproc: the default (dev) branch of the upstream repo. pypinproc: the Python 3 port
# that MPF uses (preble/pypinproc is Python 2 only).
LIBPINPROC_URL="https://github.com/preble/libpinproc.git"
LIBPINPROC_REF="286c56694dae9f068e6ba14f8f625026f15e54c7"
PYPINPROC_URL="https://github.com/missionpinball/pypinproc.git"
PYPINPROC_REF="71ad50c3dfdf13c963497def8cd3777b00c25aec"

PY="$ROOT/.venv/bin/python"
PREFIX="/usr/local"
SRC=""
DRY=0
FORCE=0

usage() { sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --python) PY="$2"; shift 2 ;;
        --prefix) PREFIX="$2"; shift 2 ;;
        --src) SRC="$2"; shift 2 ;;
        --dry-run) DRY=1; shift ;;
        --force) FORCE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
done

say() { printf '==> %s\n' "$*"; }
run() {
    printf '    $ %s\n' "$*"
    if [ "$DRY" = 0 ]; then "$@"; fi
}
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

SUDO=()
if [ "$(id -u)" != 0 ] && [ ! -w "$PREFIX" ]; then
    SUDO=(sudo)
fi

fetch() {   # fetch URL REF DIR: the one commit, shallow
    local url="$1" ref="$2" dir="$3"
    if [ -d "$dir/.git" ] && [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" = "$ref" ]; then
        printf '    %s at %s\n' "$dir" "${ref:0:12}"
        return
    fi
    run rm -rf "$dir"
    run git init -q "$dir"
    run git -C "$dir" fetch -q --depth 1 "$url" "$ref"
    run git -C "$dir" -c advice.detachedHead=false checkout -q FETCH_HEAD
}

say "P-ROC driver: libpinproc ${LIBPINPROC_REF:0:12} + pypinproc ${PYPINPROC_REF:0:12} for $PY"
if [ "$DRY" = 0 ] && [ "$FORCE" = 0 ] && "$PY" -c "import pinproc" 2>/dev/null; then
    echo "    pinproc is already importable: nothing to do (--force rebuilds)"
    exit 0
fi
if [ "$DRY" = 0 ]; then
    [ -x "$PY" ] || die "no Python at $PY (run python -m mpf_godot setup first, or pass --python)"
    for tool in git cmake pkg-config c++; do
        command -v "$tool" >/dev/null || die "$tool is missing (install the build tools: install_*.sh --proc)"
    done
    for pc in libusb-1.0 libusb libftdi1; do
        pkg-config --exists "$pc" || die "pkg-config finds no $pc (install its -dev/-devel package)"
    done
fi

SRC="${SRC:-${XDG_CACHE_HOME:-$HOME/.cache}/mpf-godot/pinproc}"
run mkdir -p "$SRC"
fetch "$LIBPINPROC_URL" "$LIBPINPROC_REF" "$SRC/libpinproc"
fetch "$PYPINPROC_URL" "$PYPINPROC_REF" "$SRC/pypinproc"

say "libpinproc (shared library into $PREFIX)"
run cmake -S "$SRC/libpinproc" -B "$SRC/libpinproc/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON \
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DCMAKE_INSTALL_PREFIX="$PREFIX"
run cmake --build "$SRC/libpinproc/build" --parallel
run ${SUDO[@]+"${SUDO[@]}"} cmake --install "$SRC/libpinproc/build"
if [ "$(uname -s)" = Linux ] && command -v ldconfig >/dev/null; then
    run ${SUDO[@]+"${SUDO[@]}"} ldconfig
fi

say "pypinproc (Python module into $PY's environment)"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig:$PREFIX/lib64/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
run "$PY" -m pip install --quiet "$SRC/pypinproc"
run "$PY" -c "import pinproc; print('    pinproc OK:', pinproc.__file__)"
say "Done. The P-ROC also needs USB access: install/99-pinproc.rules on Linux (install_linux.sh --proc)."
