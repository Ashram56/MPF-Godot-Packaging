# AK2PLUS (Intel N100) — performance, 2026-10-28

Full game `full_game_to_portal` 620 s, DMD hd, PuP 3 windows on one 1080p60 HDMI screen, GoZen VAAPI, ALSA
(USB audio card 0, dmix). Godot 4.6.3 Vulkan. intel_gpu_top -J 1 s. Results copied from /dev/shm.

| run | folder |
|---|---|
| 30 FPS (bundle default `display.max_fps` 30) | 20261028-110457-ak2plus-hd |
| 60 FPS (`TRON_MAX_FPS=60`, no setting changed) | 20261028-112639-ak2plus-hd-60fps |
| A/V check, 120 s, 60 FPS, `GOZEN_AUDIO_LATENCY=0` | 20261028-113728-av-gozenlat0 |

## 30 vs 60 FPS

| | 30 FPS | 60 FPS |
|---|---|---|
| FPS avg / worst second | 30.0 / 29 | 60.0 / 58 |
| frame median / p99 / max | 33.3 / 36.7 / 65 ms | 16.7 / 23.5 / 77 ms |
| main thread to draw submitted, median / p99 | 32.2 / 32.9 ms (cap wait) | 15.9 / 22.0 ms |
| frames over 2 vblanks / over 100 ms | 11 / 0 | 3 / 0 |
| video frames skipped (screen 12 / 2 / 13 / 14) | 187 (184 / 3 / 0 / 0) | 1 (1 / 0 / 0 / 0) |
| A/V as the probe measures it, avg / max | 75 / 101 ms | 77 / 94 ms |
| black screens, Godot ERROR lines | 0, 0 | 0, 0 |
| GPU Render/3D busy avg / p95 / max | 28.7 / 35.9 / 39.9 % | 42.4 / 51.8 / 58.8 % |
| GPU Video busy avg / p95 / max | 11.4 / 15.6 / 19.7 % | 11.7 / 16.2 / 19.9 % |
| GPU clock avg / max | 328 / 507 MHz | 440 / 701 MHz |
| package power avg / max | 9.1 / 13.0 W | 11.8 / 13.9 W |
| CPU package temperature avg / max | 49 / 64 °C | 57 / 61 °C |
| CPU clock avg | 2.3 GHz | 3.0 GHz |
| load average 1 min avg / max (4 cores) | 2.7 / 3.5 | 3.1 / 4.4 |
| board RAM used max (of 15.4 GB) | 2.67 GB | 2.67 GB |
| Godot resident peak, video memory peak | 723 MB, 450 MB | 727 MB, 442 MB |
| effects preload | 20.5 s | 10.9 s |
| busiest threads (% of a core avg/peak) | Worker 0 29/67, Workers 1-3 16/46, main 8/58 | Worker 0 22/42, a Godot thread 14/23, Workers 1-3 12/36, main 8/54 |

60 FPS late frames: 10 s (61 ms), 452 s (43 ms), 480 s (77 ms), each within 1.3 s, 0.7 s and 0.5 s of a topper
(screen 13) video open (TronLegacyLogo, TronLegacyLogo, EndOfLine).

## Video skips at 30 FPS: cadence, not decoding

The probe logs `open` at the open's first shown frame, so it has no separate "open requested / worker open done /
first frame decoded" times: in every open the first frame is shown in the frame of the open (0 ms after it, late
0 ms). The skips are not at the start: 30 of 187 fall in the first second after an open, 157 later, and they are
regular one-frame skips every 4 frames (frames 4, 8, 12, 16, ... at +100, +233, +366, +500 ms): a 30 FPS cap on a
60 Hz screen draws every other vblank, the jitter of that cadence puts a due video frame past its time and GoZen
steps 2. At 60 FPS the same videos skip 1 frame in 10 minutes, so the decoder (VAAPI, 12% busy) keeps up.

Screen 12 opens with skips (30 FPS run; first skips as (ms after open, frames, frame nr)):

