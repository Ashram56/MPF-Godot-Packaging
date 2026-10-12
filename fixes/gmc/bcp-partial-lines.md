# No sound or music for the whole session: GMC's BCP thread stops at connect

| | |
|---|---|
| Id | `gmc/bcp-partial-lines` (this file: `fixes/gmc/bcp-partial-lines.md`) |
| Component | GMC |
| Kind | bug |
| Affected versions | GMC 1.0.0 (Godot 4.5, 4.6); a note in the game's patch says mpf-gmc `main` had the same change in 2026-10 (not re-checked here) |
| Platforms | all |
| Found on | a Stern SAM recreation (Tron Legacy MPF), 2026-10-03 |
| Fact | observed (no sound; script error in Godot's log), cause from GMC 1.0.0 code |
| Our fix | [`mpf_godot/gmc_patch.py`](../../mpf_godot/gmc_patch.py) (edits `bcp-partial-lines`, 3 edits in `scripts/bcp_server.gd`) |
| Applied by | `python -m mpf_godot setup` (patches `toolchain/addons/mpf-gmc`), `python -m mpf_godot patch-gmc [GMC_DIR]`; idempotent |
| Upstream | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draft, not filed** |

## Problem

Some sessions have no sound, no music and no callouts from the start to the end; slides queued before may still
show. Godot's log has a script error from GMC's BCP parsing right after MPF connects. It depends on timing, so
some starts are fine.

## Cause

- GMC's poll thread in `scripts/bcp_server.gd` reads what the socket holds and splits it into lines:
  `var messages := _client.get_string(bytes).split("\n")`. Each piece is parsed as a whole BCP message.
- A TCP read can end anywhere. MPF's `settings` message at connect is large (every machine setting with its
  value labels), so a read often ends inside it.
- GMC then parses half a message; the parse fails and raises a script error
  ([bcp-parse-error](bcp-parse-error.md)) that stops the BCP thread. Nothing MPF sends after that is handled.

## Fix

Keep the unfinished end of each read and put it in front of the next one; parse only complete lines. The
buffer is cleared when a new client connects.

```diff
 var _client: StreamPeerTCP
+var _rx_partial := ""
 ...
 		_client = _server.take_connection()
+		_rx_partial = ""
 ...
-		var messages := _client.get_string(bytes).split("\n")
+		var data := _rx_partial + _client.get_string(bytes)
+		var cut := data.rfind("\n")
+		_rx_partial = data.substr(cut + 1)
+		var messages := PackedStringArray()
+		if cut >= 0:
+			messages = data.substr(0, cut).split("\n")
```

## How to check

Start a game with a large settings list (operator adjustments) and sounds on: unpatched, some starts are silent and
the log shows the parse error; patched, every start has sound. `python -m mpf_godot patch-gmc` prints
`in place` once applied.

## Upstream issue (draft, not filed)

**Title:** BCP server parses each socket read as whole lines; a message split across reads stops the BCP thread

**Body:**

```markdown
**Environment**
- GMC 1.0.0, Godot 4.5.x / 4.6.x, MPF 0.80.1; Windows, macOS, Linux

**Steps to reproduce**
1. A machine config with many settings (MPF sends them all, with their value labels, in one `settings`
   message at connect).
2. Start GMC, then `mpf game`. Repeat a few times.

**Expected:** every BCP message is handled.

**Actual:** on some starts, a script error from the BCP parser right after connect, then nothing MPF sends is
handled for the rest of the session (no sounds, no music).

**Cause**
`scripts/bcp_server.gd` does `var messages := _client.get_string(bytes).split("\n")` and parses every piece as a
complete message. TCP gives no message boundaries: a read can end inside a long message, so its first half is
parsed alone, fails, and the error stops the thread.

**Proposed fix** (we run this on GMC 1.0.0)

    var _client: StreamPeerTCP
    var _rx_partial := ""            # the unfinished end of the last read

    # on a new connection
    _client = _server.take_connection()
    _rx_partial = ""

    # in the poll loop, instead of the split
    var data := _rx_partial + _client.get_string(bytes)
    var cut := data.rfind("\n")
    _rx_partial = data.substr(cut + 1)
    var messages := PackedStringArray()
    if cut >= 0:
        messages = data.substr(0, cut).split("\n")

If `main` already has this, a 1.0.x release with it would help everyone on 1.0.0.
```
