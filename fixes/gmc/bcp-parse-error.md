# One bad BCP message stops GMC's BCP thread for good

| | |
|---|---|
| Id | `gmc/bcp-parse-error` (this file: `fixes/gmc/bcp-parse-error.md`) |
| Component | GMC |
| Kind | bug |
| Affected versions | GMC 1.0.0; and later until fixed upstream |
| Platforms | all |
| Found on | a Stern SAM recreation (Tron Legacy MPF), 2026-10-03 |
| Fact | observed (with [bcp-partial-lines](bcp-partial-lines.md)), cause from GMC 1.0.0 code |
| Our fix | [`mpf_godot/gmc_patch.py`](../../mpf_godot/gmc_patch.py) (edit `bcp-parse-error`, `scripts/bcp_parse.gd`) |
| Applied by | `python -m mpf_godot setup`, `python -m mpf_godot patch-gmc [GMC_DIR]`; idempotent |
| Upstream | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draft, not filed** |

## Problem

When GMC gets a `trigger` message it cannot parse, Godot logs a script error and GMC handles no further BCP
message in that session.

## Cause

In `scripts/bcp_parse.gd`, the error branch for a trigger whose JSON did not parse builds its message from the
parser's error: `result.error = "Error %s parsing trigger: %s" % [json.error, message]`. On that path the parse
result is null, so reading `json.error` raises a script error. The error is raised on GMC's BCP thread, which
stops; the error report meant for the log never gets there.

## Fix

Build the error message without the null result:

```diff
-			result.error = "Error %s parsing trigger: %s" % [json.error, message]
+			result.error = "Error parsing trigger: %s" % message
```

The bad message is then logged as GMC intended and skipped; the next message is handled.

## How to check

Send GMC a trigger whose JSON part is cut short (a line ending in the middle of a `json=` value). Unpatched:
script error, no more messages handled. Patched: one `Error parsing trigger` line in the log, and the following
messages work.

## Upstream issue (draft, not filed)

**Title:** bcp_parse.gd: error path reads json.error on a null parse result and stops the BCP thread

**Body:**

```markdown
**Environment**
- GMC 1.0.0, Godot 4.5.x / 4.6.x, MPF 0.80.1

**Steps to reproduce**
Send GMC a `trigger` command whose JSON payload does not parse (for example one cut short, which also happens
when a long message is split across socket reads).

**Expected:** an "Error ... parsing trigger" line in the log, and the next message is handled.

**Actual:** a script error in the error branch itself, and GMC's BCP thread stops: no further BCP message is
handled in that session.

**Cause**
`scripts/bcp_parse.gd`:
`result.error = "Error %s parsing trigger: %s" % [json.error, message]` runs when the parse failed, where the
parse result is null, so `json.error` raises.

**Proposed fix** (we run this on GMC 1.0.0)

    -   result.error = "Error %s parsing trigger: %s" % [json.error, message]
    +   result.error = "Error parsing trigger: %s" % message

A wider guard would also help: check every parse result for null before reading from it, so no single
message can stop the thread (GDScript has no try/catch).
```
