# Render and video guidelines for slow GPUs (engine and platform level)

Read from the code of Godot's canvas path, GDE GoZen and FFmpeg 7.1 and from the measurements in [godot-performance.md](godot-performance.md),
[frame-rate-method.md](frame-rate-method.md) and `fixes/`; **not measured as a whole** (a desk analysis, 2026-11-23). Fact tags: **code** (read in
the source), **observed** (a measurement elsewhere in this repository), **inferred** (reasoning, to confirm). The game-side rules (what a game's
display scripts should do) are in Stern-SAM-Decryption `agents/improvement.md`, section 2c; this page is what the platform must provide.

The content of a game (its videos, pictures, look) is never changed by these guidelines: they act on the engine, the platform and the
game's display code only.

## Where each lever lives

| Lever | Level | Why there |
|---|---|---|
| Godot's own source | **none** (we only patch the EGL separate-render-thread crash) | settings and project choices reach everything below |
| Video path (copies, threads, zero-copy) | **platform**: the GDE GoZen build and `video_playback.gd` of `addons/gde_gozen` | the same for every game |
| Per-board defaults (3D quality, arena resolution, MSAA, update cadence of a background, frame cap, DMD mode) | **platform**: board profiles and `limits.md` | a game declares the options, a board picks the values |
| Layer rules (opaque layers, nothing drawn under an opaque overlay, update cadence of a background viewport) | **game display runtime**, with the board's budget from the platform | needs the scene, which only the game knows |

## Video: what GoZen and FFmpeg do (code)

1. **One zero-copy path only.** Every hardware route except the Raspberry Pi 4's returns the frame to system memory (`_hw_download()`,
   `av_hwframe_transfer_data`), then copies it into an `Image` row by row, then `duplicate()`s it for the render thread, then uploads it:
   3 to 5 copies per frame and per video, on every board. Cheap on an Intel N100 (main thread at 8 % of a core, [x86/perf-report-2026-10-28.md](x86/perf-report-2026-10-28.md)), the structural limit on a small ARM board.
2. **DMA-buf reads are slow, and FFmpeg does not mitigate them for V4L2.** `drm_transfer_data_from` (`libavutil/hwcontext_drm.c`) is an `mmap` of each buffer, `DMA_BUF_IOCTL_SYNC`, a plain row-by-row `av_frame_copy`, then `munmap`, every frame. The capture buffers of V4L2 decoders are
   allocated by `vb2-dma-contig`, uncached for the CPU on non-coherent SoCs (inferred; observed on a Raspberry Pi 4: 10-15 ms per 1080p frame against 1.3 ms in normal memory, [v4l2m2m-zero-copy](../fixes/gde-gozen/v4l2m2m-zero-copy.md)).
   FFmpeg's VAAPI route avoids it (`vaGetImage` into a cacheable buffer, comment in `hwcontext_vaapi.c`).
3. **A generic zero-copy route exists on paper.** VAAPI (`vaExportSurfaceHandle`), V4L2 request (DRM PRIME frames) and V4L2 M2M (`VIDIOC_EXPBUF`) all end in an `AVDRMFrameDescriptor` (fds, offsets, pitches, modifier). The Raspberry Pi 4 patch ([gozen_zerocopy.patch](../build/gozen/gozen_zerocopy.patch)) already does the GL side (`EGL_EXT_image_dma_buf_import` per plane, `texture_create_from_native_handle`, frames held until shown, calls on the render thread): only the source of the descriptor would change. To check first: the modifier of the decoder's output, Mesa's handling of a linear dma-buf (the Pi's v3d keeps a tiled shadow copy, [fix](../fixes/gde-gozen/v4l2m2m-zero-copy.md); Panfrost: inferred not), the decoder's buffer pool when frames are held. Windows (D3D11) and Godot's Vulkan renderer need other work.
4. **Decoder threads** (`FFmpeg::enable_multithreading`): `thread_count = cores - 1` frame threads **per video**: four open videos on a 4-6 core board mean 12 to 20 decoding threads fighting Godot's main thread (inferred; not measured). Frame threading also adds N-1 frames of latency and memory per stream.
5. **No fast-decode options set**: `skip_loop_filter`, `AV_CODEC_FLAG2_FAST`; `lowres` exists only for MPEG-1/2/4 and MJPEG, not H.264.
6. **Per-frame allocations**: a new 3 MB `Image` per decoded frame (`duplicate()`), `memcpy` per row even when `linesize == width`. A ring of preallocated planes avoids the page faults (inferred).
7. **A video decoded at full size is copied and uploaded at full size** unless the decoder scales (only the Jetson's does: [set-target-size-nv12](../fixes/gde-gozen/set-target-size-nv12.md)). A video file made for the size it is shown at costs proportionally less on every route.

## Rendering: what applies on every tile-based GPU (V3D, Mali)

- Godot's Compatibility renderer breaks the frame into a pass per `SubViewport`, per `clip_children`, per backbuffer copy; each pass is a full framebuffer load and store on a tiler.
- The canvas shader's cost per pixel decides the fill rate: 118 instructions per pixel by default on V3D (observed, [pi4-canvas-shader-fill-rate](../fixes/godot/pi4-canvas-shader-fill-rate.md)); `render_mode unshaded` cuts it by 4.
- A window used as a texture (`get_texture()` on the root) is rendered to an off-screen target; whether a minimised or off-screen window is rendered at all is to read in Godot's `RendererViewport::draw_viewports` (not done).
- MSAA: V3D and Mali implement 4x; 2x is probably promoted (inferred).
- Environment glow in the Compatibility renderer: whether 4.6.3 supports it on GLES is to check in the log before relying on it.

## Per-board budget

A board's profile should declare, next to `dmd.mode`: the number of full-screen video layers it allows at the display size, whether a live 3D background is allowed (full / light / none), the arena resolution and MSAA defaults, and the update cadence of a background viewport. Values come from one measurement per board (the empty-scene ladder of [frame-rate-method.md](frame-rate-method.md)), so a new scene never needs its own tuning.

## To do (none of it built)

1. Decoder threads per video (1-2), `skip_loop_filter` option, a ring of planes: small patches of `gozen.patch` / `video_playback.gd`.
2. Zero-copy from `AVDRMFrameDescriptor` (A3): the larger piece, the one that changes the copies on every V4L2 request and VAAPI board.
3. Read Godot's source for the minimised-window question and the Compatibility glow; write the answer here.
4. Measure the whole page: desk analysis only until then.
