# Raspberry Pi 4

What a Raspberry Pi 4 needs to run an MPF + Godot game with PinUP videos, every setting with its reason and the
measurement behind it. Measured on the Tron Legacy cabinet, 24-26 Oct 2026: Raspberry Pi 4 Model B 4 GB (V3D 4.2),
Raspberry Pi OS (Debian 13), kernel 6.18.50+rpt-rpi-v8, X11 + openbox, one 1920x1080 screen on HDMI-2, sound on
the 3.5 mm jack. The files named below are in [raspberrypi/cabinet/](raspberrypi/cabinet/); the minimal image
([raspberrypi/image/](raspberrypi/image/README.md)) applies the ones that need neither a kernel build nor a patched Godot (table there); the codec module and the EGL-patched Godot are still to be added to it.

## Platform limits (decided by the owner, 2026-10-26)

A Raspberry Pi 4 shows the DMD in one of two ways, and nothing in between:

1. **An external DMD** (PIN2DMD, or ZeDMD; classic 128x32 or HD 256x64 dots, monochrome or Serum colour). No DMD on the
   screen, so the backglass window stays alone and page-flips.
2. **The DMD drawn over the backglass** (`[dmd] window="overlay"`), as **256x64 colour dots** (a game's "color256" mode:
   the colourisation's 256x64 pictures, the ROM's dot fonts), at a whole number of pixels per dot, not clipped.

Not on a Pi 4: the LCD DMD with vector text (HD) and the colourisation's pictures: it costs 45 points of CPU, a 50 s
start-up preload and twice the late frames (28.8 FPS, 7.7 % over 40 ms, 212 % CPU), and a separate DMD window, 3D light
cycles and a DMD at native 1080p are out of reach. A game's Pi 4 board profile must therefore install exactly these
settings and its setup page must offer only these two DMD choices on this board; other boards (PC, Jetson) keep all three
DMD pipelines (classic external, HD external, LCD).

## The limits

The GPU is the limit, then video decoding. 30 FPS steady is the target (the videos are 30 fps); 1080p rendering,
Vulkan and a second window are out of reach.

| Measured (Tron, 60-150 s runs, 30 FPS cap) | FPS | Frames > 40 ms | Pi CPU |
|---|---|---|---|
| backglass videos, no DMD | 29.5 | 3.7 % | 166 % |
| + classic dot DMD in the backglass window | 29.7 | 4.2 % | 168 % |
| + 256x64 colour dot DMD, 2x exact | 29.7 | 4.0 % | 168 % |
| + HD DMD (vector text, no glow), 512x128: **not offered on a Pi 4** | 28.7 | 7.2 % | 214 % (and a 50 s preload) |
| DMD at native 1080p (3x, 1920x1080 render) | 18.2 | 82 % | 145 % |

Not worth it: Vulkan (0.4-0.7 FPS, [fix](../fixes/godot/pi4-vulkan-freezes-with-video.md)), `v3d_freq=600` (no
gain), a 30 Hz mode (the EDID offers none).

## System (image)

