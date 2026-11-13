#!/usr/bin/env bash
# Game computer side of the USB link to the topper Pi Zero W (platforms/raspberrypi/zero/README.md, "USB link"):
# gives the USB Ethernet port the Zero shows (fixed MAC 02:70:75:70:00:01) the address 10.55.0.1/24, the Zero being 10.55.0.2.
# Run once as root on the game computer (a Raspberry Pi, a mini PC...): sudo bash usb-link-host.sh   (--uninstall removes it)
# NetworkManager if the computer has it, else systemd-networkd. No gateway, no DHCP, no routing: the link only carries the topper.
set -euo pipefail
MAC=02:70:75:70:00:01
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
NM=/etc/NetworkManager/system-connections/pup-topper-usb.nmconnection
NET=/etc/systemd/network/50-pup-topper-usb.network
if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$NM" "$NET"
    command -v nmcli >/dev/null && nmcli connection reload || true
    systemctl is-active -q systemd-networkd && networkctl reload || true
    echo "removed"; exit 0
fi
if command -v nmcli >/dev/null && systemctl is-active -q NetworkManager; then
    cat > "$NM" <<CONF
[connection]
id=pup-topper-usb
uuid=3f0d3b3e-7a5c-4a6e-9c27-5b1d5a7e0a01
type=ethernet
autoconnect=true

[ethernet]
mac-address=$MAC

[ipv4]
method=manual
address1=10.55.0.1/24
never-default=true

[ipv6]
method=disabled
CONF
    chmod 600 "$NM"; nmcli connection reload
    echo "NetworkManager profile pup-topper-usb written"
else
    mkdir -p /etc/systemd/network
    cat > "$NET" <<CONF
[Match]
MACAddress=$MAC

[Network]
Address=10.55.0.1/24
LinkLocalAddressing=no
IPv6AcceptRA=no
CONF
    systemctl enable --now systemd-networkd >/dev/null 2>&1 || true
    networkctl reload 2>/dev/null || systemctl restart systemd-networkd
    echo "systemd-networkd file $NET written"
fi
echo "Plug the Zero's micro-USB DATA port (the one nearest the middle) into a USB port of this computer; the topper is then 10.55.0.2."
