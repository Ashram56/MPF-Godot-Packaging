# GMC quits when a launcher checks its port; on Windows the check never sees GMC

| | |
|---|---|
| Id | `gmc/port-probe-quits` (this file: `fixes/gmc/port-probe-quits.md`) |
| Component | GMC (and how a launcher waits for it) |
| Kind | bug (quits) / improvement (a ready signal) |
| Affected versions | GMC 1.0.0, Godot 4.5.x and 4.6.x; and later until fixed upstream |
| Platforms | all (the quit); Windows (IPv6-only listener) |
| Found on | a Stern SAM recreation (Tron Legacy MPF): the quit 2026-10-03, the Windows IPv6 case 2026-10-03 |
| Fact | observed; GMC's code for the quit not read here (inferred: GMC treats any client that hangs up as MPF leaving) |
| Our fix | [`mpf_godot/launcher.py`](../../mpf_godot/launcher.py) `port_in_use()`, `wait_for_port()` |
| Applied by | the launcher (`python -m mpf_godot run GAME`) |
| Upstream | GMC, https://github.com/missionpinball/mpf-gmc/issues; status: **draft, not filed** |

## Problem

A launcher starts Godot (GMC is MPF's BCP server on port 5050), waits for the port, then starts MPF.

1. Waiting by connecting to 5050 (the usual "is the port open" check) makes GMC quit: the probe connects and
   hangs up, and Godot exits before MPF ever starts.
2. On Windows, a check of 127.0.0.1:5050 never sees GMC: Godot listens on an IPv6 socket that leaves IPv4 free,
   so the launcher waited forever and MPF never started. (MPF itself connects to `localhost`, which resolves to
   `::1` there, so MPF is not affected.)

## Cause

- GMC accepts the first client as MPF and quits when that client disconnects (inferred from the behaviour; it
  matches MPF's own `exit_on_close: True` for this connection). A probe is indistinguishable from MPF.
- Godot's `TCPServer.listen(port, "*")` opens an IPv6 socket. On Linux it also takes IPv4; on Windows the
  observed listener left 127.0.0.1:5050 free.

## Fix

The launcher never connects. It tries to **bind** the port, on every family and address:
`0.0.0.0`, `127.0.0.1`, `::` and `::1` (IPv6 sockets with `IPV6_V6ONLY`). If any bind fails, something listens.
On Windows each probe socket sets `SO_EXCLUSIVEADDRUSE` (else a bind can share a taken port); elsewhere
`SO_REUSEADDR` (so TIME_WAIT leftovers do not count). It also accepts GMC's `GMC listening on port` line in
Godot's log, and fails early, with the log's end, if Godot exits.

## How to check

`python -m mpf_godot run GAME`: "GMC is listening", then MPF connects. To see the quit: start Godot with GMC,
then `python -c "import socket; socket.create_connection(('127.0.0.1', 5050)).close()"`: Godot exits.

## Upstream issue (draft, not filed)

**Title:** A TCP probe of the BCP port makes GMC quit; offer a ready signal for launchers

**Body:**

```markdown
**Environment**
- GMC 1.0.0, Godot 4.5.x / 4.6.x, MPF 0.80.1; Linux, Windows

**Steps to reproduce**
1. Start the Godot project with GMC (BCP server on 5050).
2. `python -c "import socket; socket.create_connection(('127.0.0.1', 5050)).close()"`

**Expected:** GMC keeps waiting for MPF.

**Actual:** GMC quits. A launcher that waits for the port by connecting (the common pattern) therefore kills the
media controller before MPF starts.

Related: on Windows, Godot's listener is IPv6 only in our runs, so a probe of 127.0.0.1:5050 never succeeds.

**Proposed fix**
1. Quit on disconnect only for a client that has said `hello` (MPF always does); a connection that closes
   before any BCP command is ignored.
2. Give launchers a ready signal that needs no connection, e.g. a line on stdout or a `--ready-file=<path>`
   written once the server listens. (Our launcher binds the port on IPv4 and IPv6 to test it, and reads the
   "GMC listening on port" log line.)
3. Listen on both families explicitly on Windows, or document that the server is IPv6 there.
```
