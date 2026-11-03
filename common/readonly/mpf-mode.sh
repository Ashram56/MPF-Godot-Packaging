#!/bin/bash
# Production (read-only) or maintenance (writable) mode of an MPF image.
#   mpf-mode status                  production | maintenance, and whether it stays after a reboot
#   mpf-mode maintenance [--stay]    root (and boot) partition writable now; --stay: also after the next boots
#   mpf-mode production              back to read-only now (if a program still holds a file open for writing: reboot)
# The data partition is always writable. Nothing else changes between the modes.
set -u
CONF="${MPF_READONLY_CONF:-/etc/mpf-readonly.conf}"
[ -r "$CONF" ] && . "$CONF"
DATA="${MPF_DATA_MOUNT:-/data}"; BOOT="${MPF_BOOT_MOUNT:-}"
FLAG="$DATA/mpf/maintenance"

is_ro() { findmnt -n -o OPTIONS "$1" | tr ',' '\n' | grep -qx ro; }
set_mount() {   # set_mount ro|rw MOUNTPOINT...
    local m="$1" rc=0; shift
    for p in "$@"; do
        [ -n "$p" ] && mountpoint -q "$p" || continue
        mount -o "remount,$m" "$p" || rc=1
    done
    return $rc
}
need_root() { [ "$(id -u)" = 0 ] || exec sudo "$0" "$@"; }

case "${1:-status}" in
    status)
        if is_ro /; then echo "production (root read-only)"; else echo "maintenance (root writable)"; fi
        [ -e "$FLAG" ] && echo "maintenance stays after a reboot (mpf-mode production to end it)"
        [ -e /run/mpf-persist.degraded ] && echo "WARNING: no data partition, settings are in RAM"
        exit 0;;
    maintenance)
        need_root "$@"
        set_mount rw / "$BOOT" || { echo "could not make the system writable" >&2; exit 1; }
        if [ "${2:-}" = --stay ]; then mkdir -p "$DATA/mpf"; : > "$FLAG"; fi
        echo "maintenance mode: the system is writable. mpf-mode production (or a reboot, unless --stay) ends it.";;
    rw-only)   # boot time, from mpf-persist
        set_mount rw / "$BOOT";;
    production)
        need_root "$@"
        rm -f "$FLAG"
        sync
        if set_mount ro / "$BOOT"; then echo "production mode: read-only."
        else echo "a program still holds a file open for writing: reboot to be read-only (the maintenance flag is cleared)" >&2; exit 1; fi;;
    *) echo "usage: mpf-mode status|maintenance [--stay]|production" >&2; exit 2;;
esac
