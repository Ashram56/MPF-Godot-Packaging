# Sounds sent with `bcp_trigger()` never reach GMC

| | |
|---|---|
| Id | `mpf/bcp-trigger-unregistered-events` (this file: `fixes/mpf/bcp-trigger-unregistered-events.md`) |
| Component | MPF (documentation; GMC works as designed) |
| Kind | improvement |
| Affected versions | MPF 0.80.1 with GMC 1.0.0; and later until documented upstream |
| Platforms | all |
| Found on | a Stern SAM recreation (Tron Legacy MPF), 2026-10-03 |
| Fact | observed (no sound at all), cause from MPF 0.80.1 code |
| Our fix | none in this repository: a game's custom code calls `bcp_trigger_client()` (below) |
| Applied by | the game's code; nothing to apply |
| Upstream | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, not filed** |

## Problem

A game's custom code sent `sounds_play` (and `slides_play`) to the media controller with
`machine.bcp.interface.bcp_trigger(name="sounds_play", ...)`. Nothing played and nothing was logged.

## Cause

MPF or GMC? MPF, and only its documentation: the behaviour is by design.

- `BcpInterface.bcp_trigger()` (`mpf/core/bcp/bcp_interface.py`) sends through
  `transport.send_to_clients_with_handler(handler=name, ...)`: only to clients that sent a `register_trigger`
  for that event name. Its docstring says "Send BCP 'trigger' to the connected BCP hosts".
- MPF's own players (`sound_player`, `slide_player`, through `BcpPluginPlayer.play()` in
  `mpf/config_players/bcp_plugin_player.py`) use `bcp_trigger_client()`, which sends to one client
  unconditionally. GMC therefore never needs to register `sounds_play`, and does not.
- So `bcp_trigger()` is the call for events a client asked for; `bcp_trigger_client()` is the call for player
  commands. Nothing says so, and an unregistered event is dropped without a log line.

## Fix

The game sends player commands the way MPF's players do:

```python
client = self.machine.bcp.transport.get_named_client("local_display")
self.machine.bcp.interface.bcp_trigger_client(client=client, name="sounds_play", settings=..., context=..., calling_context=..., priority=0)
```

## How to check

Call `bcp_trigger(name="sounds_play", ...)` with GMC connected: no sound, nothing in MPF's log. The same with
`bcp_trigger_client(client=<local_display>, ...)`: the sound plays.

## Upstream issue (draft, not filed)

**Title:** Document that bcp_trigger() only reaches clients that registered the event (and log when nobody did)

**Body:**

```markdown
**Environment**
- MPF 0.80.1, GMC 1.0.0 (any BCP media controller)

**What happened**
Custom code sent `sounds_play` to the media controller with
`machine.bcp.interface.bcp_trigger(name="sounds_play", settings=..., context=..., priority=0)`.
No sound played and nothing was logged.

**Why**
`BcpInterface.bcp_trigger()` calls `transport.send_to_clients_with_handler(handler=name, ...)`, so it only reaches
clients that sent `register_trigger` for that name. MPF's own players use `bcp_trigger_client()`, so media
controllers do not register `sounds_play` / `slides_play`. That is consistent, but the docstring says
"Send BCP 'trigger' to the connected BCP hosts", and nothing tells custom-code authors which call to use.

**Proposed change**
1. Docstring of `bcp_trigger()`: "Send a BCP trigger to the clients that registered this event name
   (register_trigger). To drive a media controller's players, use bcp_trigger_client()."
2. A debug log line in `bcp_trigger()` when no client has registered the name.
3. A line in the BCP / custom code docs with the call MPF's players make:
   `bcp_trigger_client(client=machine.bcp.transport.get_named_client("local_display"), name="sounds_play", ...)`.
```
