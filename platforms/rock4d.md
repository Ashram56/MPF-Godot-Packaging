# Radxa ROCK 4D (Rockchip RK3576)

Image: [rock4d/image/README.md](rock4d/image/README.md). Cabinet settings: [rock4d/cabinet](rock4d/cabinet).

## Hardware acceleration

| | How | Status |
|---|---|---|
| GPU | Mali-G52 MC3 (Bifrost) through the mainline `panfrost` kernel driver and Mesa (trixie) GL; Godot runs `--rendering-driver opengl3` (`cabinet/mpf-game.env`). No Vulkan (PanVK does not cover this GPU) | not run on the board |
| Video decoding | rkvdec (H.264, HEVC, VP9) through the stateless V4L2 request API. GoZen is built with FFmpeg 7.1 plus Kwiboo's V4L2-request hwaccel series (14 patches, [build/gozen/build_rock4d.sh](../build/gozen/build_rock4d.sh), `gozen_v4l2request.patch`): FFmpeg decodes in the VPU, frames come out as DRM PRIME buffers and are copied to memory as NV12 (`_hw_download`), as for VAAPI on x86. Software fallback when the device or the video is refused | cross-built and loaded checks only; **never run on the board** |
| Display / HDMI | mainline `rockchipdrm` VOP2 + DW HDMI QP | not run on the board |

`GOZEN_HWDEC=1` (default in `/etc/default/mpf-netconfig`; `0` = software, `v4l2request` = this decoder only),
`GOZEN_V4L2REQUEST_DEVICE=/dev/mediaN` names the media node when the probe picks the wrong one.
Only the GoZen build of the image has the decoder: a game bundle's own GoZen is replaced by it (`MPF_GOZEN_SO`).

**Known fault: wrong pictures from rkvdec (cause known upstream, 2026-11-20, kernel 7.2.12).** About 30-40 % of the power-ups of the
decoder leave it in a state where every following H.264 decode is wrong, luma and chroma, for the whole clip (the game shows a green
tint lasting seconds or a full clip); the state holds until the next power-down. Measured on the board with
[build/gozen/hwcmp.c](../build/gozen/hwcmp.c) (hardware against software, frame by frame): 10 wrong of 25 openings, 9 wrong of 30
power-ups; the same pictures repeat exactly when wrong, two streams opened together are wrong together, the DRM plane layout is
constant, `dmesg` is silent; not the SRAM (RCB in RAM: 9 of 30), not the copy, not the clip. Known on the linux-rockchip list (S. Wright,
2026-05/06, NanoPi R76S and ArmSoM Sige5, also tested on a Rock 4D): the Rockchip BSP runs a priming decode at every decoder power-up
(`rk3576_workaround_run`), the mainline driver omits it, so the VDPU383 deblocking state is indeterminate after power-up. The patch
(not merged upstream) is built out of tree by `platforms/rock4d/image/build/rkvdec-module-build.sh` (module `rockchip-vdec.ko`
for the image's kernel, installed in `/lib/modules/<kver>/updates/`). Do not remove `sram` or `rockchip,disable-mmu-reset` from the
device tree to test this: the second one made the board not boot.

## Bootloader

Mainline U-Boot 2026.10~rc5 (Debian's source package; the board's defconfig is in it), Rockchip's `rk3576_ddr_*` and `rk3576_bl31_*`
blobs from rockchip-linux/rkbin pinned by hash. The board may also carry a Radxa U-Boot in its SPI flash: it boots the same image.
`u-boot-rockchip-spi.bin` is built too but the image does not use it; flash it to SPI only on purpose.

## Wi-Fi

The board's radio is on USB (see the device tree). The image carries the Realtek, Broadcom, Atheros and MediaTek firmware of Debian; if
the module needs an out-of-tree driver (AIC8800 for instance) Wi-Fi will not appear: use the Ethernet port or a USB dongle.

## To check on the board (nothing has been run there)

1. It boots: HDMI picture or UART log. If not, read the UART (pins, 1500000 baud) and report the last lines.
2. `ls /dev/dri /dev/media* /dev/video*`; `dmesg | grep -i -E 'panfrost|rkvdec'`.
3. The game starts, the GL renderer is Panfrost (`es2_info | grep -i renderer` in an X session).
4. A PuP video plays; `game/logs/godot.log` says `hwaccel v4l2request`/no "unavailable"; else `GOZEN_HWDEC=0`.

## Delivered build (2026-11-19)

`rock4d-debian13-sd.img.xz`, 845 MB, sha256 `11e30558749b9f3c8a9f29bd76fd1a83eb3782670d189e9004c72a35c8f107fb`, kernel 7.2.12+deb13, U-Boot
2026.10~rc5 (`u-boot-rockchip.bin` sha256 `e52f06be...d9da`), GoZen sha256 `104a785f...fd61` (glibc 2.38 symbols at most). Checked statically:
GPT, U-Boot at sector 64, FAT files and extlinux menu, ext4 fsck clean, read-only fstab, services and GoZen in place.

## Sound

Debian's kernel has no Rockchip SAI driver (`CONFIG_SND_SOC_ROCKCHIP_SAI` is not set), so the HDMI sound card of the device tree is never
created. [image/build/sai-module-build.sh](rock4d/image/build/sai-module-build.sh) builds `snd-soc-rockchip-sai.ko` for the image's kernel
(`SAI_KO=` in `build-native.sh`, loaded at boot through `modules-load.d`). It must be rebuilt for every kernel update. Not run on the board.
A USB sound card works without it (`/etc/asound.conf`).
