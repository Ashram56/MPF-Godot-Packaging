#!/usr/bin/env bash
# PID 1 of the container: the display (Xvfb), its view in a browser (x11vnc + noVNC, port 6080), the setup page (port 8080), and the game
# when one is installed and enabled. What systemd does on the images, docker/systemctl and docker/mpf-game-run do here.
set -u
DATA=/data
mkdir -p $DATA/games $DATA/state $DATA/uploads $DATA/pups $DATA/inbox $DATA/serum /run/mpf /var/log/mpf-game /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix; chown mpf:mpf $DATA /var/log/mpf-game
[ -f "$MPF_NETCONFIG_FILE" ] || printf 'WEB_PASSWORD=%s\n' "${MPF_WEB_PASSWORD:-mpf}" > "$MPF_NETCONFIG_FILE"
# first start: the game starts with the container (MPF_AUTOSTART=0 for the page's button only)
if [ ! -e $DATA/state/.container-init ]; then
    touch $DATA/state/.container-init
    [ "${MPF_AUTOSTART:-1}" = 0 ] || touch $DATA/state/game.enabled
fi

# software Vulkan (Mesa lavapipe); the file is named after the CPU (lvp_icd.x86_64.json, lvp_icd.aarch64.json)
export VK_ICD_FILENAMES=$(ls /usr/share/vulkan/icd.d/lvp_icd*.json | head -1)
# sound: a PulseAudio null sink (no sound card in a container); the game plays into it and the page's cabinet preview records its monitor
export PULSE_SERVER=unix:/tmp/pulse.sock MPF_PULSE_SINK=mpf
HOME=/run/pulse-home XDG_RUNTIME_DIR=/run/pulse-home runuser -u mpfpulse -- pulseaudio -n --exit-idle-time=-1 --daemonize=no --load="module-native-protocol-unix socket=/tmp/pulse.sock auth-anonymous=1" \
    --load="module-null-sink sink_name=mpf" >/var/log/pulseaudio.log 2>&1 & pulse_pid=$!
pids=($pulse_pid)
Xvfb :0 -screen 0 "${MPF_SCREEN:-1280x720x24}" -ac -nolisten tcp +extension GLX >/var/log/Xvfb.log 2>&1 & pids+=($!)
for _ in $(seq 50); do [ -S /tmp/.X11-unix/X0 ] && break; sleep 0.2; done
x11vnc -display :0 -forever -shared -nopw -localhost -rfbport 5900 -quiet -noxdamage >/var/log/x11vnc.log 2>&1 & pids+=($!)
websockify --web /usr/share/novnc 6080 127.0.0.1:5900 >/var/log/novnc.log 2>&1 & pids+=($!)
# the page runs through mpf_launch.py (a web package under /data/platform when there is one, else this image's copy) and is started again
# when it stops: the page's own update ("systemctl restart mpf-netconfig-web.service", see docker/systemctl) kills it to load the new version
( while :; do python3 /usr/local/bin/mpf_launch.py web; sleep 1; done ) >>/var/log/mpf-web.log 2>&1 & pids+=($!)

if systemctl is-enabled --quiet mpf-game.service && compgen -G "$MPF_GAMES_DIR/*/bundle.json" >/dev/null; then
    systemctl start --no-block mpf-game.service
fi
echo "MPF setup page: http://localhost:8080 (password: ${MPF_WEB_PASSWORD:-the one in $MPF_NETCONFIG_FILE})"
echo "Game screen:    http://localhost:6080/vnc.html?autoconnect=1&resize=scale"

stop() { systemctl stop mpf-game.service; kill "${pids[@]}" 2>/dev/null; pkill -f "mpf_.*py web" 2>/dev/null; exit 0; }
trap stop TERM INT
while sleep 5; do
    for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null || { echo "a service stopped (see /var/log in the container)" >&2; stop; }; done
done
