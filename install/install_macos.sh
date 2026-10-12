#!/usr/bin/env bash
# Installs MPF, MPF Monitor, Godot and GMC with our fixes on macOS (12 or newer, Intel or Apple silicon), with
# Python 3.11 and Git when they are missing. Safe to re-run.
#
#   install/install_macos.sh                 # Python 3.11 + Git, then python -m mpf_godot setup
#   install/install_macos.sh --no-monitor    # ... without MPF Monitor (installed by default)
#   install/install_macos.sh --proc          # ... plus libpinproc/pypinproc, built (needs Homebrew)
#   install/install_macos.sh --dry-run       # print the plan, change nothing
#   install/install_macos.sh -- --extra pillow   # arguments after -- go to python -m mpf_godot setup
#
# Options: --yes (no questions), --no-setup (prerequisites only), --python-org (use the python.org installer
# even when Homebrew is there). With Homebrew: `brew install python@3.11 git`. Without it: the python.org
# 3.11 installer (universal2 .pkg, needs an admin password) and Git from the Xcode Command Line Tools.
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
# The last Python 3.11 release with a macOS installer (later 3.11 releases are source-only security fixes)
PYORG_VERSION="3.11.9"
PYORG_PKG="python-${PYORG_VERSION}-macos11.pkg"
PYORG_URL="https://www.python.org/ftp/python/${PYORG_VERSION}/${PYORG_PKG}"
PYORG_PY="/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"

DRY=0 YES=0 MONITOR=1 PROC=0 SETUP=1 PYORG=0
SETUP_ARGS=()

usage() { sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY=1 ;;
        -y|--yes) YES=1 ;;
        --monitor) MONITOR=1 ;;
        --no-monitor) MONITOR=0 ;;
        --proc) PROC=1 ;;
        --no-setup) SETUP=0 ;;
        --python-org) PYORG=1 ;;
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
# (/usr/bin/git is only a stub until the Command Line Tools are installed: calling it opens their installer)
GIT_PATH="$(command -v git 2>/dev/null || true)"
if [ -n "$GIT_PATH" ] && { [ "$GIT_PATH" != /usr/bin/git ] || xcode-select -p >/dev/null 2>&1; }; then github_auth; fi

have_tool() { command -v "$1" >/dev/null 2>&1; }
confirm() {
    if [ "$DRY" = 0 ] && [ "$YES" = 0 ] && [ -t 0 ]; then
        local answer
        read -r -p "    $1 [Y/n] " answer
        case "$answer" in [nN]*) die "cancelled" ;; esac
    fi
}

if [ "$(uname -s)" != Darwin ]; then
    [ "$DRY" = 1 ] || die "this script is for macOS (Linux: install_linux.sh)"
    note "not macOS: showing the plan only"
fi

MACOS="$(sw_vers -productVersion 2>/dev/null || echo unknown)"
say "MPF + Godot prerequisites on macOS $MACOS ($(uname -m))$([ "$DRY" = 1 ] && echo ', dry run')"
case "$MACOS" in
    10.*|11.*) note "warning: macOS 12 or newer is needed (Godot 4.6, current Python and Qt builds)" ;;
esac

BREW=""
for b in brew /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if have_tool "$b"; then BREW="$(command -v "$b")"; break; fi
done
if [ -n "$BREW" ] && [ "$PYORG" = 0 ]; then note "Homebrew: $BREW"; else note "Homebrew: not used"; fi

python_ok() { "$1" -c "import sys, venv, ensurepip; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)" >/dev/null 2>&1; }

find_python() {
    local c
    for c in python3.11 /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11 "$PYORG_PY"; do
        if have_tool "$c" && python_ok "$(command -v "$c")"; then command -v "$c"; return 0; fi
    done
    return 1
}

