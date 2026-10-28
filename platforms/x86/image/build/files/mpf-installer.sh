#!/usr/bin/env bash
# Menu shown on the first console when the system runs from the USB stick (root label "rootfs"): pick an internal disk,
# type its name again, and mpf-install-to-disk copies the system to it. Also: sudo mpf-installer (over SSH).
set -u
[ "$(id -u)" = 0 ] || exec sudo "$0" "$@"
SRC_ROOT="$(findmnt -n -o SOURCE /)"; SRC_DISK="/dev/$(lsblk -no pkname "$SRC_ROOT" 2>/dev/null | head -1)"
while true; do
    clear
    echo "=== MPF: installation on the internal disk of this PC ==="
    echo "The system runs from the USB stick ($SRC_DISK). Disks that can receive it:"
    echo
    mapfile -t DISKS < <(lsblk -dpno NAME,TYPE | awk '$2=="disk" {print $1}' | grep -v "^$SRC_DISK$" | grep -v '/dev/\(zram\|loop\|sr\)')
    i=0
    for d in "${DISKS[@]}"; do
        i=$((i+1)); printf ' %d) %s\n' "$i" "$(lsblk -dpno NAME,SIZE,MODEL,TRAN "$d" | tr -s ' ')"
        lsblk -nlo NAME,SIZE,FSTYPE,LABEL "$d" | tail -n +2 | sed 's/^/      /'
    done
    [ "$i" -gt 0 ] || echo " (no other disk found: check the BIOS, then press r)"
    echo
    echo " r) rescan   s) shell   g) start the game session from the stick   p) power off"
    read -r -p "Number of the disk to ERASE and install on: " a
    case "$a" in
        r|R|"") continue;;
        s|S) echo "Type 'exit' to come back."; bash -l; continue;;
        g|G) exec su - mpf -c startx;;
        p|P) poweroff; exit 0;;
    esac
    case "$a" in *[!0-9]*) continue;; esac
    D="${DISKS[$((a-1))]:-}"; [ -n "$D" ] || continue
    if mpf-install-to-disk "$D"; then
        echo; read -r -p "Installed. Press Enter to power off, and remove the USB stick only once the PC is off... " _; poweroff; exit 0
    fi
    read -r -p "Installation failed or cancelled. Enter to go back to the menu... " _
done
