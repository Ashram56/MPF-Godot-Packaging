#!/bin/sh
# After a game bundle is installed on a machine: does it really run? A package that "checks" can still crash in a loop at start.
#   check_installed.sh [SECONDS]      (default 60; run on the machine, as root or the game's user)
# Restarts the game service, waits, and says OK only if the service stayed up the whole time with no restart; otherwise prints
# the restart count and the last lines of the game's journal (the first error is what to read).
SECS=${1:-60}
UNIT=mpf-game.service
say() { printf '%s\n' "$*"; }
command -v systemctl >/dev/null 2>&1 || { say "no systemd here: start the game by hand and watch its output"; exit 2; }
active=$(ls -d /opt/games/*@* /data/persist/games/*@* 2>/dev/null | head -20)
say "installed games:"; say "$active"
say "active game: $(cat /var/lib/mpf-netconfig/active-game /data/mpf/active-game 2>/dev/null | head -1)"
systemctl restart "$UNIT" || { say "FAIL: the service did not restart"; exit 1; }
start=$(date +%s)
n0=$(systemctl show -p NRestarts --value "$UNIT")
while [ $(( $(date +%s) - start )) -lt "$SECS" ]; do
    st=$(systemctl is-active "$UNIT")
    n=$(systemctl show -p NRestarts --value "$UNIT")
    if [ "$st" != active ] || [ "$n" != "$n0" ]; then
        say "FAIL after $(( $(date +%s) - start )) s: service $st, restarts $n (was $n0)"
        journalctl -u "$UNIT" -n 40 --no-pager -o cat 2>/dev/null | tail -40
        exit 1
    fi
    sleep 2
done
say "OK: $UNIT stayed active for $SECS s with no restart"
for p in godot mpf; do pgrep -af "$p" >/dev/null 2>&1 && say "  running: $p"; done
