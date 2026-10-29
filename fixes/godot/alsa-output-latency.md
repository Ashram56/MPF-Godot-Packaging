# Sound cracks, and videos run ahead of their sound, on a Raspberry Pi 4 (ALSA)

| | |
|---|---|
| Id | `godot/alsa-output-latency` (this file: `fixes/godot/alsa-output-latency.md`) |
| Component | Godot |
| Kind | bug (latency 0) / improvement (buffer) |
| Affected versions | Godot 4.6.3, ALSA driver; and later until fixed upstream |
| Platforms | Linux with ALSA (seen on a Raspberry Pi 4, analogue jack, no dmix); Windows and macOS report a real latency |
| Found on | a Stern SAM recreation on a Raspberry Pi 4, 2026-10-25/26 |
| Fact | observed: 4-8 underruns a minute with 15 ms, none with 60 ms; `AudioServer.get_output_latency()` returns 0 while ALSA holds 58-93 ms (4096 frames at 44.1 kHz) |
| Our fix | the game sets `audio/driver/output_latency=60` in `project.godot` (or `--audio-output-latency 60`); [`../../addons/gde_gozen/video_playback.gd`](../../addons/gde_gozen/video_playback.gd) subtracts `GOZEN_AUDIO_LATENCY` (seconds) or the project's `output_latency` when the driver says 0 |
| Applied by | a project setting a game sets in its `project.godot`; the GoZen add-on; on the Pi image `GOZEN_AUDIO_LATENCY=0.087` in the service's environment |
| Upstream | Godot, https://github.com/godotengine/godot/issues; status: **draft, not filed** |

## Problem

1. With Godot's default 15 ms output buffer the sound cracks on a Pi 4 while videos play: ALSA underruns.
2. Videos synced to their sound (GoZen's audio clock: playback position + time since last mix - output latency)
   showed the picture about 0.09 s ahead of the sound, because the latency read back is 0.

## Cause

1. 15 ms is too short for a 4-core board busy decoding and drawing video.
2. Godot's ALSA driver does not report the device's delay (`snd_pcm_delay`), so `get_output_latency()` returns 0.

## Fix

1. 60 ms: no underruns in 60 s of play, 45 ms later sound is not noticeable on a pinball.
2. The add-on's clock uses a fallback when the driver says 0. Measured on the Pi: picture and sound within about
   0.02 s with `GOZEN_AUDIO_LATENCY=0.087`. Over 2.5 h of attract, no drift that grows; the Pi 4 jack's clock ran
   +15 ppm (under 1 ms a minute).

## How to check

`print(AudioServer.get_output_latency())` on the Pi: 0. `cat /proc/asound/card*/pcm0p/sub0/status` while playing:
`delay` of 2500-4100 frames.

## Upstream issue (draft, not filed)

**Title:** AudioServer.get_output_latency() returns 0 with the ALSA driver

**Body:**

```markdown
Godot 4.6.3, Linux, ALSA driver (Raspberry Pi 4, analogue output). get_output_latency() returns 0 while
snd_pcm_delay() reports 58-93 ms. Code that syncs video to audio (the docs' recommended formula) is then off by
the whole buffer. Expected: the driver's real latency (snd_pcm_delay or buffer size), like the WASAPI and CoreAudio
drivers.
```
