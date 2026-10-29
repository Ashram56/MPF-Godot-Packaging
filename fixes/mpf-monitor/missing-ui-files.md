# `mpf monitor` stops: searchable_tree.ui: No such file

| | |
|---|---|
| Id | `mpf-monitor/missing-ui-files` (this file: `fixes/mpf-monitor/missing-ui-files.md`) |
| Component | MPF Monitor |
| Kind | packaging |
| Affected versions | mpf-monitor 1.0.0 on PyPI (wheel and sdist); and later until fixed upstream |
| Platforms | all |
| Found on | a Stern SAM recreation, 2026-10-03 |
| Fact | observed; the PyPI wheel and sdist listed again on 2026-10-12 (no `.ui` file in either) |
| Our fix | [`mpf_godot/toolchain.py`](../../mpf_godot/toolchain.py) `MPF_MONITOR_UI_FILES`, `MPF_MONITOR_UI_URL`; [`mpf_godot/setup_toolchain.py`](../../mpf_godot/setup_toolchain.py) `install_monitor_ui()` |
| Applied by | `python -m mpf_godot setup` (unless `--no-monitor`) |
| Upstream | MPF Monitor, https://github.com/missionpinball/mpf-monitor/issues; status: **draft, not filed** |

## Problem

After `pip install mpf-monitor==1.0.0`, `mpf monitor` opens and stops when it builds its windows:

```
... mpfmonitor/core/ui/searchable_tree.ui: No such file
```

## Cause

- `mpfmonitor/core/devices.py`, `modes.py`, `variables.py` and `inspector.py` load Qt Designer files with
  `uic.loadUi(os.path.join(os.path.dirname(__file__), "ui", "<name>.ui"))`.
- The release's `pyproject.toml` sets `include-package-data = true` and `packages.find include = ["mpfmonitor*"]`,
  but the sdist has no `MANIFEST.in` and no `package-data` entry for `*.ui`, so neither the sdist nor the wheel
  carries `mpfmonitor/core/ui/` (inferred from the package contents).
- Missing: `events_table.ui`, `inspector.ui`, `searchable_table.ui`, `searchable_tree.ui`.

## Fix

Setup downloads the four files from the release's git tag
(`https://raw.githubusercontent.com/missionpinball/mpf-monitor/v1.0.0/mpfmonitor/core/ui/`), checks that each
starts like a Qt Designer file (`<ui`), and writes them next to the installed package. It adds only missing
files, so a fixed release needs nothing.

## How to check

```sh
pip download mpf-monitor==1.0.0 --no-deps && unzip -l mpf_monitor-1.0.0-py3-none-any.whl | grep "\.ui"   # nothing
python -m mpf_godot setup                    # "MPF Monitor's window layouts (4 files missing ...)": 4 added
python -m mpf_godot run <game> --monitor     # the monitor opens its windows
```

## Upstream issue (draft, not filed)

**Title:** 1.0.0 on PyPI is missing mpfmonitor/core/ui/*.ui (searchable_tree.ui: No such file)

**Body:**

```markdown
**Environment**
- mpf-monitor 1.0.0 from PyPI (wheel and sdist), MPF 0.80.1, Python 3.11, Windows/macOS/Linux

**Steps to reproduce**
1. `pip install mpf==0.80.1 mpf-monitor==1.0.0`
2. Start a game, then `mpf monitor` in the machine folder.

**Expected:** the monitor windows open.

**Actual:** the monitor stops with `searchable_tree.ui: No such file`. Neither
`mpf_monitor-1.0.0-py3-none-any.whl` nor `mpf_monitor-1.0.0.tar.gz` contains `mpfmonitor/core/ui/`
(events_table.ui, inspector.ui, searchable_table.ui, searchable_tree.ui), which `devices.py`, `modes.py`,
`variables.py` and `inspector.py` load with `uic.loadUi()`.

**Cause** (from the package contents): `include-package-data = true` only picks files named by MANIFEST.in or
tracked by a VCS plugin; the sdist has neither, and there is no package-data entry for `*.ui`.

**Proposed fix** in pyproject.toml:

    [tool.setuptools.package-data]
    mpfmonitor = ["core/ui/*.ui"]

(or a MANIFEST.in with `recursive-include mpfmonitor *.ui`), then a 1.0.1 release. A CI step
`unzip -l dist/*.whl | grep core/ui/searchable_tree.ui` would keep it from coming back.

**Workaround:** copy the four files from the v1.0.0 tag into `site-packages/mpfmonitor/core/ui/`.
```