| Setting | Where | Why |
|---|---|---|
| An EDID for a screen that sends none | `/lib/firmware/edid/<name>.bin`, cmdline `drm.edid_firmware=HDMI-A-2:edid/<name>.bin` | without EDID, vc4 refuses HDMI audio (-524) and guesses modes. Tron's: 1920x1080 at 60 Hz plus a CTA block with basic audio (LPCM 2 ch); only for such screens |
| `video=HDMI-A-2:1920x1080@60D video=HDMI-A-1:1920x1080@60D` | `/boot/firmware/cmdline.txt` | forced outputs; HDMI-1 always shows as connected, so X turns it off (next row) |
| `snd_bcm2835.enable_headphones=1` | cmdline | the device tree disables the jack's card |
| One X output: HDMI-2 primary at 1920x1080, HDMI-1 off | `~/.xinitrc` ([xinitrc](raspberrypi/cabinet/xinitrc)) | a second output costs a copy per frame |
| ALSA default = `plug` to `hw:CARD=Headphones` (no dmix) | `/etc/asound.conf` ([asound.conf](raspberrypi/cabinet/asound.conf)) | dmix stalls on snd_bcm2835 (hw_ptr stays 0); only the game plays sound |
| The owner's timezone | `timedatectl set-timezone` | the image's UTC shows in the game's clock |
| Fixed `bcm2835-codec` module | `/lib/modules/$(uname -r)/updates/bcm2835-codec.ko`, then `depmod` ([patch](raspberrypi/cabinet/bcm2835-codec-flush-completion.patch): three inverted completion tests) | the stock module oopses when a decoder closes with zero-copy. Built per kernel version, never on the Pi (cross-build); a kernel update brings the stock one back |
| Godot 4.6.3 with the EGL patch | the toolchain's Godot, `GODOT=` | official 4.6.3 crashes with `--render-thread separate` on GLES ([fix](../fixes/godot/gles-separate-render-thread-crash.md)) |
| Mouse cursor hidden | X with `-nocursor`, or `unclutter` | the cursor sat in the middle of the screen; the image starts X with `-nocursor` |

## The game service's environment

| Setting | Where | Why |
|---|---|---|
| `--rendering-driver opengl3 --render-thread separate --max-fps 30 --audio-output-latency 60` | `/etc/default/mpf-game` `MPF_GAME_ARGS` ([mpf-game.env](raspberrypi/cabinet/mpf-game.env)) | Compatibility renderer; the render thread halves the main thread (49 % instead of ~90 %); [30 FPS](../fixes/godot/frame-cap-30.md) steady on a 60 Hz screen; [60 ms](../fixes/godot/alsa-output-latency.md): no underruns instead of ~6 a minute (cracks) |
| `GOZEN_HWDEC=1` | `/etc/default/mpf-netconfig` ([mpf-netconfig.env](raspberrypi/cabinet/mpf-netconfig.env)) | V4L2 hardware decoder + [zero-copy](../fixes/gde-gozen/v4l2m2m-zero-copy.md): 330 % to ~175 % CPU, video lag 0.7 s to none. Only with the fixed codec module |
| `GOZEN_AUDIO_LATENCY=0.087` | same | ALSA reports 0 latency while it holds 58-93 ms: videos ran 0.09 s ahead of their sound ([fix](../fixes/godot/alsa-output-latency.md)) |
| Game variables in `mpf-netconfig`, not `mpf-game` | `common/netconfig/mpf_netconfig.py` `game_exec` | it forwards only `GODOT` and the game's venv variable from `/etc/default/mpf-game` |

## The game's settings (board profile)

A game's bundle carries these as its Raspberry Pi 4 board profile (applied once at install by the setup page,
`board_profile()` in `common/netconfig/mpf_netconfig.py`). Tron's names in brackets.

| Setting | Value | Measured |
|---|---|---|
| backglass window | fullscreen, borderless, render size 1280x720 | one page-flipped window; a 1080p render costs too much GPU |
| other screens (topper) | off (`[pup] third_screen=false`) | each window costs |
| DMD | drawn in the backglass window (`[dmd] window="overlay"`), or on a real panel (PIN2DMD, ZeDMD); never its own window | its own window: 21 instead of 29.6 FPS (X copies the fullscreen window, no page flip) |
| DMD background | none (`[dmd] background="none"`) | 3D light cycles: 10 FPS |
| DMD rounded corners | a panel behind, not clipped (`corner_clip=false`) | [clip_children](../fixes/godot/clip-children-slow-v3d.md): +20 points of GPU, 3x the late frames |
| DMD size | a whole number of render pixels per dot (`view_size=[512, 128]`, nearest filter) | non-integer scaling: moiré |
| DMD mode | 256x64 colour dots (`color256`), or an external panel; never the LCD/HD vector mode | see the platform limits above |

## Sound and picture in sync

Over 2.5 h of attract the frame chosen stayed within 0.00 to -0.13 s of its sound across 33 plays of a 2.5 min
trailer, with no trend; the jack's clock runs +15 ppm. What reaches the screen with zero-copy was not measured.
