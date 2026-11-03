# The platform in a Docker container (test a game on a PC or a Mac)

One container with what a cabinet image runs, without the cabinet: the **setup page** (port 8080: install a game bundle from the
WebDAV share or a file, PuP Packs, Serum files, DMD output, settings, Monitor, scenarios), the **game's window in a browser** (port
6080, noVNC), Godot on **software Vulkan** (Mesa lavapipe) and **software video decoding** (GoZen / FFmpeg): no GPU, no driver, no USB
device. It uses the same code as the images (`common/netconfig/`, `mpf_godot/`, `native/`); only systemd is replaced by two small
scripts. Back to [all platforms](../platforms/README.md).

## Use

Docker Desktop (Windows, macOS) or Docker Engine (Linux), then from this repository:

```sh
docker compose up --build            # first build: 10 to 20 minutes (MPF, Godot, GMC, libzedmd, libserum)
```

| What | Where |
|---|---|
| Setup page | http://localhost:8080 (any user name, password `mpf`, or `MPF_WEB_PASSWORD`) |
| The game's window | http://localhost:6080/vnc.html?autoconnect=1&resize=scale |
| DMD preview on the page | Configuration > DMD output > **web** (the pictures a ZeDMD would get, Serum colour included) |

1. Open the setup page, **Install** a game bundle (the share's `.tar.xz` URL, or upload the file). The page checks and installs it as on
   a cabinet; the game starts with the container once installed (`MPF_AUTOSTART=0`: with the page's Start button only).
2. Watch it in the browser tab of port 6080. Keys and mouse go to the game's window.
3. Everything lives in the volume `mpf-data` (`/data`: games, settings, PuP Packs, Serum files, scores): `docker compose down` keeps it,
   `docker compose down -v` erases it.

Options (environment or a `.env` file beside `docker-compose.yml`): `MPF_WEB_PASSWORD`, `MPF_BIND` (default `127.0.0.1`: the ports
are reachable from this computer only; `0.0.0.0` opens them to the network, set a password first), `MPF_SCREEN` (`1280x720x24`),
`MPF_AUTOSTART`. Without compose:

```sh
docker build -f docker/Dockerfile -t mpf-godot .
docker run --rm -p 127.0.0.1:8080:8080 -p 127.0.0.1:6080:6080 --shm-size 1g -v mpf-data:/data mpf-godot
```

## What differs from a cabinet

- **Board `x86`** (`MPF_BOARD`; `MPF_BOARD=rpi4` shows a game as a Raspberry Pi 4 would run it, its profile's limits included).
  On a Mac with Apple silicon the image is built for arm64 (Docker runs it natively): same code, board `x86` profile; set
  `MPF_BOARD=arm64` if a bundle has such a profile.
- **Software rendering and decoding**: slower than a GPU, enough for a recent PC (lower the game's frame rate or resolution in its
  settings otherwise). No frame-rate figure here is a cabinet's.
- **No sound** (Godot's dummy audio driver), no Wi-Fi, no read-only mode, no OS update: those tiles of the page do nothing useful.
- **No ZeDMD or PIN2DMD** over USB (Docker Desktop does not pass USB devices); the `web` output shows what they would get. For a real
  ZeDMD on a PC or a Mac use the [local platform](../platforms/local.md).
- `systemctl`/`journalctl` are `docker/systemctl` and `docker/journalctl`: they handle `mpf-game.service` (start, stop, restart, status,
  autostart; the log is `/var/log/mpf-game/service.log`) and `reboot` restarts the container.

## Files

| File | Role |
|---|---|
| `Dockerfile` | stage 1 builds `dmd_bridge` (libzedmd, libserum unmodified); stage 2: Python 3.11, Xvfb, x11vnc, noVNC, Mesa Vulkan, then `python -m mpf_godot setup --no-monitor` |
| `entrypoint.sh` | PID 1: Xvfb, VNC, noVNC, the setup page, the game |
| `mpf-game-run` | `Restart=always` of `mpf-game.service` |
| `systemctl`, `journalctl` | stand-ins for the two commands the page's code calls |
| `../docker-compose.yml` | ports, volume, options |

## Checked (2026-11-03, cloud sandbox, Linux x86_64)

- The image builds (about 10 minutes), the setup page answers on 8080 behind its password, noVNC on 6080.
- Godot 4.6.3 draws on Mesa lavapipe ("Vulkan 1.3, Forward Mobile, llvmpipe"), GMC listens, MPF reaches attract mode.
- A format 2 bundle made with `common/games/make_bundle.py` from `examples/minimal` was installed through the inbox, started and stopped
  with the stand-in `systemctl`; the game runs as the `mpf` user.
- `tests/test_docker.py`.

**Not checked**: a real game bundle (Tron, Transformers), the DMD `web` preview with a Serum file, the frame rate on a PC, Docker
Desktop on Windows and macOS (Apple silicon builds for arm64).
