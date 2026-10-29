#!/bin/sh
# Update the setup page of a machine that is already running, without rebuilding the image.
#   sudo sh update_page.sh            (from a folder holding the mpf_*.py files, e.g. common/netconfig of a clone)
# Copies mpf_*.py to /usr/local/bin and restarts the page. On a production (read-only) image the system is made writable
# for the copy and back to read-only after; the page restarts either way. The game keeps running.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
[ "$(id -u)" = 0 ] || { echo "run it with sudo"; exit 1; }
ls "$HERE"/mpf_web.py >/dev/null
RO=0
if command -v mpf-mode >/dev/null 2>&1 && mount | grep -q ' / .*[(,]ro[,)]'; then RO=1; mpf-mode maintenance --stay; fi
for f in "$HERE"/mpf_*.py; do install -m 0755 "$f" /usr/local/bin/; done
[ "$RO" = 1 ] && mpf-mode production || true
systemctl restart mpf-netconfig-web.service
sleep 2
systemctl is-active mpf-netconfig-web.service
