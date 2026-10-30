#!/bin/bash
# Is the system really quiet on its flash? Run it after the game has played for a while (or at any time):
#   sudo mpf-ro-check
# It shows the mode, every writable real mount, the failed units (a service that wanted to write to a read-only place),
# how much each partition was written since boot (sectors from /sys/block/*/*/stat) and the processes that wrote most.
# Expected in production: the root and boot partitions at 0 MB; the data partition a few MB at most.
CONF="${MPF_READONLY_CONF:-/etc/mpf-readonly.conf}"
[ -r "$CONF" ] && . "$CONF"
DATA="${MPF_DATA_MOUNT:-/data}"
echo "== mode";           mpf-mode status
echo; echo "== writable mounts on real storage"
findmnt -rno TARGET,SOURCE,FSTYPE,OPTIONS | awk '$3 ~ /^(ext[234]|vfat|xfs|btrfs|f2fs)$/ && $4 !~ /(^|,)ro(,|$)/ {print "  " $1 "  " $2 "  (" $3 ")"}'
echo; echo "== failed units";  systemctl --no-legend --failed | sed 's/^/  /'; systemctl --failed --quiet || true
echo; echo "== written since boot (MB)"
for s in /sys/block/*/*/stat; do
    part="$(basename "$(dirname "$s")")"; disk="$(basename "$(dirname "$(dirname "$s")")")"
    case "$disk" in loop*|ram*|zram*) continue;; esac
    read -r -a f < "$s"; mb=$(( ${f[6]} / 2048 ))
    mnt="$(findmnt -rno TARGET -S "/dev/$part" | head -1)"
    printf '  %-12s %6d MB  %s\n' "$part" "$mb" "${mnt:-}"
done
echo; echo "== processes that wrote most (write_bytes since they started)"
for p in /proc/[0-9]*; do
    [ -r "$p/io" ] || continue
    b="$(awk '/^write_bytes/ {print $2}' "$p/io" 2>/dev/null)"; [ "${b:-0}" -gt 0 ] || continue
    printf '%d\t%s\t%s\n' "$b" "${p#/proc/}" "$(tr '\0' ' ' < "$p/cmdline" | cut -c1-80)"
done | sort -rn | head -8 | awk -F'\t' '{printf "  %8.1f KB  pid %-6s %s\n", $1/1024, $2, $3}'
echo; echo "== journal: write errors on a read-only place"
journalctl -b -q --no-pager 2>/dev/null | grep -i "read-only file system" | tail -10 | sed 's/^/  /'
true
