# The platform in a container, to test any game bundle on a PC or a Mac without a cabinet: the same setup page (port 8080) and the same
# start code as the images, software video decoding (no GPU needed), the game's window in a browser (noVNC, port 6080).
# docker/README.md has the commands. Build from the repository root:   docker build -f docker/Dockerfile -t mpf-godot .
ARG PYTHON_IMAGE=python:3.11-slim-trixie

# ---- the DMD bridge (unmodified libzedmd and libserum, for the page's "web" DMD output and the Serum colour)
FROM ${PYTHON_IMAGE} AS bridge
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl cmake make g++ autoconf automake libtool \
        pkg-config patch xz-utils libusb-1.0-0-dev && rm -rf /var/lib/apt/lists/*
COPY native /src/native
RUN set -e; out=/opt/dmd_bridge; mkdir -p $out/lib /tmp/z /tmp/s \
 && bash /src/native/libzedmd/build_libzedmd.sh /tmp/z >/dev/null \
 && bash /src/native/dmd_bridge/build.sh /tmp/z /tmp/z >/dev/null \
 && cp /tmp/z/dmd_bridge $out/ && cp -a /tmp/z/lib/. $out/lib/ \
 && bash /src/native/serum/build_libserum.sh /tmp/s >/dev/null \
 && cp /tmp/s/libserum*.so* $out/; ls -R $out | head -30

# ---- the platform
FROM ${PYTHON_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive
# gcc: on arm64 (Mac Apple silicon) a Python dependency of MPF without a wheel is compiled by pip.
# Xvfb + x11vnc + noVNC: the game's window in a browser (xrandr, for the page's screen list); mesa's software Vulkan (lavapipe) for Godot's mobile renderer; the libraries ffmpeg grabs the windows for the page's cabinet preview (x11grab on Xvfb :0); alsa-utils for arecord.
# Godot's official build and GoZen (FFmpeg, software decoding) load.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl unzip xz-utils procps iproute2 openssl gcc libc6-dev \
        xvfb xauth x11-xserver-utils x11vnc novnc websockify ffmpeg alsa-utils pulseaudio pulseaudio-utils \
        mesa-vulkan-drivers libvulkan1 libgl1 libegl1 libxcursor1 libxinerama1 libxi6 libxrandr2 libxkbcommon0 libxkbcommon-x11-0 \
        libfontconfig1 libdbus-1-3 libudev1 libasound2 libpulse0 libusb-1.0-0 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 -s /bin/bash mpf
COPY . /opt/MPF-Godot
WORKDIR /opt/MPF-Godot
# MPF, the patched GMC and Godot, with the installer the other platforms use (no MPF Monitor: the page has its own)
RUN python -m mpf_godot setup --no-monitor && rm -rf /root/.cache && chown -R mpf:mpf /opt/MPF-Godot
COPY --from=bridge /opt/dmd_bridge /opt/dmd_bridge
# PulseAudio runs as its own user: stopping the game (pkill -u mpf in docker/systemctl) must not stop the sound
RUN useradd -r -m -d /run/pulse-home -s /usr/sbin/nologin mpfpulse \
 && install -m 755 docker/systemctl docker/journalctl docker/mpf-game-run /usr/local/bin/ \
 && install -m 755 common/netconfig/mpf_netconfig.py /usr/local/bin/mpf_netconfig.py \
 && cp common/netconfig/*.py /usr/local/bin/ \
 && python - <<'PY'
import os, sys
sys.path.insert(0, "/opt/MPF-Godot")
from mpf_godot import toolchain as tc
open("/etc/default/mpf-game", "w").write(
    'GODOT=%s\nMPF_GAME_VENV=%s\nDISPLAY=:0\n' % (tc.godot_path(), tc.venv_dir()))
PY
ENV MPF_USER=mpf MPF_PLATFORM_DIR=/opt/MPF-Godot MPF_DMD_BRIDGE_DIR=/opt/dmd_bridge MPF_BOARD=x86 \
    MPF_NETCONFIG_FILE=/data/mpf-network.txt MPF_GAMES_DIR=/data/games MPF_STATE_DIR=/data/state MPF_UPLOAD_DIR=/data/uploads \
    MPF_PUP_DIR=/data/pups MPF_INBOX_DIR=/data/inbox MPF_SERUM_DIR=/data/serum MPF_GOZEN_NEEDS="" \
    LIBGL_ALWAYS_SOFTWARE=1 MPF_SCREEN=1280x720x24
VOLUME /data
EXPOSE 8080 6080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD curl -fs -o /dev/null -m 4 http://127.0.0.1:8080/ || exit 1
ENTRYPOINT ["/opt/MPF-Godot/docker/entrypoint.sh"]
