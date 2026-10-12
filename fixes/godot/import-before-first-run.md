# A GMC game that was never opened in the Godot editor does not start

| | |
|---|---|
| Id | `godot/import-before-first-run` (this file: `fixes/godot/import-before-first-run.md`) |
| Component | Godot (with GMC) |
| Kind | packaging |
| Affected versions | Godot 4.5 and 4.6.3 with GMC 1.0.0 (any add-on that relies on `class_name`) |
| Platforms | all |
| Found on | this repository's smoke test (`examples/minimal`), 2026-10-12; Tron Legacy MPF's setup has imported twice since 2026-10-02 |
| Fact | observed |
| Our fix | `mpf_godot/launcher.py` `import_project()` |
| Applied by | `python -m mpf_godot addons GAME` and `python -m mpf_godot run GAME` (only when `GAME/.godot/` has no class cache) |
| Upstream | none needed for Godot (documented behaviour); a note for GMC's install docs at https://github.com/missionpinball/mpf-gmc/issues; status: **draft, not filed** |

## Problem

A game folder fresh from git (no `.godot/` folder) started with `godot --path GAME` stops at once. GMC never opens
port 5050, so MPF waits forever. Godot's log:

```
SCRIPT ERROR: Parse Error: Could not find type "MPFDisplay" in the current scope.
          at: GDScript::reload (res://addons/mpf-gmc/classes/mpf_window.gd:6)
SCRIPT ERROR: Parse Error: Could not find base class "MPFSceneBase".
ERROR: Failed to instantiate an autoload, script 'res://addons/mpf-gmc/mpf_gmc.gd' does not inherit from 'Node'.
```

## Cause

GMC's scripts name each other by `class_name` (`MPFDisplay`, `MPFSceneBase`, ...). Godot resolves those names from
`.godot/global_script_class_cache.cfg`, which only an import (the editor, or `--import`) writes. A plain run does
not build it. The first import pass can also report the add-on's icons as missing; a second pass is clean.

## Fix

Before the first run, the launcher runs `godot --headless --path GAME --import` twice when the class cache is
missing. Games that ship their own setup do the same (Tron Legacy MPF's `setup.py` imports twice).

## How to check

`python -m unittest tests.test_smoke` copies `examples/minimal` (no `.godot/`), runs it, and checks that GMC
listens, MPF connects and the log has no `SCRIPT ERROR`. Without the import the same run fails as above.

## Upstream issue (draft, not filed)

**Title:** Docs: a project must be imported once before GMC runs from the command line

**Body:**

```markdown
GMC 1.0.0 with Godot 4.6.3. A GMC project checked out from git, where `.godot/` is not committed, fails when it is
started from the command line (`godot --path . `) before anyone opened it in the editor:

    SCRIPT ERROR: Parse Error: Could not find type "MPFDisplay" in the current scope.
    ERROR: Failed to instantiate an autoload, script 'res://addons/mpf-gmc/mpf_gmc.gd' does not inherit from 'Node'.

GMC never listens on 5050 and MPF waits. Running `godot --headless --path . --import` (twice: the first pass can
report the add-on's icons) builds `.godot/global_script_class_cache.cfg` and the project then starts.

Proposal: say so in the installation docs (cabinets and CI start GMC without the editor), or have GMC's
documented launch command import first.
```
