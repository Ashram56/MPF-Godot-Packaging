#!/bin/sh
# Install a web package by hand (the page's own update card does the same, step 3 of the plan).
#   sudo sh install_web_package.sh mpf-web-<id>.tar.xz
# Verifies the .sha256 beside it, unpacks under $MPF_WEB_DIR (default /data/platform), points `current` at it, restarts the page.
# The data partition is writable in production mode: no maintenance window needed. Roll back: ln -sfn <older id> current.
set -e
[ "$(id -u)" = 0 ] || { echo "run it with sudo"; exit 1; }
A=$1; [ -f "$A" ] || { echo "usage: $0 mpf-web-<id>.tar.xz"; exit 1; }
D=${MPF_WEB_DIR:-/data/platform}
[ -f "$A.sha256" ] && (cd "$(dirname "$A")" && sha256sum -c "$(basename "$A").sha256")
mkdir -p "$D"
ID=$(tar -tf "$A" | head -1 | cut -d/ -f1)
tar -xf "$A" -C "$D"
ln -sfn "$D/$ID" "$D/current.new" && mv -T "$D/current.new" "$D/current"
systemctl restart mpf-netconfig-web.service
sleep 2
systemctl is-active mpf-netconfig-web.service
journalctl -u mpf-netconfig-web -n 3 --no-pager | grep mpf_launch || true
