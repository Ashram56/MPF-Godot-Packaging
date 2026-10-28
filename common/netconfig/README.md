# netconfig: Wi-Fi, SSH, games and a setup page for the MPF images

Shared by every image (Raspberry Pi 4, Jetson Xavier NX, x86 mini PC). Standard library Python, no dependencies besides
`iw`, `openssl` (always there) and `hostapd` + `dnsmasq` (fallback access point only).

| File | Role |
|---|---|
| `mpf-network.txt.template` | Text file the user edits (SSID, password, country, SSH key, mode). Lives where the image can be mounted from Windows/macOS: the FAT boot partition |
| `mpf_netconfig.py` | Entry point and network side. `apply` (read the file at boot; the Wi-Fi password is erased from it afterwards), `web` (setup page on port 8080), `ap` (access point `MPF-Setup`, password `mpf-setup`, page at http://192.168.4.1:8080 when no network came up in 90 s), `game` (what `mpf-game.service` runs), `inbox` (install what is waiting in the inbox) |
| `mpf_common.py` | Settings read from the environment and `/etc/mpf-readonly.conf`, the writable-window helper for read-only mode |
| `mpf_games.py` | Everything about games: install, versions, the active game, PuP Packs, settings, start and stop, the inbox |
| `mpf_monitor.py` | Switch monitor (BCP client of the running game) and saved log snapshots |
| `mpf_ota.py` | Updates of games and PuP Packs from a WebDAV folder (list, download, install; address, user and password kept in `ota.json`, mode 0600) |
| `mpf_web.py` | The page (one HTML file, English and French) and its HTTP routes |
| `mpf-netconfig-*.service`, `mpf-game.service` | systemd units: apply, web, ap, inbox, and the game |

The page listens on every interface, so it works over Ethernet too (Wi-Fi can be set up from a wired machine); it asks for the password of the image user (or `WEB_PASSWORD` from the file). Per-image settings go in
`/etc/default/mpf-netconfig`: `MPF_NETCONFIG_FILE`, `MPF_USER`, `MPF_WLAN`, `MPF_WEB_PORT`, `MPF_AP_PSK`, `MPF_AP_DELAY`.
Install (what each platform's `build-native.sh` does): copy every `mpf_*.py` to `/usr/local/bin/` (they import each other), the
units to `/etc/systemd/system/`, enable `mpf-netconfig-apply`, `-web`, `-ap`, `-inbox` (and `mpf-game` where the game starts at power-on),
copy the template to the configured path as `mpf-network.txt`.

## The page

One screen, in the browser's language (English or French, a selector at the top), with cards that show only what applies:

- **Status**: addresses, Wi-Fi network and signal, free space, mode (production or maintenance), the game running or not.
- **Games**: every installed game and version with its name, version, size, the active one marked; *Activate at startup*, *Delete*, and the
  upload of a new bundle or of a PuP Pack for the selected game. Start, stop, restart, start at power-on, the last lines of the log.
- **Settings** of the active game, built from the bundle's own settings schema (`options.tool`, `options.schema`).
- **Wi-Fi**: the networks in range (tap to choose), password, country. **SSH**: a public key, password logins on or off.
- **Mode**: production or maintenance ([common/readonly](../readonly/README.md)).

## Games: several versions, several games

`mpf_games.py` keeps every game in its own folder `MPF_GAMES_DIR/<id>@<version>` and one of them is the **active game** (the one
`mpf-game.service` starts and the page configures). Installing a bundle never overwrites another version:

- a new version of an installed game inherits the old one's settings, scores and PuP Pack (`keep_on_update` paths; the Pack and its media
  are hard-linked, so there is one copy on the disk), and the old version stays playable: choose it again on the page to go back;
- an update of the *active* game becomes the active one; a *different* game waits to be chosen on the page (the first game on an empty
  image is active at once);
- the same version again replaces itself (keeping what `keep_on_update` lists);
- a game with no PuP Pack is a game whose bundle has no `pup` section; a game with another Pack is another game or version with its own.

The bundle format and what a game may rely on are in [common/games/README.md](../games/README.md): that file is the contract.
Games are checked before anything is written (format, `target.arch`, the optional `.sha256` of the archive, `sha256sum -c SHA256SUMS`),
streamed to `MPF_UPLOAD_DIR`, never held in memory. `MPF_GOZEN_SO` replaces a bundle's arm64 GoZen with the board's own, unless the
bundle's build already carries `MPF_GOZEN_NEEDS` (default `v4l2m2m zero_copy`, from `bundle.json` `gozen`). After the first-run defaults,
the bundle's board profile is applied (`bundle.json` `profiles.apply`: the bundle picks its profile from the device tree and sets only what
nobody set, once).

