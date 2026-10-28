#!/usr/bin/env bash
# Install the remote topper on a Raspberry Pi (Raspberry Pi OS Lite, Bookworm): mpv, the agent, and a service
# that starts it at boot. Run it as the Pi's normal user (it uses sudo), from a clone of the repository:
#
#     bash mpf_godot/pup_remote/topper/install.sh
#
# or straight from GitHub, without a clone:
#
#     curl -fsSL https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/mpf_godot/pup_remote/topper/install.sh | bash
#
# Again to update; `bash install.sh --uninstall` removes it (the videos stay in ~/pup-topper/media).
# Then, on the game computer, the game copies its topper videos here (platforms/pup-remote-topper.md).
set -euo pipefail

REF="${PLATFORM_REF:-main}"
RAW="https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/$REF"
APP=/opt/pup-topper
CFG=/etc/pup-topper.cfg
UNIT=/etc/systemd/system/pup-topper.service
USER_NAME="$(id -un)"
MEDIA="$HOME/pup-topper/media"

if [ "$(id -u)" = 0 ]; then
    echo "Run this as the Pi's normal user, not root: it runs the topper as that user (and asks for sudo)." >&2
    exit 1
fi

if [ "${1:-}" = "--uninstall" ]; then
    sudo systemctl disable --now pup-topper 2>/dev/null || true
    sudo rm -rf "$APP" "$UNIT"
    sudo systemctl daemon-reload
    echo "Removed the topper service and $APP; kept $CFG and $MEDIA."
    exit 0
fi

echo "== mpv"
sudo apt-get update -qq
sudo apt-get install -y -qq mpv python3

echo "== the agent in $APP"
sudo mkdir -p "$APP"
HERE=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/topper.py" ]; then
    HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -n "$HERE" ]; then
    # from a clone: the agent, and the PuP rules it shares with the game
    sudo cp "$HERE/topper.py" "$HERE/pup-topper.cfg" "$APP/"
    sudo cp "$HERE/../../mpf_godot/pup_remote/screen_rules.py" "$APP/"
else
    for f in mpf_godot/pup_remote/topper/topper.py mpf_godot/pup_remote/topper/pup-topper.cfg mpf_godot/pup_remote/screen_rules.py; do
        sudo curl -fsSL "$RAW/$f" -o "$APP/$(basename "$f")"
    done
fi

echo "== settings in $CFG"
if [ ! -f "$CFG" ]; then
    sed "s#^media=.*#media=$MEDIA#" "$APP/pup-topper.cfg" | sudo tee "$CFG" > /dev/null
else
    echo "kept the existing $CFG"
fi
mkdir -p "$MEDIA"

echo "== the service (user $USER_NAME)"
# video and render: the screen and the hardware decoder without a desktop
sudo usermod -a -G video,render "$USER_NAME"
sudo tee "$UNIT" > /dev/null <<EOF
[Unit]
Description=PuP topper (PuP screens 13 and 14 from the game)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
SupplementaryGroups=video render
ExecStart=/usr/bin/python3 $APP/topper.py --config $CFG
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable pup-topper
sudo systemctl restart pup-topper

echo
echo "Done. The topper starts at boot and finds the game on the network."
echo "Next, on the game computer:"
echo "  1. turn the game's remote PuP screens on (platforms/pup-remote-topper.md)"
echo "  2. copy the topper videos to $USER_NAME@$(hostname).local (the game's topper media tool)"
echo "Its log: journalctl -u pup-topper -f    Settings: sudo nano $CFG, then sudo systemctl restart pup-topper"