| t open (ms) | clip | skipped < 1 s / later | first skips | frames shown |
|---|---|---|---|---|
| 4733 | StartGame 1 | 1 / 5 | (601,1,19) (6167,1,186) (6667,1,201) | 241 |
| 29533 | LightCycleFlare1 | 7 / 40 | (100,1,4) (233,1,8) (366,1,12) (500,1,16) | 137 |
| 125900 | LightCycleJackpot2 | 2 / 9 | (200,1,7) (266,1,9) (1499,1,46) | 81 |
| 237364 | DiscWars1 | 8 / 13 | (67,1,3) (200,1,7) (334,1,11) (467,1,15) | 66 |
| 262564 | DiscWarsJackpot1 | 1 / 4 | (433,1,14) (4467,1,135) | 170 |
| 271797 | DiscWarsJackpot2 | 5 / 11 | (333,1,11) (467,1,15) (600,1,19) | 69 |
| 502295 | LightCycleFlare3 | 1 / 12 | (767,1,24) (2367,1,72) (5567,1,168) | 250 |
| 570428 | MatchGameOver | 4 / 58 | (500,1,16) (633,1,20) (767,1,24) (900,1,28) | 214 |
| 513295 (screen 2) | Drain4 | 0 / 3 | (2033,1,62) (2100,1,64) (2233,1,68) | 75 |

Clips (ffprobe): all H.264 High, yuv420p, 1920x1080, 30/1, 2 B-frames, AAC 48 kHz stereo (TronLegacyBG: no audio),
first keyframe at 0, next at 8.33 s (GOP 250).

| clip | bitrate | duration |
|---|---|---|
| MatchGameOver | 2.53 Mb/s | 9.23 s |
| LightCycleFlare1 | 3.52 Mb/s | 6.20 s |
| DiscWars1 | 3.13 Mb/s | 2.93 s |
| DiscWarsJackpot2 | 4.04 Mb/s | 2.87 s |
| LightCycleFlare3 | 3.79 Mb/s | 8.80 s |
| LightCycleJackpot2 | 3.61 Mb/s | 3.10 s |
| StartGame 1 | 4.91 Mb/s | 8.27 s |
| DiscWarsJackpot1 | 2.84 Mb/s | 5.87 s |
| Drain4 | 4.33 Mb/s | 2.63 s |
| TronLegacyBG | 1.00 Mb/s | 15.23 s |

## A/V: the probe's figure follows GoZen's assumed latency

- Godot's ALSA driver reports an output latency of 0. GoZen's clock then subtracts its fallback
  (`GOZEN_AUDIO_LATENCY`, else `audio/driver/output_latency` = 60 ms, video_playback.gd lines 101-105, 408-410);
  `tools/perf_probe.gd` (line 108) subtracts only `AudioServer.get_output_latency()` = 0.
- Default: probe 75-77 ms. With `GOZEN_AUDIO_LATENCY=0` (120 s): probe 17 ms avg, 43 max. The figure moves by the
  60 ms GoZen assumes: it is fallback + ~15 ms, not a measure of what is heard.
- What is heard depends on the real ALSA delay: Godot asks for a 2048-frame period (60 ms at 48 kHz rounded to a
  power of 2: 42.7 ms) with 2 periods, on dmix (slave period 1024, buffer 16384, card 0 USB). The real delay is
  between ~43 and ~85 ms, so the default 60 ms is about right; the true offset is probably within ±25 ms.
- To get a measured answer: (1) the probe should subtract the same fallback as GoZen when the driver says 0;
  (2) the real delay needs either a driver that reports it (PulseAudio/PipeWire, or Godot's ALSA driver
  computing snd_pcm_delay) or an acoustic check (a clip with a flash + click, filmed). Then set
  GOZEN_AUDIO_LATENCY to that value in /etc/default/mpf-netconfig.

## Proposals (nothing changed in the game)

1. `display.max_fps` 60 on this board: removes the cadence skips (187 -> 1) and halves late frames (11 -> 3), for
   +13 points of GPU 3D, +2.7 W, +8 °C average. The setting's own help says 60 where the GPU keeps up. Needs a board
   profile for the AK2PLUS (or x86) in profiles.json, or the installer setting it.
