# A slide's `MPF.server.add_event_handler()` never fires: the MPF event is never sent to GMC

| | |
|---|---|
| Id | `gmc/event-handler-before-connect` (this file: `fixes/gmc/event-handler-before-connect.md`) |
| Component | GMC |
| Kind | bug |
| Affected versions | GMC 1.0.0 (Godot 4.5.2, MPF 0.80.1); later until fixed upstream |
| Platforms | all |
| Found on | a Stern Whitestar recreation (Lord of the Rings), 2026-11-21 |
| Fact | observed (MPF log: no `register_trigger` received; the handler never ran) and code |
| Our fix | the game's slide script; nothing to apply (see Fix) |
| Applied by | the game's code |
| Upstream | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draft, not filed** |

## Problem

A slide or autoload calls `MPF.server.add_event_handler("my_event", handler)` in `_ready()`, typically the
window's initial slide. MPF posts `my_event` during the game, but the handler is never called and GMC logs nothing.

## Cause

`addons/mpf-gmc/scripts/bcp_server.gd`, `add_event_handler()`: the first registration of an event sends
`register_trigger?event=...` at once with `_send()`. The initial slide's `_ready()` runs before MPF has connected,
so the message goes nowhere, and the event is now in `registered_handlers`, so later calls do not send it again.
On connection (`reset` message), GMC re-registers only `registered_events` and `auto_signals`, not the keys of
`registered_handlers`.

## Fix

In the game: append the event name to `MPF.server.registered_events` before calling `add_event_handler()`;
GMC then registers it on every BCP reset (each connection), and the handler is in place:

```gdscript
for e in ["lotr_dmd", "lotr_sound"]:
    if e not in MPF.server.registered_events:
        MPF.server.registered_events.append(e)
MPF.server.add_event_handler("lotr_dmd", _on_dmd)
```

## How to check

Start Godot, then MPF; post the event from MPF (any custom code). Without the fix the MPF log shows no
`register_trigger` for it and the handler never runs; with it, `register_trigger?event=lotr_dmd` follows the reset
and the handler runs.

## Upstream issue (draft, not filed)

**Title:** add_event_handler() before MPF connects is lost (register_trigger not re-sent on reset)

**Body:**

```markdown
GMC 1.0.0, MPF 0.80.1, Godot 4.5.2.

Steps: in the initial slide's `_ready()`, call `MPF.server.add_event_handler("my_event", cb)`. Start GMC, then MPF.
Post `my_event` from MPF.

Expected: `cb` runs. Actual: never; MPF never receives `register_trigger?event=my_event`.

Cause: `add_event_handler()` sends `register_trigger` immediately (before the client is connected, so it is
dropped) and the `reset` handler re-registers only `registered_events` and `auto_signals`, not
`registered_handlers`' keys.

Proposed fix: in the `reset` branch, also send `register_trigger` for every key of `registered_handlers`.
```
