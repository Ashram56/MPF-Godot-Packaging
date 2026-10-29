# Video playback with GDE GoZen (and the native video add-on)

> Moved here from Stern-SAM-Decryption `agents/pup_pack.md` (section 6) on 2026-10-27. The PuP agent keeps which
> player a platform uses and the pack's mapping; how the players behave is this repository's. See also
> [fixes/gde-gozen/](../fixes/README.md#gde-gozen) (queue fill, hardware decoding order, NV12) and
> [platforms/jetson.md](jetson.md), [frame-rate-method.md](frame-rate-method.md) (V4L2 on a Pi 4).

- **One player everywhere it can be.** Windows first used the native add-on (Media Foundation): the owner saw
  audio/video stutter and drift. GoZen on Windows shares every fix made for the Jetson. (observed, a game owner,
  2026-10-10)
- **A video switch must never wait for a worker** (`tools/pup/runtime/pup_addons/gde_gozen/video_playback.gd`
  `close()`): GDE GoZen's player waited on the main thread for the screen's open or loop-restart task. A playlist
  switching during a loop restart (for example the end of a multiball, background and info screens switching
  together) froze every screen 0.3-0.6 s on a Xavier NX, in 2 full games of 5. The closed video now goes to the
  worker that frees it once that task is done, and the open and restart tasks take the video they work on instead of
  reading the node's (observed, 2026-10-12).
- **A/V sync cannot trust `AudioServer.get_output_latency()`**: with Godot's ALSA driver on a Raspberry Pi 4 it
  returns 0 while ALSA holds 58-93 ms (a 4096-frame buffer at 44.1 kHz), so the picture ran ~0.09 s ahead of the
  video's sound. The video clock now subtracts a fallback when it reads 0 (`GOZEN_AUDIO_LATENCY=0.087`,
  else the project's `audio/driver/output_latency`); Godot's default 15 ms buffer also underran there (cracks),
  60 ms fixed it. No growing drift in 2.5 h of attract; the Pi 4 jack's clock ran +15 ppm. (observed, 2026-10-26)
- **A DMD drawn inside the backglass window**: give it a whole number of render pixels per dot (for example 256x64 at
  512x128, `[dmd] view_size`) with nearest filtering and no second dot shader on top; two non-integer
  resamplings (256 dots in 535 px, then 1.5x to 1080p) gave a strong moiré. On a Pi 4 (Godot 4.6 Compatibility,
  V3D) `clip_children` on a 535x148 panel for round corners cost ~20 points of GPU and tripled the late frames:
  draw the round panel behind the DMD instead. A 256x64 dot DMD cost nothing (29.7 FPS at a 30 cap); the HD DMD
  without glow at 512x128 cost ~45 points of CPU and a 50 s preload; at native 1080p (3x) the GPU fell to 18 FPS.
  (observed, 2026-10-26)
- **Keep a 30 fps video in sync when the game draws less than 30 fps**: a video player that decodes one frame
  per drawn frame falls behind (Pi 4, game at 27.4 FPS: the picture ran ~85 ms per second late, 5 s after a
  minute of attract, while the audio clock stayed exact). Decode in a loop until the queue is full (for example:
  `_decode_frames` in `video_playback.gd`, queue of 3), and the gap stayed within +-0.2 s over 2 min.
  A hung or killed GoZen zero-copy process can leave the Pi 4's VideoCore wedged (v3d hang resets, codec
  component creation timeouts) until a reboot. (observed, 2026-10-27)
- **The GoZen Windows build** is a MinGW-w64 cross build in Docker (for example `scripts/build_gozen.sh windows`,
  `scripts/gozen/build_windows_in_docker.sh`, the hwaccel code in `scripts/gozen/gozen.patch` under `_WIN32`):
  FFmpeg 7.1 trimmed to the pack's codecs, `--enable-d3d11va --enable-dxva2` with the h264/hevc/vp9 hwaccels,
  asm on, everything static, so the DLL imports only Windows' own DLLs; LGPL (no `--enable-gpl`/`nonfree`).
  One D3D11 device serves every video (FFmpeg locks it). A cloud session cannot test the GPU: Wine loads the DLL
  and decodes in software, the GPU test is the owner's. (code)
- **Check the decoder without the game** (for example `python scripts/pup/video_check.py`): decodes a few pack videos
  on the GPU, then with `GOZEN_HWDEC=0`, and prints per video the decoder and how many times faster than real
  time it runs. On a Ryzen 7 7800X3D: GPU (d3d11va) about 1.0 ms per 1080p frame, 33x real time (the copy
  back from the GPU costs most of it); software 0.3 to 0.5 ms, 63x to 117x, but on all cores. Either way decoding
  is not a desktop PC's bottleneck: the GPU path is the default because it leaves the CPU to MPF and Godot.
  (observed, 2026-10-10)