2. If 30 FPS stays: GoZen should not step 2 when a frame is late by less than one vblank (show it late instead).
3. The remaining late frames come with topper video opens (screen 13): opening off the main thread or pre-opening
   the topper loops (TronLegacyLogo is opened again each time) would remove them.
4. Probe: subtract the GoZen fallback latency, so av.csv measures the same clock GoZen plays by.

## What changed on the machine during these tests

Nothing permanent for the runs: `TRON_MAX_FPS=60` and `GOZEN_AUDIO_LATENCY=0` were environment variables of the
test commands only; no override.cfg. Earlier today (kept): game/options.json `"dmd.mode": "hd"`;
game/.godot/extension_list.cfg `res://addons/gde_gozen/gozen.gdextension`; /etc/default/mpf-game `GODOT=...`,
`TRON_VENV=...`; ~/.profile GPU wait; ~/.config/systemd/user/claude-remote.service; linger on for mpf;
/opt/games/tron-legacy-mpf/perf -> /dev/shm/perf. installed vs platform addons/gde_gozen/video_playback.gd: identical
(md5 a4e154988e05ae1d04ee023b23a046a7).

## 60 FPS as the service default (second 60 FPS run, 20261028-114422-ak2plus-60fps-default)

/etc/default/mpf-game: `MPF_GAME_ARGS=--max-fps 60` (backup /etc/default/mpf-game.bak-20261028); the service
runs `Godot ... --max-fps 60 -- --dmd=hd`. The profile itself runs scripts/run.py with TRON_MAX_FPS=60 (the same
Godot flag).

| | 60 FPS run 1 | 60 FPS run 2 |
|---|---|---|
| FPS avg / worst second | 60.0 / 58 | 60.0 / 57 |
| frame median / p99 / max | 16.7 / 23.5 / 77 ms | 16.7 / 21.9 / 58 ms |
| frames > 20 ms (of ~36700) | 1757 (1583 in 20-25 ms) | 1034 (969 in 20-25 ms) |
| frames > 25 / > 33.4 / > 41.7 ms | 171 / 6 / 3 | 59 / 3 / 1 |
| of the > 20 ms, within 0.5 s after a video open | 176 | 117 |
| video frames skipped | 1 | 3 |
| GPU 3D busy avg / p95 / max | 42.4 / 51.8 / 58.8 % | 42.8 / 52.7 / 64.8 % |
| GPU Video busy avg / max | 11.7 / 19.9 % | 11.6 / 20.9 % |
| package power avg / max (GPU alone) | 11.8 / 13.9 W | 11.7 / 14.0 W (GPU 0.5 / 0.8 W) |

Skips left (step 2 = one frame), with ms after the open's first frame shown (= open, see above):
- run 1: screen 12 AttractMode-Trailer3 frame 5, 134 ms after open, late 0.2 ms
- run 2: screen 12 AttractMode-Trailer1 frame 5, 140 ms after open, late 6.7 ms; StartGame 1 frame 157, 5208 ms;
  MatchGameOver frame 196, 6502 ms
The regular every-4th-frame skips after the opens are gone. The one early skip (frame 5, ~140 ms) is in attract
mode, the first event clip over the backglass loop.

## Audio sync, recomputed (60 FPS run 2)

av.csv minus the 60 ms GoZen subtracts (GOZEN_AUDIO_LATENCY unset, output_latency 60, driver latency 0):
97 samples, median +16.9 ms, p95 +31.4, min -1.0, max +37.3 (+ = audio ahead). Per clip (median / p95):
DiscWarsJackpot1 12.6/32.4, MatchGameOver 20.9/26.5, StartGame 1 13.6/29.8, DiscWars6 26.9/31.0,
LightCycleFlare5 17.9/22.9, LightCycleFlare6 15.3/27.9, QuorraJackpot3 11.4/13.8, DiscWarsJackpot2 5.9/8.8,
LightCycleFlare1 13.2/17.2, LightCycleJackpot4 20.1/20.6, DiscWars7 24.3/29.8, AttractMode-Trailer1 7.6/8.5.

