# `mpf` does not start once MPF Monitor is installed (ruamel.yaml.clib 0.2.15)

| | |
|---|---|
| Id | `mpf/ruamel-yaml-clib-0.2.15` (this file: `fixes/mpf/ruamel-yaml-clib-0.2.15.md`) |
| Component | MPF |
| Kind | packaging |
| Affected versions | MPF 0.80.1 (pins `setuptools~=72.2.0`, `ruamel.yaml==0.18.6`) with ruamel.yaml.clib 0.2.15, Python 3.10 to 3.12; and later until fixed upstream |
| Platforms | all (Python before 3.13; ruamel.yaml does not use the C library from 3.13 on) |
| Found on | a Stern SAM recreation (Tron Legacy MPF), 2026-10-03 |
| Fact | observed (`mpf` stopped at start); the `pkg_resources` step reproduced on Python 3.11.x, setuptools 72.2.0, 2026-10-12 |
| Our fix | [`mpf_godot/toolchain.py`](../../mpf_godot/toolchain.py) `REQUIREMENTS`: `ruamel.yaml.clib==0.2.14; python_version < "3.13"` |
| Applied by | `python -m mpf_godot setup` (pip installs the pin next to MPF) |
| Upstream | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, not filed** |

## Problem

With MPF 0.80.1 and MPF Monitor 1.0.0 in one environment, a fresh install takes ruamel.yaml.clib 0.2.15 and every
`mpf` command stops before it does anything:

```
pkg_resources.DistributionNotFound: The 'ruamel.yaml.clib>=0.2.7; platform_python_implementation == "CPython"
and python_version < "3.13"' distribution was not found and is required by ruamel.yaml
```

Without MPF Monitor, `mpf` starts.

## Cause

- ruamel.yaml.clib 0.2.15 installs its metadata as `ruamel_yaml_clib-0.2.15.dist-info` (0.2.14:
  `ruamel.yaml.clib-0.2.14.dist-info`).
- MPF loads plugin commands with `pkg_resources.iter_entry_points(group='mpf.command')` and
  `entry_point.load()` in `mpf/commands/__init__.py`. `load()` checks the plugin's whole requirement tree
  (mpf-monitor, then mpf, then ruamel.yaml, then ruamel.yaml.clib).
- The `pkg_resources` of setuptools 72.2 (pinned by MPF) does not match the `ruamel_yaml_clib` metadata to
  the requirement `ruamel.yaml.clib`, so the check fails. MPF Monitor is the only installed package with an
  `mpf.command` entry point, which is why it takes MPF Monitor to trigger it.

## Fix

Pin `ruamel.yaml.clib==0.2.14` for Python before 3.13. That release has the old metadata name; pip accepts it
because ruamel.yaml asks for `>=0.2.7`.

## How to check

```sh
python3.11 -m venv v && v/bin/pip install "setuptools==72.2.0" "ruamel.yaml==0.18.6" "ruamel.yaml.clib==0.2.15"
v/bin/python -c "import pkg_resources; pkg_resources.require('ruamel.yaml==0.18.6')"   # DistributionNotFound
v/bin/pip install "ruamel.yaml.clib==0.2.14"
v/bin/python -c "import pkg_resources; pkg_resources.require('ruamel.yaml==0.18.6')"   # no error
```

With the toolchain: `python -m mpf_godot setup`, then `.venv/bin/mpf --version` runs.

## Upstream issue (draft, not filed)

**Title:** `mpf` fails with DistributionNotFound for ruamel.yaml.clib 0.2.15 when a plugin (mpf-monitor) is installed

**Body:**

```markdown
**Environment**
- MPF 0.80.1 (pins setuptools~=72.2.0, ruamel.yaml==0.18.6), mpf-monitor 1.0.0
- ruamel.yaml.clib 0.2.15 (what pip picks today), Python 3.11 (any Python before 3.13)
- Windows, macOS and Linux

**Steps to reproduce**
1. `python3.11 -m venv v && v/bin/pip install mpf==0.80.1 mpf-monitor==1.0.0`
2. `v/bin/mpf --version`

**Expected:** MPF starts.

**Actual:**
pkg_resources.DistributionNotFound: The 'ruamel.yaml.clib>=0.2.7; platform_python_implementation == "CPython"
and python_version < "3.13"' distribution was not found and is required by ruamel.yaml

Without mpf-monitor installed, `mpf` starts.

**Cause**
ruamel.yaml.clib 0.2.15 names its metadata `ruamel_yaml_clib-0.2.15.dist-info`. `mpf/commands/__init__.py`
loads `mpf.command` entry points with `pkg_resources.iter_entry_points()` and `entry_point.load()`, which
checks the plugin's full requirement tree; the pkg_resources of setuptools 72.2 does not match the new name to
`ruamel.yaml.clib`. The step alone:

    pip install "setuptools==72.2.0" "ruamel.yaml==0.18.6" "ruamel.yaml.clib==0.2.15"
    python -c "import pkg_resources; pkg_resources.require('ruamel.yaml==0.18.6')"   # DistributionNotFound

**Workaround:** `pip install "ruamel.yaml.clib==0.2.14"`.

**Proposed fix** (any one):
- Load plugin commands with `importlib.metadata.entry_points(group="mpf.command")` (Python 3.10+), which does
  no requirement check, and drop `pkg_resources` (also used in `mpf/core/machine.py` and
  `mpf/core/config_spec_loader.py`); or
- `entry_point.load(require=False)` in `mpf/commands/__init__.py`; or
- add `ruamel.yaml.clib<0.2.15; python_version < "3.13"` to MPF's requirements until then.
```
