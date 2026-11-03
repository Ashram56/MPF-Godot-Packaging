#!/bin/bash
# Early at every boot (mpf-persist.service, before local-fs.target): make the one read/write partition available and put
# the folders that must keep their content on it. Everything else stays read-only. Steps:
#   1. find the partition labelled MPF_DATA_LABEL; if there is none (first boot), create it in the free space at the end
#      of the disk the root lives on, and format it (ext4 with its journal: a cabinet loses power without warning)
#      an image made with common/games/inject_image.py carries a small FAT32 partition labelled MPFSEED instead (games in its inbox/,
#      made without Linux tools): its files are copied into <data>/inbox once, at step 2. An older image made by that tool carries
#      the partition itself (games in its inbox): it is grown to the end of the disk when it is the last partition and free space follows it
#   2. fsck -p, mount it on MPF_DATA_MOUNT (noatime); if that fails, a tmpfs takes its place so the system still boots
#   3. for each "name:target" of MPF_PERSIST, seed <data>/persist/<name> from the image's target once, bind-mount it over the target
#   4. if the maintenance flag (<data>/mpf/maintenance) is there, switch the root (and boot) partition to writable
set -u
CONF="${MPF_READONLY_CONF:-/etc/mpf-readonly.conf}"
[ -r "$CONF" ] && . "$CONF"
LABEL="${MPF_DATA_LABEL:-mpfdata}"; DATA="${MPF_DATA_MOUNT:-/data}"; MINMB="${MPF_DATA_MIN_MB:-512}"
USERNAME="${MPF_USER:-}"
DEGRADED=/run/mpf-persist.degraded
log() { echo "mpf-persist: $*"; }

create_partition() {
    local rootpart disk before after new label
    rootpart="$(findmnt -n -o SOURCE /)"
    disk="${MPF_ROOT_DISK:-/dev/$(lsblk -no pkname "$rootpart" 2>/dev/null | head -1)}"   # MPF_ROOT_DISK: for tests
    [ -b "$disk" ] || { log "cannot find the disk of $rootpart"; return 1; }
    label="$(blkid -p -o value -s PTTYPE "$disk" 2>/dev/null)"
    # a disk bigger than the image: the GPT backup header is still in the middle of the disk, move it to the end first
    [ "$label" = gpt ] && sfdisk --relocate gpt-bak-std "$disk" >/dev/null 2>&1
    # free space after the last partition, in MB
    local free_mb
    free_mb="$(sfdisk --list-free --bytes "$disk" 2>/dev/null | awk '$1 ~ /^[0-9]+$/ && $4 > m {m=$4} END {printf "%d", m/1048576}')"
    if [ "${free_mb:-0}" -lt "$MINMB" ]; then log "only ${free_mb:-0} MB free on $disk (need $MINMB)"; return 1; fi
    before="$(lsblk -lnpo NAME "$disk" | sort)"
    if [ "$label" = gpt ]; then echo ',,L' | sfdisk --append --no-reread -q "$disk" || return 1
    else echo ',,83' | sfdisk --append --no-reread -q "$disk" || return 1; fi
    # the disk is in use (the root is mounted): tell the kernel only about the new partition
    partx -a "$disk" >/dev/null 2>&1 || partprobe "$disk" >/dev/null 2>&1
    udevadm settle --timeout=30
    after="$(lsblk -lnpo NAME "$disk" | sort)"
    new="$(comm -13 <(echo "$before") <(echo "$after") | head -1)"
    [ -b "$new" ] || { log "the new partition did not appear"; return 1; }
    log "creating $new (${free_mb} MB) as $LABEL"
    mkfs.ext4 -q -F -L "$LABEL" -m 0 "$new" || return 1
}

# The image carries a small data partition (common/games/inject_image.py) and the card is bigger: take the free space after it.
grow_partition() {
    local dev="$1" name disk num start size pend free_sectors
    name="$(basename "$(readlink -f "$dev")")"
    [ -r "/sys/class/block/$name/partition" ] || return 0
    num="$(cat "/sys/class/block/$name/partition")"
    disk="${MPF_ROOT_DISK:-/dev/$(lsblk -no pkname "$dev" 2>/dev/null | head -1)}"
    [ -b "$disk" ] || return 0
    if [ "$(blkid -p -o value -s PTTYPE "$disk" 2>/dev/null)" = gpt ]; then
        sfdisk --relocate gpt-bak-std "$disk" >/dev/null 2>&1
        partx -a "$disk" >/dev/null 2>&1      # the kernel may have dropped the partitions when the table was rewritten
    fi
    start="$(cat "/sys/class/block/$name/start")"; size="$(cat "/sys/class/block/$name/size")"
    pend=$((start + size))
    # a free region that begins right after this partition (sfdisk reports sectors of 512 bytes here)
    free_sectors="$(sfdisk --list-free "$disk" 2>/dev/null | awk -v s="$pend" '$1 == s {print $3}' | head -1)"
    [ "${free_sectors:-0}" -ge 32768 ] || return 0       # nothing after it, or under 16 MB
    log "growing $dev by $((free_sectors / 2048)) MB"
    echo ', +' | sfdisk -N "$num" --no-reread -q "$disk" >/dev/null 2>&1 || { log "cannot grow the partition table of $disk"; return 0; }
    partx -u --nr "$num" "$disk" >/dev/null 2>&1 || partprobe "$disk" >/dev/null 2>&1
    udevadm settle --timeout=30
    e2fsck -fp "$dev" >/dev/null 2>&1
    resize2fs "$dev" >/dev/null 2>&1 || log "resize2fs failed on $dev"
}

