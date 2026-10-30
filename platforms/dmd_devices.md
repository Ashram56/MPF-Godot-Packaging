# RGB LED DMDs: PIN2DMD and ZeDMD

A GMC game can show its 128x32 DMD on a PIN2DMD or a ZeDMD as well as (or instead of) the screen. GMC does not
need a screen for this: Godot reads back its own picture and sends it on. Worked example: a Stern SAM recreation
(`docs/hardware.md`, "PIN2DMD" and "ZeDMD"), where these pieces were written. **Neither device has been tried on real
hardware yet**: the packets follow libdmdutil's and libzedmd's source, checked in tests against fake devices.

| Piece | What |
|---|---|
| `addons/dmd_out/dmd_out.gd` | Godot autoload. With the user arg `--pin2dmd[=#RRGGBB]` or `--zedmd[=#RRGGBB]` it sends each changed frame (up to 30 a second) to MPF as a 12288-byte RGB `rgb_dmd_frame` named `default`; with `--zedmd-feed=PATH` as well, it starts the native feeder and pipes the frames to it instead. Monochrome: each dot's brightness (16 shades) scales one colour, default `#ff730d`. Inert without the args. |
| `examples/dmd_devices/pin2dmd.yaml` | MPF overlay for MPF 0.80.1's own `pin2dmd` platform (pyusb, USB `0314:e457`): `hardware: rgb_dmd: pin2dmd`, `pin2dmd: resolution 128x32, panel rgb`, `rgb_dmds: default`. |
| `examples/dmd_devices/zedmd.yaml` | MPF overlay for `mpf_godot/zedmd_native.py` (pyserial, the ZeDMD serial protocol), in place of MPF's `zedmd` platform, which does not load everywhere (`fixes/mpf/zedmd-native-serial.md`). |
| `examples/dmd_devices/zedmd_feed.yaml` | MPF overlay when the native feeder drives the ZeDMD: MPF only moves the original DMD to the virtual platform. |
| `native/zedmd_feed/zedmd_feed.c` | The feeder: C, libc only, Linux and macOS. Reads 128x32 RGB frames on stdin, sends the newest one; `--probe` says whether a ZeDMD answers (exit 2 if none). |
| `mpf_godot/zedmd_native.py` | The pyserial platform (921600 baud, 115200 on the ESP32-S3's own USB; port by USB id or `ZEDMD_PORT`). |

## Set-up

1. In the venv: `pip install pyusb` (PIN2DMD) or `pip install pyserial` (ZeDMD). The PIN2DMD also needs libusb 1.0,
   and on Linux a udev rule to run without root:
   `SUBSYSTEM=="usb", ATTR{idVendor}=="0314", ATTR{idProduct}=="e457", MODE="0666"`.
2. Copy `addons/dmd_out/` into the game's Godot project and add `dmd_out.gd` as an autoload (after GMC's `MPF`).
3. Copy the overlay you need into the game's `config/` and give it after the hardware config:
   `mpf game . -c config,pin2dmd` or `-c config,zedmd`. For `zedmd.yaml`, MPF must import `mpf_godot`: put this
   repository's root on `PYTHONPATH` (or copy `zedmd_native.py` into the game and change the platform path).
4. Start Godot with the matching user arg: `godot --path GAME -- --pin2dmd` (or `--zedmd`, `--zedmd=#2a6cff`).

The native feeder (no MPF, no BCP, no Python in the frame path; lighter on a Raspberry Pi):

```sh
cc -O2 -o zedmd_feed native/zedmd_feed/zedmd_feed.c      # on the build box, not on a Pi
./zedmd_feed --probe                                      # exit 0: a ZeDMD answered
godot --path GAME -- --zedmd --zedmd-feed=$PWD/zedmd_feed # MPF with examples/dmd_devices/zedmd_feed.yaml
```

## Findings

1. The DMD must be the exact 128x32 picture: an HD or smoothed DMD read back and shrunk gives blurred dots. A game
   with an HD mode should switch it off when one of these args is given (a game's `dmd_mode.gd` may force its classic mode).
2. MPF's `pin2dmd` platform accepts only the `rgb_dmds` device named `default`. MPF stops with "Pin2Dmd USB device not
   found" when the PIN2DMD is missing or another program (DMDext) holds it.
3. On a P-ROC machine, a P-ROC DMD and an LED DMD together are not supported: the overlays move `dmds: dmd` to the
   virtual platform, and the game must not also send `--proc-dmd`-style frames.
4. To check on hardware: the PIN2DMD's colour order (`panel: rbg` swaps green and blue) and its firmware's "virtual
   pinball" mode; the ZeDMD's port, firmware 5.x, colour order, and the brightness command's payload (a guess).
5. Colour pictures (a colourisation) are out of scope here: this add-on only ever sends one colour scaled by
   brightness.

## Choosing the device

Which display a machine uses (a PIN2DMD, a ZeDMD, or the screen) depends on the board and on what is plugged in, not
on the game, so the platform decides it:

```sh
python -m mpf_godot dmd-detect        # prints pin2dmd, zedmd, or nothing
python -m mpf_godot addons GAME --dmd # copies addons/dmd_out into the game (add it as an autoload)
```

A PIN2DMD counts when its USB id (0314:e457) is on the bus; a ZeDMD only when it answers the handshake on its USB serial
port (the ESP32's own USB 303a:1001, or a CH340 / CP210x bridge, ids other boards share). Linux only (sysfs); a ZeDMD on
Wi-Fi is not looked for. A game's launcher runs `dmd-detect` at start and, if it names a device, starts Godot with
`--pin2dmd` / `--zedmd` and MPF with the matching overlay; a choice made by the player (the setup page's "DMD display")
wins over detection. The game itself only has to keep its DMD classic 128x32 when one of these args is present.

## Sizes and pictures a game can publish

A game can offer more than the classic dots. In Godot it calls `get_node("/root/dmd_out").publish("hd", viewport)` (any name;
`classic`, the root viewport, is the default) and the machine's launcher starts Godot with the device's size and the picture
it wants:

| Device | `resolution` / size arg | Picture |
|---|---|---|
| ZeDMD, PIN2DMD | `128x32` (default) | `classic`: the exact dots, 16 shades |
| PIN2DMD XL | `192x64`, `--dmd-size=192x64` | any published picture, Lanczos to size, 8 bits |
| PIN2DMD HD, ZeDMD HD | `256x64`, `--dmd-size=256x64` | e.g. `--dmd-feed=256x64` or `hd` |

MPF's pin2dmd platform takes 128x32, 192x64 and 256x64. The native ZeDMD feeder is 128x32 only. Colour stays the game's
business: without it the add-on sends one colour scaled by brightness. Not run on a device.

## Colourising a game's DMD (the game's job)

The DMD is part of the game, so a colourisation (Serum or any other) belongs to the game, not to this platform. `zedmd_feed` stays the plain feeder: 12288-byte RGB frames of 128x32 on stdin, nothing else. A game puts its own colouriser in front of it: a program the game builds, that reads the add-on's frames (`--zedmd-feed=PROGRAM`), colours them and pipes RGB frames to the `zedmd_feed` it starts itself. Tron Legacy's is `game/native/dmd_serum` (libserum, GPL v2; Tron-Legacy-MPF docs/hardware.md, "Serum colour on a ZeDMD"). Like every native tool, it is built offline per CPU with the game's bundle; nothing is compiled on the machine that plays.
