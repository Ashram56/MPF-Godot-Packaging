# Frame rate on a new board (Raspberry Pi 4 as the worked example): what to check before promising one

> Moved here from Stern-SAM-Decryption `agents/packaging.md` (section 5d) on 2026-10-27: Godot, GoZen, V4L2 and
> board findings belong to this repository; Stern-SAM-Decryption keeps ROM extraction and re-coding. Related fixes
> with upstream drafts: [fixes/godot/](../fixes/README.md#godot), [fixes/gde-gozen/](../fixes/README.md#gde-gozen).
> Worked example: a Stern SAM recreation on a Raspberry Pi 4B.


Tested on a Pi 4B, Debian 13 (trixie), Raspberry Pi kernel 6.18, Mesa 25.0.7 (Mesa 26.2.2 from the Pi repository
gave the same times), Godot 4.6.3 on the Compatibility (OpenGL ES) renderer, GoZen for the PuP Pack's videos, a 1080p
backglass full screen, the classic 128x32 DMD in its own window (2026-10-24; findings also in issue #44). The
numbers are in the game repository (`docs/pup/README.md`, "Raspberry Pi 4"); this is the method and what applies to
any SAM game or any new board (a Pi 5, an Orange Pi, another Jetson). All observed on the machine unless said.

## A. Check these first, in this order, before profiling the game**

1. **Which renderer and which thread mode really run.** The Pi 4 needs `--rendering-driver opengl3` (Vulkan is not a freeze but 1 fps:
   V3DV uploads each copied video plane with a render pass that allocates and zeroes a fresh tile-state buffer, about
   2 s a frame with 1080p planes; stack `texture_2d_update` > `vkCmdCopyBufferToImage` > `copy_buffer_to_image_shader`
   > `v3dv_job_allocate_tile_state`. A bare Godot 1080p scene does 74.8 fps in Vulkan against 39 in OpenGL, so only
   video uploads are the problem. The separate render thread under Vulkan crashed after 5 s: a game script touched
   the scene tree from that thread. V3DV exposes `VK_EXT_external_memory_dma_buf`, but a zero-copy import needs a
   GDExtension doing the import and a TFU copy to a tiled image: not built). A game's `run.py` added `--render-thread safe` whenever `opengl3` was asked (a workaround for
   the captures under Xvfb), so the Pi ran with the separate render thread off while `project.godot` said on and
   Jetson docs said "on by default". Ask the engine (`RenderingServer.is_on_render_thread()`), never the setting
   (a command-line `--render-thread` overrides `project.godot`'s `thread_model`). It cannot be turned on there: Godot 4.6.3
   with `--render-thread separate` and opengl3 crashes at start ("Error initializing GLAD", SIGSEGV; the GL ES context
   is not created on the render thread) (code: `EGLManager::release_current()` in `drivers/egl/egl_manager.cpp`
   leaves `current_window` set, so the render thread's `window_make_current()` returns early with no context; one
   line, `current_window = nullptr;`, fixes it, in Godot's master but not in 4.6.3: a Godot built with it runs
   `separate` cleanly, observed). On the Pi 4 it moved the main thread from 90 % to 60 % (+45 % on the render thread,
   +6-12 points in all) without more frames, but with a frame cap it gave the steadiest frames (see C). Any GDExtension
   that makes GL calls must then run them through `RenderingServer.call_on_render_thread()`. The same applies to a
   launcher's window mode: test fullscreen against windowed.
2. **Fullscreen or not, and one window only.** A windowed Godot on X is copied by X every frame (a Pi 4: +7 ms TFU and
   +10 ms render at 1080p; an empty scene 45 fps windowed, 60 fps with `--fullscreen`, which page flips). A second
   window on the same X screen (an LCD DMD beside a full screen backglass) loses the page flip as well: Pi 4 at a
   30 fps cap, 29.6 -> 21 fps, the TFU from 13 % to 42 % (observed). Draw the second display inside the full screen
   window instead (a `Control` over or beside the backglass's screens: same cost as no DMD, observed; a game's
   `[dmd] window="backglass"` in `game/pup.cfg`). A 3D background behind such a DMD (a 3D animated frame) cost
   ~40 ms of GPU a frame there: keep it off small GPUs.
3. **The cost of a full-window layer, with the default 2D shader.** Measure an empty scene, then a `ColorRect`,
   then N layers. On the Pi 4 (V3D, 8 QPU at 500 MHz, about 16 G instructions a second) Godot's default canvas
   shader is 118 instructions a pixel, so about 136 Mpixel/s: 10-14 ms for one 1080p layer, +10 ms for each more.
   `render_mode unshaded` and a branch-free YUV shader (32 instructions) cut that 4 times. Blending is free
   (opaque and transparent `ColorRect` cost the same); textures and bandwidth were not the limit. Use
   `V3D_DEBUG=shaderdb` (instructions, threads, spills) and `/sys/devices/platform/v3dbus/fec00000.v3d/gpu_stats`.
   A full-window `ColorRect` for a black background costs 3 to 6 fps: use `RenderingServer.set_default_clear_color`.
4. **Videos: layers hidden under an opaque video should neither be drawn nor decoded** (a silent one pauses until
   uncovered). The Pi 4's hardware decoder slows the GPU by 15 to 30 %, software decoding in parallel does not.
5. **A heavy background in a SubViewport** (a 3D animated DMD frame: 3D with glow, about 13 passes a frame) cost
   27 ms a frame on the Pi 4 and half of the frame rate; turning it off (or the classic 128x32 DMD) is the largest
   single gain. Count the render passes a frame before blaming the video.
6. **GPU frequency was not the limit once the shaders were light**: an overclock to 600 MHz (no extra voltage)
   gave nothing, because the main thread became the limit. Overclocking is the last step, and needs the owner.

## B. The V4L2 stateful decoder (`bcm2835-codec`, `/dev/video10`, FFmpeg `h264_v4l2m2m`)**

- `avcodec_flush_buffers()` leaves it answering EOF to every later request (a looping video stops): restart in
  place (`VIDIOC_STREAMOFF`/`STREAMON` on both queues, as the stateful decoder interface defines a seek) or recreate
  the decoder. `pkt_timebase` and `time_base` must be set. Capture buffers are YU12 or NV12, 1920x1088 for 1080p.
- The capture buffers are **uncached** mappings: reading a 1080p frame costs 10-15 ms (1.3 ms from normal memory),
  and NEON does not help (25 %). So copying frames to Godot's textures is the bottleneck, not decoding.
- **Zero-copy** (validated: 54 fps and 1.1 ms CPU a frame in a C prototype; Godot's CPU 160 % -> 93 %, video lag
  4.4 s -> 0.9 s in the game): `VIDIOC_EXPBUF` (dmabuf per capture buffer, once) -> `EGL_EXT_image_dma_buf_import`
  per plane (R8 for Y, U and V with their offsets and pitches; GR88 for NV12's UV) -> `glEGLImageTargetTexture2DOES`
  -> `RenderingServer.texture_create_from_native_handle` -> the existing YUV shader. FFmpeg 7.1 has no drm_prime
  output for `v4l2m2m`: find the buffer from `frame->buf[0]` (opaque is FFmpeg's internal `V4L2Buffer`), so FFmpeg's
  source tree must stay configured next to GoZen. The GL calls must run on the render thread. Keep the software
  fallback, hold decoded frames until a few frames after they were shown, and skip late frames instead of slipping
  the clock.
- **Mesa v3d cannot sample a linear dmabuf texture**: it copies the plane to a tiled shadow on the TFU at every
  draw (`V3D_DEBUG=perf`: "Updating WxH@0 shadow for linear texture", `v3d_update_shadow_texture`): about 1.6 ms a
  1080p plane, 12 ms a frame for two 1080p videos. Converting once per decoded frame does not help while the game
  shows fewer frames than the video has. Re-encoding the videos to 720p cuts it 4 to 6 times but the owner may
  refuse to touch the pack; `Window.content_scale_size` (a lower render size, videos untouched) is the other lever
  (1280x720: +38 % fps).
- **The driver's STREAMOFF returns too early (kernel bug, any `h264_v4l2m2m` user).** In `bcm2835-codec`
  (code: `drivers/staging/vc04_services/bcm2835-codec/bcm2835-v4l2-codec.c`, Raspberry Pi kernel 6.18), the buffer
  callbacks `ip_buffer_cb` and `op_buffer_cb` signal the end of a stop with
  `if (!port->enabled && atomic_read(&port->buffers_with_vpu)) complete(&ctx->frame_cmplt);`: the test is inverted,
  so the completion fires on the *first* buffer returned and `stop_streaming` comes back while buffers are still
  with the VPU. Symptoms in `dmesg` (observed, Pi 4B): `videobuf2_common: driver bug: stop_streaming operation is
  leaving buffer N in active state`, WARNINGs in `__vb2_queue_cancel` and in `vb2_buffer_done` called from
  `buffer_work_cb`, and now and then a NULL dereference in `dma_release_from_dev_coherent` (`vb2_dc_put` from a
  dmabuf release) that needs a reboot. Every close or loop of a video is a STREAMOFF, so a PuP Pack hits it within
  minutes, with or without dmabuf zero-copy. Fix: `!atomic_read(...)` at the three places that test it (complete
  when no buffer is left with the VPU). Build the module out of tree against the matching `linux-headers` package
  (cross-build it, not on the board) and load it in place of the stock one (`rmmod bcm2835-codec; insmod ...`, or
  install it in `/lib/modules/$(uname -r)/updates/` and run `depmod -a` so it wins at boot); rebuild it at every
  kernel update until the fix is upstream. Check `dmesg` for the warning after a soak, not only that videos play.
- **A hardware decoding switch keyed to one board decodes in software on the next.** A game that turns hardware
  decoding on only when it finds Jetson device nodes (`/dev/nvhost-*`) silently runs software decoding on a Pi 4,
  and a benchmark that forces the environment variable (`GOZEN_HWDEC=1`) hides it (code). Detect each
  board's decoder (`/dev/video10` with `bcm2835-codec` on a Pi), and check the startup log line (for example
  "software decoding") of the *installed service*, not of a hand-started run.
- Pi sound and screens, found on the way: the 3.5 mm jack card is missing on trixie (`snd_bcm2835.enable_headphones=0`
  in the DTB bootargs: append `snd_bcm2835.enable_headphones=1` to `cmdline.txt`); a screen that sends no EDID and is
  forced with `video=HDMI-A-n:1920x1080@60D` gets no HDMI audio (vc4 treats it as DVI): give it an EDID with a CEA
  block (audio, LPCM, HDMI VSDB) through `drm.edid_firmware=HDMI-A-n:edid/<file>.bin`; without PipeWire ALSA
  `default` is card 0 (often an HDMI port with nothing), Godot then uses its Dummy driver: write `/etc/asound.conf`
  (`plug` to `hw:Headphones`; dmix on the jack stalls); X can keep an unplugged HDMI output as the primary at 0,0
  (turn it off in `~/.xinitrc` with `xrandr`).
- **Remote Control on the board:** a `claude remote-control` session started by a service from the home directory
  asks for folder trust at every start: start it from a dedicated folder (`~/claude-rc`) and answer once. Builds do
  not belong on the board (FFmpeg and godot-cpp took about 45 minutes with the game stopped): cross-build in
  Docker or on a build machine and hand the library over through a throwaway git branch the board clones.

**Open:** `tools/pup/runtime/` (the runtime other games copy) does not have these changes yet: the fast YUV shader,
covered layers neither drawn nor decoded, no full-window `ColorRect`, `render_size`, and the zero-copy patch of GoZen
(in the first game: a `gozen_zerocopy.patch`, the add-on's `video_playback.gd` and the PuP player).

## C. Measuring (any new board)
 compare at the same frame rate and report the video lag (median and the 95th
percentile) and the frames over 50 ms, not CPU percent alone (a lower CPU at a lower frame rate proves nothing);
three runs per variant, because random video picks move the frame rate by 15 %; stop the game and any build while
measuring; the GPU's queue time (`gpu_stats`), ALSA underruns and `vcgencmd get_throttled` go in every row. Measure the video lag
(the decoded frame's time against its presentation time) for every decoding configuration: on a slow board
software decoding can show a high frame rate while it delivers the videos several seconds late with the CPU
saturated, whereas V4L2 hardware decoding with dmabuf zero-copy keeps the lag near zero at about half the CPU
(observed, Pi 4B). Frame rate and CPU alone pick the wrong configuration.
Report the frame time spread too (p90, frames over 40 ms): with vsync at 60 Hz a GPU near full makes every frame a
little over 16.7 ms wait for the next vblank and cost 33 ms, so "45 fps" is an uneven mix of 60 and 30 (Pi 4: median
16.7 ms, p90 35 ms). When the videos are 30 fps (check with `ffprobe`), `--max-fps 30` loses no video frame and costs
less (Pi 4: 190 % -> 165 % CPU, GPU 72 % -> 58 %); with a separate render thread it was the steadiest (p90 33.3 ms,
3 % of frames over 40 ms against 7 %). Look for a 30 Hz mode first (`xrandr`): an EDID that only offers 60 Hz rules
out true 30 Hz vsync. Change one variable per run and repeat the control at the end: two controls 20 minutes apart
differed by 1-2 fps. NV12 instead of YUV420P from the V4L2 decoder (two planes instead of three in zero-copy) changed
nothing measurable on the Pi 4 (GPU -3 points).

## D. Building for the board off the board
 Cross-compile on an x86_64 machine with Ubuntu's `aarch64-linux-gnu`
toolchain (glibc 2.39 on 24.04; check `objdump -T | grep GLIBC_` against the board's). Godot: put `gcc`, `g++`, `ar`,
`ranlib`, `strip` symlinks to the `aarch64-linux-gnu-` tools first on `PATH` and run
`scons platform=linuxbsd arch=arm64 target=editor production=yes lto=none use_static_cpp=yes` (`PKG_CONFIG_LIBDIR`
pointed nowhere so no host library leaks in; the X11/Wayland headers are Godot's own): 38 min on 4 cores, 148 MB,
57 MB with `xz -9`. Without LTO it measured the same as the official build on the Pi 4 (observed). GoZen and FFmpeg
cross-build the same way (FFmpeg `--enable-cross-compile --arch=aarch64 --cross-prefix=aarch64-linux-gnu-`); for a
binary that must also run on JetPack 5, build in an `ubuntu:20.04` container (glibc 2.29-2.31). A GDScript change can
be checked without the board: `qemu-aarch64-static -L /usr/aarch64-linux-gnu <arm64 godot> --headless --path game
--check-only --script res://<file>.gd` (autoload names are unknown there: compare with the unchanged file). Hand the
binaries to the board on a throwaway orphan git branch with their `.sha256` (it needs no credentials to clone a
public repository), and measure them beside the installed ones, never in their place.