brew_install() {    # brew_install FORMULA...: the ones that are not installed
    local missing=() f
    for f in "$@"; do
        "$BREW" list --formula "$f" >/dev/null 2>&1 || missing+=("$f")
    done
    if [ ${#missing[@]} = 0 ]; then note "in place: $*"; return 0; fi
    confirm "brew install ${missing[*]}?"
    run "$BREW" install "${missing[@]}"
}

# ------------------------------------------------------------------ Git

say "Git"
if have_tool git && git --version >/dev/null 2>&1; then
    note "in place: $(git --version)"
elif [ -n "$BREW" ]; then
    brew_install git
else
    # /usr/bin/git is a stub until the Command Line Tools are installed; this opens Apple's installer
    run xcode-select --install || true
    die "finish the Command Line Tools install that macOS just opened, then run this script again"
fi

# ------------------------------------------------------------------ Python 3.11

say "Python 3.11"
PY=""
if PY="$(find_python)"; then
    note "in place: $PY"
elif [ -n "$BREW" ] && [ "$PYORG" = 0 ]; then
    brew_install python@3.11
    PY="$("$BREW" --prefix python@3.11 2>/dev/null || echo /opt/homebrew/opt/python@3.11)/bin/python3.11"
else
    note "python.org installer $PYORG_VERSION (universal2): $PYORG_URL"
    confirm "Download and install it (asks for an admin password)?"
    TMP="$(mktemp -d)"
    run curl -fSL -o "$TMP/$PYORG_PKG" "$PYORG_URL"
    run sudo installer -pkg "$TMP/$PYORG_PKG" -target /
    # python.org builds bring no CA certificates of their own; this installs certifi's
    run "/Applications/Python 3.11/Install Certificates.command"
    rm -rf "$TMP"
    PY="$PYORG_PY"
fi
if [ "$DRY" = 0 ]; then
    python_ok "$PY" || die "no usable Python 3.11 at $PY (see the messages above)"
fi
note "Python: $PY"

# ------------------------------------------------------------------ P-ROC build tools

if [ "$PROC" = 1 ]; then
    say "P-ROC build tools (Homebrew)"
    [ -n "$BREW" ] || die "--proc needs Homebrew (https://brew.sh) for cmake, libusb, libusb-compat and libftdi"
    brew_install cmake pkg-config libusb libusb-compat libftdi
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
    ARGS=()
    [ "$MONITOR" = 1 ] || ARGS+=(--no-monitor)
    [ "$DRY" = 1 ] && ARGS+=(--dry-run)
    [ "$(uname -s)" = Darwin ] || ARGS+=(--os macos)      # the plan shown on another OS
    ARGS+=(${SETUP_ARGS[@]+"${SETUP_ARGS[@]}"})
    if [ "$DRY" = 1 ] && { ! have_tool "$PY" || [ ! -d "$ROOT/mpf_godot" ]; }; then
        note "\$ (cd $ROOT && $PY -m mpf_godot setup ${ARGS[*]-})"
    else
        printf '    $ %s\n' "(cd $ROOT && $PY -m mpf_godot setup ${ARGS[*]-})"
        (cd "$ROOT" && "$PY" -m mpf_godot setup ${ARGS[@]+"${ARGS[@]}"})
    fi
fi
if [ "$PROC" = 1 ]; then
    say "P-ROC: libpinproc + pypinproc"
    BUILD=("$HERE/build_pinproc.sh" --python "$ROOT/.venv/bin/python" --prefix "$("$BREW" --prefix 2>/dev/null || echo /usr/local)")
    [ "$DRY" = 1 ] && BUILD+=(--dry-run)
    if [ "$DRY" = 1 ]; then printf '    $ %s\n' "${BUILD[*]}"; else "${BUILD[@]}"; fi
    note "If macOS claims the P-ROC as /dev/tty.usbserial*, install FTDI's D2xxHelper and reboot (platforms/macos.md)."
fi
say "Done$([ "$DRY" = 1 ] && echo ' (dry run: nothing was changed)')"
if [ "$SETUP" = 1 ]; then
    note "Toolchain in $ROOT:"
    note "Paths and versions:  $ROOT/.venv/bin/python -m mpf_godot info"
    note "Into a game:         $ROOT/.venv/bin/python -m mpf_godot addons <game folder> [--video]"
    note "Start a game:        $ROOT/.venv/bin/python -m mpf_godot run <game folder>$([ "$MONITOR" = 1 ] && echo ' [--monitor]')"
fi
