#!/usr/bin/env bash
# Sourced by the image build scripts: puts the read-only production mode (common/readonly/README.md) into a rootfs.
#
#   . "$REPO_ROOT/common/readonly/install-readonly.sh"
#   mpf_readonly_install ROOTFS USER BOOT_MOUNT ["extra:/persistent/target ..."] ["/path:size ..."]
#
#   ROOTFS      the directory the image is built in
#   USER        the cabinet user (owns the persistent ~/.ssh and the folders on the data partition)
#   BOOT_MOUNT  where the FAT boot partition is mounted in the image (/boot/firmware, /boot/efi), "" when there is none
#   extra       more "name:target" pairs for MPF_PERSIST (a target that does not exist in the image is skipped)
#   volatile    more "path:size" pairs for MPF_VOLATILE (folders that a service rewrites at every boot: a tmpfs over them)
# The platform scripts keep their own partition layout: nothing here depends on it. The data partition is made by
# mpf-persist at the first boot, in the free space at the end of the disk.
# Everything is driven by /etc/mpf-readonly.conf (mpf-readonly.conf.default): change a list there, not this function.

mpf_readonly_install() {
    local R="$1" user="$2" boot="${3:-}" extra="${4:-}" volatile="${5:-}" here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    install -d "$R/usr/local/sbin" "$R/etc/systemd/system/local-fs.target.wants"
    install -m 755 "$here/mpf-persist.sh" "$R/usr/local/sbin/mpf-persist"
    install -m 755 "$here/mpf-mode.sh" "$R/usr/local/sbin/mpf-mode"
    install -m 755 "$here/mpf-ro-check.sh" "$R/usr/local/sbin/mpf-ro-check"
    install -m 644 "$here/mpf-persist.service" "$R/etc/systemd/system/mpf-persist.service"
    ln -sf /etc/systemd/system/mpf-persist.service "$R/etc/systemd/system/local-fs.target.wants/mpf-persist.service"

    # configuration: the defaults with this image's user, boot mount and extra persistent folders
    local persist
    persist="$(sed -n 's/^MPF_PERSIST="\(.*\)"$/\1/p' "$here/mpf-readonly.conf.default") usersh:/home/$user/.ssh $extra"
    sed -e "s|^MPF_USER=.*|MPF_USER=$user|" -e "s|^MPF_BOOT_MOUNT=.*|MPF_BOOT_MOUNT=$boot|" \
        -e "s|^MPF_PERSIST=.*|MPF_PERSIST=\"$(echo $persist)\"|" "$here/mpf-readonly.conf.default" > "$R/etc/mpf-readonly.conf"
    [ -n "$volatile" ] && sed -i "s|^MPF_VOLATILE=\"\(.*\)\"\$|MPF_VOLATILE=\"\1 $volatile\"|" "$R/etc/mpf-readonly.conf"
    . "$R/etc/mpf-readonly.conf"

    # targets of the persistent binds must exist (a bind needs its mount point); drop the pairs the image does not have
    local keep="" pair target
    for pair in $MPF_PERSIST; do
        target="${pair#*:}"
        case "$pair" in usersh:*) install -d -m 700 "$R$target"; chroot "$R" chown "$user:$user" "$target" 2>/dev/null || true;; esac
        [ -e "$R$target" ] && keep="$keep $pair" || echo "readonly: $target is not in the image, not persistent"
    done
    sed -i "s|^MPF_PERSIST=.*|MPF_PERSIST=\"$(echo $keep)\"|" "$R/etc/mpf-readonly.conf"
    install -d "$R$MPF_DATA_MOUNT"

    # fstab: root and boot read-only, RAM disks for what is written all the time. The options are only appended: the last
    # one wins ("defaults,ro" is read-only). A kernel command line with ro (set by the platform) does the same for root.
    local fstab="$R/etc/fstab"
    touch "$fstab"
    sed -i -E 's@^(\S+\s+/\s+ext4\s+)(\S+)@\1\2,ro@' "$fstab"
    [ -n "$boot" ] && sed -i -E "s@^(\\S+\\s+${boot}\\s+vfat\\s+)(\\S+)@\\1\\2,ro@" "$fstab"
    local v path size mode
    for v in $MPF_VOLATILE; do
        path="${v%%:*}"; size="${v#*:}"; mode=0755
        case "$path" in /tmp|/var/tmp) mode=1777;; esac
        sed -i -E "\\@^tmpfs\\s+${path}\\s@d" "$fstab"
        printf 'tmpfs %s tmpfs nosuid,nodev,mode=%s,size=%s 0 0\n' "$path" "$mode" "$size" >> "$fstab"
        mkdir -p "$R$path"
    done

    # journal in RAM; no mail, logs or caches on the flash
    install -d "$R/etc/systemd/journald.conf.d" "$R/etc/tmpfiles.d" "$R/etc/profile.d"
    printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=16M\nForwardToSyslog=no\n' > "$R/etc/systemd/journald.conf.d/10-mpf-volatile.conf"
    printf 'd /var/log/mpf-game 0755 %s %s -\n' "$user" "$user" > "$R/etc/tmpfiles.d/mpf-game.conf"
    # no shell history; the X cookie in RAM (startx puts its server cookie in /tmp already)
    cat > "$R/etc/profile.d/mpf-readonly.sh" <<'PROF'
# read-only production mode (common/readonly): nothing is written to the home folder
export HISTFILE=/dev/null
export XAUTHORITY="/tmp/.Xauthority-$(id -un)"
PROF
    # the X server's log in RAM instead of /var/log/Xorg.0.log (startx runs this script)
    if [ -d "$R/etc/X11/xinit" ]; then
        printf '#!/bin/sh\n\nexec /usr/bin/X -nolisten tcp -logfile /tmp/Xorg.0.log "$@"\n' > "$R/etc/X11/xinit/xserverrc"
        chmod 755 "$R/etc/X11/xinit/xserverrc"
    fi
    # stable DHCP identity without a writable /etc/machine-id (the lease of a cabinet must not change at every boot)
    local f
    for f in "$R"/etc/systemd/network/*.network; do
        [ -e "$f" ] || continue
        install -d "$f.d"
        printf '[DHCPv4]\nClientIdentifier=mac\n' > "$f.d/10-mpf-mac.conf"
    done
    # jobs that write to the root file system
    local u
    for u in apt-daily.timer apt-daily-upgrade.timer apt-daily.service apt-daily-upgrade.service dpkg-db-backup.timer \
             e2scrub_all.timer e2scrub_reap.service man-db.timer logrotate.timer alsa-restore.service alsa-state.service; do
        if [ -e "$R/lib/systemd/system/$u" ] || [ -e "$R/usr/lib/systemd/system/$u" ]; then ln -sf /dev/null "$R/etc/systemd/system/$u"; fi
    done
    echo "readonly: root and ${boot:-no boot partition} read-only, persistent: $(grep '^MPF_PERSIST=' "$R/etc/mpf-readonly.conf")"
}