This recomputed figure does not depend on GOZEN_AUDIO_LATENCY: the probe's raw value is the latency GoZen assumes
plus this residual (75-77 ms with 60, 17 ms with 0), so changing the variable moves both by the same amount.
What is heard = residual + (assumed latency - real latency).

Audio path: Godot ALSA driver (no PulseAudio/PipeWire installed: no pactl, pw-top), mix rate 44100 (Godot default,
not set in project.godot) through the ALSA default plug + dmix (resampled to 48000) on card 0, the USB adapter
"CSCTEK USB Audio and HID" (0573:1573); not HDMI. dmix slave: S16_LE 2 ch 48000 Hz, period 1024, buffer 16384.
Godot's ALSA buffer: period = closest power of 2 of 60 ms x 44100 = 2048 frames (46.4 ms), 2 periods (92.9 ms):
the real delay is between ~46 and ~93 ms (about 70 ms on average) plus a few ms in the USB device; ALSA through
dmix gives no usable delay to read (status delay is garbage), so it is an estimate, not a measurement. If it is
~70 ms, what is heard is about +7 ms (audio slightly ahead); GOZEN_AUDIO_LATENCY=~0.087 (real + residual) would put
it at 0. Not changed: the computed offset cannot show the effect, and the real delay needs measuring first
(PipeWire/PulseAudio report it, or a filmed flash + click clip).

## Remaining skips and slow frames (both 60 FPS runs, no change)

