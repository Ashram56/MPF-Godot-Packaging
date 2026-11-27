# A sound event reaches Godot but plays nothing: its "cmd" parameter is the event name

| | |
|---|---|
| Id | `gmc/bcp-cmd-kwarg` (this file: `fixes/gmc/bcp-cmd-kwarg.md`) |
| Component | GMC (BCP trigger handling) |
| Kind | bug |
| Affected versions | GMC with MPF 0.80.1, Godot 4.6.3 (and later until fixed upstream) |
| Platforms | all |
| Found on | a Williams WPC recreation (Terminator 2), 2026-11-21 |
| Fact | observed |
| Our fix | none in this repo: games must not name an event parameter `cmd` |
| Applied by | the game (its MPF event's keyword) |
| Upstream | GMC issue tracker; status: **draft, not filed** |

## Problem

A game posted `t2_sound` with `cmd='7a_0d'` for its Godot sound player. MPF's log showed the right value, but
the GDScript handler received `{"name": "t2_sound", "cmd": "t2_sound"}`: no sound ever played, on every platform,
with no error.

## Cause

BCP's trigger command carries the event as `trigger?name=...&<params>`; on the GMC side the parsed message's
command word is stored under the key `cmd` in the same dictionary as the parameters, so a parameter named `cmd`
is overwritten by the command name (inferred from the payload; the overwrite happens in GMC's BCP parsing).

## Fix

Name the parameter anything but `cmd` (or `name`), e.g. `sound='7a_0d'`.

## How to check

Post an event with `cmd=` and with another keyword, print the payload in the handler: the first shows the event
name, the second the value.

## Upstream issue (draft, not filed)

**Title:** BCP trigger parameter named `cmd` is replaced by the command name

**Body:**

```markdown
MPF posts an event registered by GMC with a keyword `cmd` (e.g. `events.post('x', cmd='a')`). The GDScript
handler receives `{"name": "x", "cmd": "x"}`: the parameter is overwritten by the BCP command/event name.
Expected: the parameter's value, or a documented reserved-key list. Workaround: use another keyword.
```