`/etc/default/mpf-game` holds what the base system gives a game: `GODOT`, `MPF_GAME_VENV` (the Python environment with MPF), `DISPLAY`,
`XAUTHORITY` and `MPF_GAME_ARGS` (Pi 4: `-- --rendering-driver opengl3`). A bundle names the variables it reads under `requires.env`
(a name ending in `VENV` receives the venv folder).

### The inbox: games installed at boot

Files in `MPF_INBOX_DIR` (`/data/inbox` in read-only mode) are installed by `mpf-netconfig-inbox.service` before the game starts, then
removed. This is how [common/games/inject_image.py](../games/inject_image.py) puts games in an image before it is flashed, and how
you can drop a file from SSH without the page:

| File | Installed as |
|---|---|
| `*.tar.xz` (+ optional `*.tar.xz.sha256`) | a game bundle, in name order (the first one of an empty image becomes the active game) |
| `<id>.pup.zip` or `<id>@<version>.pup.zip` | the PuP Pack of that game (its active or newest version when only the id is given) |
| any other `*.zip` | the PuP Pack of the active game |

A file that fails goes to `inbox/failed/` with a `.log` that says why; the page's status shows the last job.

## Read-only production mode

On an image built with the read-only mode ([common/readonly](../readonly/README.md), `/etc/mpf-readonly.conf` exists) the page shows a *Mode*
section (production or maintenance), uploads go to the data partition, the game's `logs/` and Godot's user folders to RAM,
the Wi-Fi password is erased from `mpf-network.txt` in a short writable window of the boot partition, and `MODE=maintenance|production`
in that file switches the mode at the next boot. Without that file nothing changes.

## Platform limits

A board has limits a game must respect, and they live in the bundle's board profile (applied once at install by the step
above), not in the setup page: the profile sets the board's only allowed choices, so the page cannot offer more. On a
Raspberry Pi 4 the DMD is an external panel or the 256x64 colour dots over the backglass, never the HD vector mode
([platforms/raspberrypi.md](../../platforms/raspberrypi.md), "Platform limits"). Record each new limit there with its
measurement, and in the game's profile.

## Updates from a WebDAV server (*Updates* card)

Type the folder's address, user and password once (kept on this machine only, in `ota.json` of the state folder, never shown again;
an empty password field keeps the saved one; redirects are refused). *Check for updates* lists the bundles (`*.tar.xz`, with a
`.sha256` beside) and PuP Packs in the folder and its sub-folders; *Install* downloads one and installs it exactly like an upload.
The list says *installed* or *changed on the server* (size or date differ from what was installed). The engine itself (the base
system) is not updated this way yet.

## Configuration tab: switch monitor and saved logs

The page has three tabs (*Games*, *Install and updates*, *Configuration*; the address keeps the tab: `#config`).

- **Switch monitor** (*Configuration > Diagnostics*): the machine's switches live, lit when active, from MPF's own BCP server for outside
  clients (`127.0.0.1:5051`, the one MPF Monitor uses; `MPF_BCP_HOST` / `MPF_BCP_PORT` change it). A click flips a switch or taps it
  (a 150 ms pulse), as chosen. The game must be running; the connection exists only while the monitor is open.
- **Save the game log**: writes one text file (machine state, journal of the game and of this page, the game's log files, latest switch
  changes) to `/data/logs` (`/var/lib/mpf-logs` on an ordinary image, `MPF_SAVED_LOGS_DIR`), keeps the latest 20, and lists them for
  download. In read-only mode the live logs are in RAM, so this is the way to keep them for someone who debugs the machine.
