# A music player driven by triggers keeps playing after the game was cancelled

| | |
|---|---|
| Id | `godot/audio-only-screen-keeps-playing` (this file: `fixes/godot/audio-only-screen-keeps-playing.md`) |
| Component | Godot |
| Kind | bug |
| Affected versions | any: the game's own player logic |
| Platforms | all (seen on a Raspberry Pi 4) |
| Found on | Tron Legacy MPF, 2026-10-27 |
| Fact | observed: the PuP OST (an audio-only player) ran from the start of the game to the end of the test, 149 s, through the service menu and the attract |
| Our fix | on `tron_service_entered` MPF sends the music player a `stopall`, which clears its foreground and background and stops the stream (Tron-Legacy-MPF PR #55, `game/tron_pup/mode.py`, `game/pup/pup_screen.gd`) |
| Applied by | the game's code |
| Upstream | none needed |

## Problem

Music from a game cancelled in the service menu (SELECT twice ends the game without its game over) kept looping
under the attract, which then sounded quieter: its own sounds were mixed under the music.

## Cause

The OST is a background loop of its own player, started and stopped by triggers (game over, attract). A game
ended from the service menu skips the game over, so no trigger ever stops it, and a plain `stopplayer` only
stops the foreground, not the background loop.

## Fix

A `stopall` command that clears both the foreground and the background of the player, sent when the path that
skips the usual stop is taken. Any player driven by triggers needs a way out for every route that ends a game.

## How to check

Play a game, open the coin door, SELECT twice, BACK, close the door: the music stops when the menu opens. A
probe that logs every second which `AudioStreamPlayer` is playing shows it (before: until the end; after: stops
at the menu).

## Upstream issue

None.