- Frame-5 skip: only on the first clip ever played on screen 12 (AttractMode-Trailer3 at 1.00 s in run 1,
  AttractMode-Trailer1 at 0.94 s in run 2, ~140 ms after its first frame). None of the other 101 opens per run
  skips in its first 300 ms (each screen's first open: s13 0.72/0.66 s, s2 0.87/0.66 s, s12 1.00/0.94 s, s14
  15.85 s; only s12's skips). Cold start of the first 1080p clip with audio on that screen, during start-up.
- Slow frames >= 40 ms: start-up 0.42-1.63 s (window creation, first opens); 9.99 s / 9.93 s (61 / 58 ms) with no
  video event within 50 ms: the end of the 10.8 s DMD effects preload; run 1 452.61 s (43.8 ms) and 480.39 s
  (77.3 ms): topper (screen 13) opens TronLegacyLogo (+60 ms) and EndOfLine (+101 ms), small clips
  (1920x560 / 1920x562, 0.19 Mb/s, no audio), single opens, nothing else at the same time; run 2 502.2 s (39.7 ms):
  screen 14 LC Both Yellow Bottom Reverse (+54 ms) and screen 12 LightCycleFlare1 (+89 ms) together.
- At opens in general (after 8 s, per run: screens 12/2/13/14 = 39/18/19/21 opens), the worst frame in the 200 ms
  before the first frame is > 25 ms in 16/7/9/7 (run 1) and 12/5/6/5 (run 2) of them, > 33.4 ms in 2/2/3/1 and
  2/0/0/1: about one open in three costs a frame of 25-33 ms, whatever the clip size, and the topper's small clips
  do it as much as the 1080p ones: the cost is the open itself (decoder and texture setup), not the decode.

## Test A: GoZen blank image cached (Packaging commit 39b64b2), 60 FPS, two runs — reverted

| | ref 60 run 1 | ref 60 run 2 | 39b64b2 run 1 | 39b64b2 run 2 |
|---|---|---|---|---|
| opens (97) with worst frame in 200 ms before > 20 / > 25 / > 33.4 ms | 86 / 39 / 8 | 75 / 28 / 3 | 46 / 24 / 10 | 80 / 39 / 6 |
| frames > 20 / > 25 / > 33.4 / > 41.7 ms | 1757 / 171 / 6 / 3 | 1034 / 59 / 3 / 1 | 260 / 20 / 5 / 3 | 2350 / 172 / 4 / 2 |
| p99 / max | 23.5 / 77 | 21.9 / 58 | 19.4 / 93 | 23.2 / 52 |
| video frames skipped | 1 | 3 | 2 | 2 |

The two runs with the change bracket the two without: no measurable effect. The 20-25 ms frames vary 260 to 2350
between identical runs (start-time jitter under vsync more than missed vblanks). Installed file restored
(md5 a4e154988e05ae1d04ee023b23a046a7); the patched copy came from the branch, backup video_playback.gd.bak-20261028.

## Test B: audio buffer 30 ms and mix rate 48000 (game/override.cfg) — kept

The USB sink (card 0) plays 8000, 16000 or 48000 Hz only (/proc/asound/card0/stream0): Godot's default 44100 mix was
resampled to 48000 by plug/dmix. game/override.cfg:

    [audio]

    driver/output_latency=30
    driver/mix_rate=48000

(the service and run.py both read it; GoZen's fallback latency follows output_latency: 30 ms).

| | 60 FPS ref run 2 (60 ms, 44.1 kHz) | test B (30 ms, 48 kHz) |
|---|---|---|
| A/V raw probe avg / max | 77 / 97 ms | 45 / 63 ms |
| A/V recomputed (minus GoZen's latency) median / p95 / min / max | 16.9 / 31.4 / -1.0 / 37.3 | 11.8 / 32.3 / -8.2 / 33.3 |
| Godot buffer (period x 2) | 2048 @ 44.1 kHz = 46.4 ms x 2 | 1024 @ 48 kHz = 21.3 ms x 2 |
| frames > 20 / > 25 / > 41.7 ms, p99, max | 1034 / 59 / 1, 21.9, 58 | 226 / 31 / 3, 19.2, 73 |
| video frames skipped | 3 | 1 (first attract clip, frame 5) |
| underruns / xruns (journal, godot.log) | 0 | 0 |

The recomputed offset gets 5 ms closer to 0 and the real buffer is halved (estimated heard offset about +10 ms).
No underrun logged; crackle can only be checked by ear.

## Test C: PuP decoder warm-up (Tron-Legacy-MPF commit 26e779a), 60 FPS, two runs — reverted

Applied as a patch on the installed game/pup/pup_player.gd (its base differs from the bundle's: md5 302ca14f
installed vs 33f9a397 at 26e779a^); restored afterwards (backup pup_player.gd.bak-20261028). The warm-up clip
(AttractMode-Trailer1, screen -1 in the probe) opens at 0.85 s, 0 black screens, no ERROR/warning about it.

| | warm-up run 1 | warm-up run 2 |
|---|---|---|
| skipped (frames) | 5: warm clip frames 7 and 10; screen 12 AttractMode-Trailer2 frame 3 at 1.21 s and frame 25 at 1.94 s | 5: warm clip frames 8, 12, 14; none on a visible screen |
| first 12 s, frames > 25 ms | 0.50 s 141, 0.95 s 77, 1.03 s 92, 0.65-0.86 s 25-41, 1.18 s 26, 1.90 s 46, 10.18 s 49 | 0.43 s 159, 0.89 s 147, 0.60 s 59, 0.67-1.19 s 27-41 (8), 1.85-1.94 s 27-46, 10.14 s 58 |
| after 8 s: over 2 vblanks / over 100 ms, max | 4 / 1, 103 ms (170.7 s, QuorraMB: 3 screens) | 1 / 0, 58 ms |
| A/V recomputed median / p95 | 17.9 / 32.2 ms | 8.1 / 32.3 ms |

Without the warm-up (60 FPS runs) the first 12 s had 6-11 frames > 25 ms, worst 121-229 ms at 0.4 s, 51-56 ms at
~1.05 s. With it: 10 and 15, and a second long frame (77-92 ms, 147 ms) when the warm clip opens. The first visible
event clip still skipped in run 1 (frame 3 and 25 of Trailer2), so the cold-start skip moves or stays; the warm-up
adds start-up frames. Kept out.
