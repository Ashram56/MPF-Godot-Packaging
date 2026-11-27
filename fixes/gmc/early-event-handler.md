# A slide's MPF event handler never fires: its register_trigger was sent before MPF connected

| | |
|---|---|
| Id | `gmc/early-event-handler` (this file: `fixes/gmc/early-event-handler.md`) |
| Component | GMC |
| Kind | bug |
| Affected versions | GMC 1.0.0 |
| Platforms | all |
| Found on | a Williams WPC recreation, 2026-11-21 |
| Fact | observed (the handler never ran in a real MPF + GMC run; it did once the event was in `registered_events`) |
| Our fix | game code: add the event to `MPF.server.registered_events` before `add_event_handler` (below) |
| Applied by | the game (no patch in this repository) |
| Upstream | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draft, not filed** |

## Problem

A slide (or any node) that calls `MPF.server.add_event_handler("my_event", handler)` in `_ready()` never
receives `my_event`, although MPF posts it (MPF's log shows it). Other events registered the same way may work by
chance, when something else registered them after the connection.

## Cause

`bcp_server.gd` `add_event_handler()` sends `register_trigger?event=my_event` once, the first time, through
`_send()`, which drops the message while no MPF client is connected. Slides in the main scene are ready before
MPF connects, so MPF never learns that GMC wants the event. On every BCP reset (the connection), GMC re-sends
`register_trigger` only for `registered_events` and `auto_signals`, not for `registered_handlers`.

## Fix

In the game, before `add_event_handler`:

```gdscript
for e in ["my_event", "my_other_event"]:
    if e not in MPF.server.registered_events:
        MPF.server.registered_events.append(e)
    MPF.server.add_event_handler(e, ...)
```

An upstream fix would re-send `register_trigger` for every key of `registered_handlers` on reset.

## How to check

Run MPF + GMC, post `my_event` from MPF after the connection: with the fix the handler runs; without it nothing
happens and GMC logs nothing.

## Upstream issue (draft, not filed)

**Title:** add_event_handler() before MPF connects is lost (register_trigger not re-sent on reset)

**Body:**

```markdown
GMC 1.0.0. `MPF.server.add_event_handler("my_event", cb)` called in a slide's `_ready()` sends `register_trigger`
before MPF is connected, so it is dropped, and the `reset` handler re-registers only `registered_events` and
`auto_signals`, not the keys of `registered_handlers`. `cb` never runs.
Proposed fix: on reset, also send `register_trigger` for every key of `registered_handlers`.
```

## Related pitfall: `[keyboard]` entries need their kind

`gmc.cfg` `[keyboard]` entries are `key=["switch", "s_name"]` (optional third element `"active"`, `"inactive"`
or `"toggle"`) or `key=["event", "name"]`. `key=["s_name"]` is silently ignored (`mpf_gmc.gd` `_input()`,
`match cfg[0]`): no key works and nothing is logged (observed, 2026-11-21).
