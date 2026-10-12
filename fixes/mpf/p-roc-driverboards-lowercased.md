# `p_roc: driverboards: sternSAM` gives an unknown machine type

| | |
|---|---|
| Id | `mpf/p-roc-driverboards-lowercased` (this file: `fixes/mpf/p-roc-driverboards-lowercased.md`) |
| Component | MPF |
| Kind | bug |
| Affected versions | MPF 0.80.1 (and earlier 0.5x releases with the same validator, not checked); and later until fixed upstream |
| Platforms | all |
| Found on | a Stern SAM recreation (Tron Legacy MPF), 2026-10-03 |
| Fact | code (MPF 0.80.1 `config_validator.py` and `config_spec.yaml`; the strings of MPF's bundled pypinproc); not run on a P-ROC |
| Our fix | none in code: a game puts `driverboards:` under `hardware:` (example below) |
| Applied by | the game's config; nothing to apply |
| Upstream | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, not filed** |

## Problem

The documented `p_roc:` setting for the driver boards does not work for the mixed-case types:

```yaml
p_roc:
  driverboards: sternSAM        # reaches pypinproc as "sternsam"
```

pypinproc answers `Unknown machine type.  Expecting wpc, wpc95, sternSAM, sternWhitestar, or custom.` The same
holds for `wpcAlphanumeric` and `sternWhitestar`. `wpc`, `wpc95`, `pdb` and `custom` are already lowercase and work.

## Cause

- `mpf/config_spec.yaml` declares `p_roc: driverboards: single|enum(wpc,wpcAlphanumeric,wpc95,sternSAM,sternWhitestar,pdb,custom,None)|None`.
- `ConfigValidator._validate_type_enum()` (`mpf/core/config_validator.py`) lowercases both the allowed values and
  the item, and returns the lowercased string.
- `PRocHardwarePlatform.__init__()` (`mpf/platforms/p_roc.py`) passes it to `pinproc.normalize_machine_type()`,
  which compares names case-sensitively (`strcmp`), so `sternsam` is unknown.
- `hardware: driverboards` is `single|str|None`: not lowercased, so it works there. The P-ROC platform falls
  back to it when `p_roc: driverboards` is empty.

## Fix

The game sets the type under `hardware:`, where MPF keeps its case:

```yaml
hardware:
  platform: p_roc
  driverboards: sternSAM
```

## How to check

`mpf game . -c config,<proc overlay> -x` validates the config on virtual hardware. With the type under `p_roc:`,
print the validated value: `machine.config_validator.validate_config("p_roc", {"driverboards": "sternSAM"})`
returns `{"driverboards": "sternsam", ...}`. On a P-ROC, MPF then stops at `normalize_machine_type`.

## Upstream issue (draft, not filed)

**Title:** p_roc: driverboards is lowercased by the enum validator, pypinproc rejects sternSAM / sternWhitestar / wpcAlphanumeric

**Body:**

```markdown
**Environment**
- MPF 0.80.1, P-ROC platform, any OS (found by reading the code while configuring a Stern SAM machine; not yet run
  on a board)

**Steps to reproduce**

    hardware:
      platform: p_roc
    p_roc:
      driverboards: sternSAM

Start `mpf game` with a P-ROC connected.

**Expected:** machine type SternSAM.

**Actual:** `ConfigValidator._validate_type_enum()` returns the value lowercased (`sternsam`);
`PRocHardwarePlatform.__init__()` passes it to `pinproc.normalize_machine_type()`, which compares with `strcmp`
and raises "Unknown machine type.  Expecting wpc, wpc95, sternSAM, sternWhitestar, or custom."
Same for `wpcAlphanumeric` and `sternWhitestar`. Quick check without hardware:

    machine.config_validator.validate_config("p_roc", {"driverboards": "sternSAM"})["driverboards"]  # 'sternsam'

**Workaround:** put `driverboards: sternSAM` under `hardware:` (type `str`, not lowercased).

**Proposed fix** (any one):
- in `p_roc.py`, map the validated value back to pypinproc's spelling before `normalize_machine_type()`
  (also covers `hardware: driverboards: sternsam`);
- or make `_validate_type_enum()` return the allowed value in its declared case.

Sketch of the first:

    PROC_MACHINE_TYPES = {t.lower(): t for t in
                          ("wpc", "wpcAlphanumeric", "wpc95", "sternSAM", "sternWhitestar", "pdb", "custom")}
    value = self.config['driverboards'] or self.machine.config['hardware']['driverboards']
    self.machine_type = self.pinproc.normalize_machine_type(PROC_MACHINE_TYPES.get(str(value).lower(), value))
```
