# netconfig: Wi-Fi, SSH and a setup page for the MPF images

Shared by the Raspberry Pi 4 and Jetson Xavier NX images. Standard library Python, no dependencies besides
`iw`, `openssl` (always there) and `hostapd` + `dnsmasq` (fallback access point only).

| File | Role |
|---|---|
| `mpf-network.txt.template` | Text file the user edits (SSID, password, country, SSH key). Lives where the image can be mounted from Windows/macOS: the FAT boot partition |
| `mpf_netconfig.py` | `apply` (read the file at boot; the Wi-Fi password is erased from it afterwards), `web` (setup page on port 8080), `ap` (access point `MPF-Setup`, password `mpf-setup`, page at http://192.168.4.1:8080 when no network came up in 90 s) |
| `mpf-netconfig-*.service` | systemd units for the three modes |

The page listens on every interface, so it works over Ethernet too (Wi-Fi can be set up from a wired machine); it asks for the password of the image user (or `WEB_PASSWORD` from the file). Per-image settings go in
`/etc/default/mpf-netconfig`: `MPF_NETCONFIG_FILE`, `MPF_USER`, `MPF_WLAN`, `MPF_WEB_PORT`, `MPF_AP_PSK`, `MPF_AP_DELAY`.
Install: copy the script to `/usr/local/bin/`, the units to `/etc/systemd/system/`, enable the three, copy the
template to the configured path as `mpf-network.txt`.

## Game bundle and PuP Pack upload

The page also installs a game bundle (`<name>-<version>-linux-<arch>.tar.xz`, or `-linux-all`: one universal bundle for every machine, both texture formats and no binary (`target.arch` `arm64+x86_64`; `platform_addons: ["gde_gozen"]` makes the page install this platform's own GoZen build for the machine, `MPF_PLATFORM_DIR`), format of Tron-Legacy-MPF `docs/bundle.md`) and an optional PuP Pack `.zip`.
Files are streamed to `MPF_UPLOAD_DIR`, never held in memory. The bundle is checked (format, `target.arch`, optional `.sha256` of the archive,
`sha256sum -c SHA256SUMS`), unpacked to `MPF_GAMES_DIR/<id>`; on an update the `keep_on_update` paths of the old install are carried over.
The pack is installed with the bundle's own `pup.install` command. The page then shows the bundle's settings (built from `options.json`,
written with `bundle_options.py`) and a Start/Stop button (transient unit `mpf-game`, `start.py`). `/etc/default/mpf-game` holds `GODOT`,
`TRON_VENV`, `DISPLAY`, `XAUTHORITY` and `MPF_GAME_ARGS` (Pi 4: `-- --rendering-driver opengl3`). `MPF_GOZEN_SO` replaces the bundle's arm64 GoZen with the board's own, unless the bundle's build already carries `MPF_GOZEN_NEEDS` (default `v4l2m2m zero_copy`, from `bundle.json` `gozen`). After the first-run defaults, the bundle's board profile is applied (`bundle.json` `profiles.apply`: the bundle picks its profile from the device tree and sets only what nobody set, once; Tron-Legacy-MPF `docs/bundle.md`, Board profiles).

## Platform limits

A board has limits a game must respect, and they live in the bundle's board profile (applied once at install by the step
above), not in the setup page: the profile sets the board's only allowed choices, so the page cannot offer more. On a
Raspberry Pi 4 the DMD is an external panel or the 256x64 colour dots over the backglass, never the HD vector mode
([platforms/raspberrypi.md](../../platforms/raspberrypi.md), "Platform limits"). Record each new limit there with its
measurement, and in the game's profile.

How a game builds a bundle for this page: [platforms/game-bundles.md](../../platforms/game-bundles.md).