# Games put in the image before flashing (inject_image.py): the FAT32 partition MPFSEED holds an inbox/ folder. Copied once.
import_seed() {
    local seed id marker mnt="${MPF_SEED_MOUNT:-/run/mpf-seed}"
    seed="$(blkid -L "${MPF_SEED_LABEL:-MPFSEED}" 2>/dev/null)"
    [ -n "$seed" ] || return 0
    [ -e "$DEGRADED" ] && return 0                      # the data is in RAM: do not use it up with bundles
    id="$(blkid -s UUID -o value "$seed" 2>/dev/null)"; id="${id:-seed}"
    marker="$DATA/mpf/seed-imported-$id"
    [ -e "$marker" ] && return 0
    mkdir -p "$mnt" "$DATA/inbox" "$DATA/mpf"
    mount -t vfat -o ro,nosuid,nodev,noexec "$seed" "$mnt" || { log "cannot mount the seed $seed"; return 0; }
    if [ -d "$mnt/inbox" ]; then
        if cp -r --no-preserve=mode,ownership "$mnt/inbox/." "$DATA/inbox/"; then
            sync; : > "$marker"; log "copied the games of $seed to $DATA/inbox"
        else
            log "copying the games of $seed failed"
        fi
    fi
    umount "$mnt"
}

dev="$(blkid -L "$LABEL" 2>/dev/null)"
if [ -z "$dev" ]; then
    udevadm settle --timeout=30
    dev="$(blkid -L "$LABEL" 2>/dev/null)"
fi
if [ -z "$dev" ] && create_partition; then dev="$(blkid -L "$LABEL" 2>/dev/null)"; fi

mkdir -p "$DATA"
if [ -n "$dev" ] && [ -z "${MPF_NO_GROW:-}" ]; then grow_partition "$dev"; fi
if [ -n "$dev" ]; then
    e2fsck -p "$dev" >/dev/null 2>&1; rc=$?
    [ "$rc" -ge 4 ] && log "e2fsck found errors it could not fix on $dev (rc $rc)"
    mount -o noatime "$dev" "$DATA" || { log "cannot mount $dev"; dev=""; }
fi
if [ -z "$dev" ]; then
    log "WARNING: no data partition: $DATA is in RAM, settings and scores are lost at power-off"
    mount -t tmpfs -o size=256m,mode=0755 tmpfs "$DATA"
    : > "$DEGRADED"
fi
mkdir -p "$DATA/persist" "$DATA/mpf" "$DATA/uploads" "$DATA/cache"
import_seed
if [ -n "$USERNAME" ] && id "$USERNAME" >/dev/null 2>&1; then chown "$USERNAME": "$DATA/cache"; fi

for pair in ${MPF_PERSIST:-}; do
    name="${pair%%:*}"; target="${pair#*:}"
    src="$DATA/persist/$name"
    if [ ! -e "$target" ]; then log "skip $name: $target is not in the image"; continue; fi
    if [ ! -e "$src" ]; then
        if [ -d "$target" ]; then
            mkdir -p "$src"
            cp -a "$target/." "$src/"
            chown --reference="$target" "$src"; chmod --reference="$target" "$src"
        else
            cp -a "$target" "$src"
        fi
    fi
    # a file and a folder cannot replace each other
    if [ -d "$target" ] && [ ! -d "$src" ] || [ -f "$target" ] && [ ! -f "$src" ]; then log "skip $name: $src is not the same kind as $target"; continue; fi
    mount --bind "$src" "$target" || log "cannot bind $src on $target"
done

if [ -e "$DATA/mpf/maintenance" ]; then
    log "maintenance flag: the system is writable"
    /usr/local/sbin/mpf-mode rw-only
fi
exit 0
