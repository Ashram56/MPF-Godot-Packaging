# Fixes and improvements

Every change we carry to MPF, MPF Monitor, GMC, Godot and the add-ons and libraries around them, one document
each: problem, cause, our fix, affected versions, platforms, how to check, and a draft issue for the upstream
project. **No draft is filed yet**: each becomes one upstream issue when the owner says so. Platform and
installer findings (Windows, macOS, Linux, Jetson) are in [../platforms/](../platforms/README.md).

New fix: copy [TEMPLATE.md](TEMPLATE.md) to `fixes/<component>/<slug>.md`, then run `python fixes/make_index.py`
(this page is generated from the documents' tables; `tests/test_fixes.py` checks both).

## MPF

Upstream tracker: https://github.com/missionpinball/mpf/issues

| Fix | Kind | Platforms | Applied by | Upstream |
|---|---|---|---|---|
| [Sounds sent with `bcp_trigger()` never reach GMC](mpf/bcp-trigger-unregistered-events.md) | improvement | all | the game's code; nothing to apply | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, n… |
| [`p_roc: driverboards: sternSAM` gives an unknown machine type](mpf/p-roc-driverboards-lowercased.md) | bug | all | the game's config; nothing to apply | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, n… |
| [No P-ROC driver for MPF on Linux, nor on Apple silicon Macs](mpf/pinproc-linux-macos.md) | packaging | Linux x86_64 and arm64 (Jetson included); macOS (Apple sili… | `install/install_linux.sh --proc`, `install/install_macos.sh --proc`, `python -m mpf_godo… | pypinproc, https://github.com/missionpinball/pypinproc/issues (wheels… |
| [P-ROC on Windows: "Could not import pinproc" without the VC++ runtime or FTDI's driver](mpf/pinproc-windows-vcredist.md) | packaging | Windows x86_64 and x86; Windows on ARM (no build at all) | `install/install_windows.ps1 -Proc` (the D2XX driver stays a manual step: FTDI's download… | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, n… |
| [`mpf` does not start once MPF Monitor is installed (ruamel.yaml.clib 0.2.15)](mpf/ruamel-yaml-clib-0.2.15.md) | packaging | all (Python before 3.13; ruamel.yaml does not use the C lib… | `python -m mpf_godot setup` (pip installs the pin next to MPF) | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, n… |

## MPF Monitor

Upstream tracker: https://github.com/missionpinball/mpf-monitor/issues

| Fix | Kind | Platforms | Applied by | Upstream |
|---|---|---|---|---|
| [`mpf monitor` stops: searchable_tree.ui: No such file](mpf-monitor/missing-ui-files.md) | packaging | all | `python -m mpf_godot setup` (unless `--no-monitor`) | MPF Monitor, https://github.com/missionpinball/mpf-monitor/issues; st… |
| [MPF Monitor does not install on Jetson / arm64 Linux (PyQt6 builds from source and fails)](mpf-monitor/pyqt6-arm64-glibc.md) | packaging | Linux arm64 with glibc older than 2.39 (Jetson L4T R35 / Je… | `python -m mpf_godot setup`, `install/install_linux.sh` | MPF Monitor, https://github.com/missionpinball/mpf-monitor/issues; st… |

## GMC

Upstream tracker: https://github.com/missionpinball/mpf-gmc/issues

| Fix | Kind | Platforms | Applied by | Upstream |
|---|---|---|---|---|
| [One bad BCP message stops GMC's BCP thread for good](gmc/bcp-parse-error.md) | bug | all | `python -m mpf_godot setup`, `python -m mpf_godot patch-gmc [GMC_DIR]`; idempotent | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draf… |
| [No sound or music for the whole session: GMC's BCP thread stops at connect](gmc/bcp-partial-lines.md) | bug | all | `python -m mpf_godot setup` (patches `toolchain/addons/mpf-gmc`), `python -m mpf_godot pa… | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draf… |
| [Number keys and "/" do nothing in GMC on an AZERTY keyboard](gmc/keyboard-layout.md) | bug | all (any non-US layout: AZERTY seen; QWERTZ and others like… | `python -m mpf_godot setup`, `python -m mpf_godot patch-gmc [GMC_DIR]`; idempotent | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draf… |
| [GMC quits when a launcher checks its port; on Windows the check never sees GMC](gmc/port-probe-quits.md) | bug (quits) / improvement (a ready sign… | all (the quit); Windows (IPv6-only listener) | the launcher (`python -m mpf_godot run GAME`) | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draf… |
| [Every slide show rebuilds the slide's nodes: hitches on slow hardware](gmc/slide-reuse.md) | improvement | all; it matters on slow targets (measured on a Jetson Xavie… | **not applied by this repository's installer**: it needs game code (which slides to keep,… | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draf… |

## Godot

Upstream tracker: https://github.com/godotengine/godot/issues

| Fix | Kind | Platforms | Applied by | Upstream |
|---|---|---|---|---|
| [Late frames on a 4-core board: Godot's main thread shares its core](godot/core-pinning-main-thread.md) | improvement | Linux with 4+ cores and a real display; measured on Jetson… | the launcher (`python -m mpf_godot run`), on Linux with 4+ cores, not under Xvfb | Godot, https://github.com/godotengine/godot/issues; status: none need… |
| [Screenshots from a headless run are blank, and Movie Maker runs too fast for a live client](godot/headless-draws-nothing.md) | improvement | all for `--headless` and `--write-movie`; the Xvfb workarou… | the launcher (`python -m mpf_godot run`, `--xvfb` to force it) | Godot docs, https://github.com/godotengine/godot-docs/issues; status:… |
| [A GMC game that was never opened in the Godot editor does not start](godot/import-before-first-run.md) | packaging | all | `python -m mpf_godot addons GAME` and `python -m mpf_godot run GAME` (only when `GAME/.go… | none needed for Godot (documented behaviour); a note for GMC's instal… |
| [The game freezes for seconds the first time text is drawn with an MSDF font](godot/msdf-glyphs-main-thread.md) | bug | all (MSDF generation is CPU work); measured on Linux arm64… | the game's setup step (a headless Godot script run once after install) | Godot, https://github.com/godotengine/godot/issues; status: **draft,… |
| [On a Raspberry Pi 4 the game freezes while a video plays with Vulkan: the launcher uses OpenGL ES](godot/pi4-vulkan-freezes-with-video.md) | improvement | Raspberry Pi 4 | the launcher (`python -m mpf_godot run`) | Godot, https://github.com/godotengine/godot/issues; status: none need… |
| [Every start recompiles every pipeline: the Vulkan pipeline cache is never saved with the separate render thread](godot/pipeline-cache-not-saved-render-thread.md) | bug | Linux arm64 seen (Jetson Xavier NX, L4T R35.6.4, Vulkan, Mo… | a project setting a game sets in its `project.godot` | Godot, https://github.com/godotengine/godot/issues; status: **draft,… |
| [Godot's separate render thread: on with videos on Godot 4.6.3, a loss on 4.5.2 without them](godot/render-thread-setting.md) | improvement | all (a project setting); measured on Jetson Xavier NX, L4T… | a project setting a game sets in its `project.godot`; the launcher (`python -m mpf_godot… | Godot, https://github.com/godotengine/godot/issues; status: none need… |
| [With the separate render thread, the log fills with `_texture_2d_update` errors when text is drawn](godot/separate-render-thread-glyph-cache.md) | bug | Linux arm64 seen (Jetson Xavier NX, L4T R35.6.4, Vulkan, Mo… | - | Godot, https://github.com/godotengine/godot/issues; status: **draft,… |
| [Large animations stall for seconds when they load: lossless frames decompress slowly on ARM](godot/vram-compressed-frames.md) | improvement | all (an import setting); measured on Jetson Xavier NX, L4T… | the game's media generator or import presets (Tron-Legacy-MPF: `scripts/gen_media.py` wri… | Godot, https://github.com/godotengine/godot/issues; status: none need… |
| [Four windows run at a quarter of the refresh rate: each vsync'd window waits for its own vertical blank](godot/vsync-one-window-multiwindow.md) | improvement | Jetson Xavier NX, L4T R35.6.4, X11 + openbox, NVIDIA Tegra… | the game's script, once its extra windows are created | Godot, https://github.com/godotengine/godot/issues; status: **draft,… |
| [Video switches stall about 1.3 s on a 4-core board: background tasks queue on one thread](godot/worker-pool-low-priority-ratio.md) | improvement | all (a project setting); matters on 4-core boards; measured… | a project setting a game sets in its `project.godot` | Godot, https://github.com/godotengine/godot/issues; status: none need… |

## GDE GoZen

Upstream tracker: https://codeberg.org/gozen/gde_gozen/issues

| Fix | Kind | Platforms | Applied by | Upstream |
|---|---|---|---|---|
| [Videos decode on the CPU on Windows: GPU decoding through Direct3D 11 Video or DXVA2](gde-gozen/d3d11va-dxva2-windows.md) | improvement | Windows 10/11 x86_64 (MinGW-w64 cross build); NVIDIA, AMD a… | the committed `addons/gde_gozen/bin/libgozen.windows.template_release.x86_64.dll`, copied… | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are of… |
| [Several videos at once fall behind: frames decoded on the main thread, just in time](gde-gozen/decode-ahead.md) | improvement | all (GDScript); measured on Jetson Xavier NX, L4T R35.6.4 | `python -m mpf_godot addons GAME --video` | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are of… |
| [Videos decode on the CPU on a Jetson: GoZen never asks FFmpeg for the hardware decoder](gde-gozen/hwdec-nvmpi-first.md) | improvement | Linux arm64 on a Jetson: AGX Orin, L4T R36.4.3 (JetPack 6.2… | the committed binaries in `addons/gde_gozen/bin/` (rebuilt by `build/gozen/build_gozen.sh… | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are of… |
| [Videos decode on the CPU on a Raspberry Pi 4: GoZen only knows the Jetson's hardware decoder](gde-gozen/hwdec-v4l2m2m.md) | improvement | Linux arm64 on a Raspberry Pi 4 with the Raspberry Pi kerne… | the committed binary `addons/gde_gozen/bin/libgozen.linux.template_release.arm64.so` once… | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are of… |
| [The GoZen build links libvpx, libaom and TLS that a player of local mp4 files never uses](gde-gozen/lean-build-option.md) | improvement | Linux x86_64 and arm64 (glibc 2.31+), Windows x86_64 (MinGW… | `../../build/gozen/build_gozen.sh` (`scons ... lean=yes`) | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are of… |
| [Every video switch freezes all windows for 1 to 2.5 s: VideoPlayback opens, loops and frees videos on the main thread](gde-gozen/main-thread-stalls.md) | bug | all (GDScript); worst with a slow-to-open hardware decoder:… | `python -m mpf_godot addons GAME --video` (copies the patched add-on into the game) | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are of… |
| [The app freezes for minutes when a video seeks near its end: `seek_frame()` steps back one frame per retry at EOF](gde-gozen/seek-frame-retry-loop.md) | bug | all (C++ loop); seen on Jetson Xavier NX, L4T R35.6.4, nvpm… | `python -m mpf_godot addons GAME --video` | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are of… |
| [Small video windows still copy full-size frames: decode at the shown size, as NV12](gde-gozen/set-target-size-nv12.md) | improvement | scaling: Jetson with jetson-ffmpeg's nvmpi decoders (measur… | the committed binaries plus the add-on scripts, copied by `python -m mpf_godot addons GAM… | GDE GoZen, https://codeberg.org/gozen/gde_gozen/issues (issues are of… |

## jetson-ffmpeg

Upstream tracker: https://github.com/gjrtimmer/jetson-ffmpeg/issues

| Fix | Kind | Platforms | Applied by | Upstream |
|---|---|---|---|---|
| [Closing a decoder mid-video sometimes crashes the app (SIGSEGV in libnvmmlite_video)](jetson-ffmpeg/close-crash.md) | bug | Jetson AGX Orin, L4T R36.4.3 (JetPack 6.2): crashes; Jetson… | `../../platforms/jetson/install_jetson_hwdec.sh`; checked by `../../platforms/jetson/jets… | jetson-ffmpeg, https://github.com/gjrtimmer/jetson-ffmpeg/issues; sta… |
| [With several videos switching at once, one decoder hangs forever (JetPack 6) or segfaults (JetPack 5)](jetson-ffmpeg/concurrent-decoders-hang.md) | bug | Jetson AGX Orin, L4T R36.4.3 (JetPack 6.2): hangs; Jetson X… | `../../platforms/jetson/install_jetson_hwdec.sh`; checked by `../../platforms/jetson/jets… | jetson-ffmpeg, https://github.com/gjrtimmer/jetson-ffmpeg/issues; sta… |
| [Looping or seeking a video freezes the app forever: the decode after `avcodec_flush_buffers()` never returns](jetson-ffmpeg/flush-hang.md) | bug | Jetson AGX Orin, L4T R36.4.3 (JetPack 6.2), Ubuntu 22.04; J… | `../../build/gozen/build_gozen.sh` (GoZen's FFmpeg) and `../../platforms/jetson/install_j… | jetson-ffmpeg, https://github.com/gjrtimmer/jetson-ffmpeg/issues; sta… |
| [Hardware decoding is slow on JetPack 5: every plane of every frame is mapped and unmapped for the CPU](jetson-ffmpeg/planes-mapped-once.md) | improvement | measured on Jetson Xavier NX, L4T R35.6.4 (JetPack 5.1.4);… | `../../platforms/jetson/install_jetson_hwdec.sh` | jetson-ffmpeg, https://github.com/gjrtimmer/jetson-ffmpeg/issues; sta… |
| [Every video switch stalls about 1 s: `nvmpi_decoder_close()` waits out two 500 ms timeouts](jetson-ffmpeg/slow-close.md) | bug | Jetson AGX Orin, L4T R36.4.3 (JetPack 6.2); Jetson Xavier N… | `../../platforms/jetson/install_jetson_hwdec.sh` (builds libnvmpi with the patch); checke… | jetson-ffmpeg, https://github.com/gjrtimmer/jetson-ffmpeg/issues; sta… |

## native_video

Upstream tracker: https://github.com/claytercek/godot-native-video/issues

| Fix | Kind | Platforms | Applied by | Upstream |
|---|---|---|---|---|
| [Videos fail to open, or the app crashes, depending on the file path's length (native_video heap overrun)](native-video/gdzig-heap-overrun.md) | bug | Windows x86_64 (seen: panics, `OpenFailed`, heap corruption… | the committed binaries, copied by `python -m mpf_godot addons GAME --video` on Windows an… | godot-native-video, https://github.com/claytercek/godot-native-video/… |

Test projects and repro programs the reports refer to: [repro/](repro/).

37 documents.
