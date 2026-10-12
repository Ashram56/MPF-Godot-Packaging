# P-ROC on Windows: "Could not import pinproc" without the VC++ runtime or FTDI's driver

| | |
|---|---|
| Id | `mpf/pinproc-windows-vcredist` (this file: `fixes/mpf/pinproc-windows-vcredist.md`) |
| Component | MPF (its bundled pypinproc for Windows) |
| Kind | packaging |
| Affected versions | MPF 0.80.1 (`mpf/platforms/pinproc/windows/pinproc.cp38..cp314-*.pyd`); and later until fixed upstream |
| Platforms | Windows x86_64 and x86; Windows on ARM (no build at all) |
| Found on | a Stern SAM recreation (Tron Legacy MPF), 2026-10-03 |
| Fact | code (the import table of `pinproc.cp311-win_amd64.pyd`); not run on a Windows PC with a board |
| Our fix | [`install/install_windows.ps1`](../../install/install_windows.ps1) `-Proc`: installs the Visual C++ 2015-2022 runtime (winget `Microsoft.VCRedist.2015+.<arch>`, else Microsoft's installer), checks for `ftd2xx.dll`, warns on ARM |
| Applied by | `install/install_windows.ps1 -Proc` (the D2XX driver stays a manual step: FTDI's download page) |
| Upstream | MPF, https://github.com/missionpinball/mpf/issues; status: **draft, not filed** |

## Problem

On a Windows PC without the Visual C++ runtime or FTDI's D2XX driver, MPF stops with
`Could not import "pinproc". Either the library is not installed or is missing some of its dependencies.`
The message does not say which DLL is missing. On Windows on ARM there is no pypinproc at all.

## Cause

- The `.pyd` imports `MSVCP140.dll`, `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll` (Visual C++ 2015-2022
  runtime) and `FTD2XX.dll` (FTDI's D2XX driver). Neither comes with Python nor with Windows; Python ships
  `vcruntime140.dll` but not `MSVCP140.dll`.
- `p_roc_common.py` catches the `ImportError` and keeps it as the `__cause__` of a generic `MpfRuntimeError`.
- MPF bundles `win32` and `win_amd64` builds only: no `win_arm64`.

## Fix

The Windows installer's `-Proc` installs the runtime (the arm64 runtime on ARM), checks for
`%SystemRoot%\System32\ftd2xx.dll` and points to https://ftdichip.com/drivers/d2xx-drivers/ when it is missing,
and warns that a P-ROC needs an x64 PC.

## How to check

`install_windows.ps1 -Proc -DryRun` prints the steps. Then `.venv\Scripts\python -c "from mpf.platforms.pinproc.windows import pinproc"`
imports; without the runtime it should fail with `ImportError: DLL load failed` (inferred from the import table, not run).

## Upstream issue (draft, not filed)

**Title:** Windows P-ROC: name the missing DLL (MSVCP140 / FTD2XX) and document the VC++ runtime

**Body:**

```markdown
**Environment**
- MPF 0.80.1, Windows 10/11 x64, Python 3.11, P-ROC

**Problem**
MPF's bundled `mpf/platforms/pinproc/windows/pinproc.cp3xx-win_amd64.pyd` imports MSVCP140.dll,
VCRUNTIME140.dll, VCRUNTIME140_1.dll and FTD2XX.dll. On a PC without the Visual C++ 2015-2022 runtime or
FTDI's D2XX driver, the import fails and MPF says only:
`Could not import "pinproc". Either the library is not installed or is missing some of its dependencies.`
There is also no win_arm64 build.

**Steps to reproduce**
1. Fresh Windows 10 x64 without the VC++ redistributable; `pip install mpf==0.80.1`
2. `python -c "from mpf.platforms.pinproc.windows import pinproc"` -> `ImportError: DLL load failed` (expected from the import table; we have not run this on a clean PC)

**Proposed fix**
1. Include the original ImportError text in the MpfRuntimeError message (`p_roc_common.py`), and add:
   "On Windows it needs the Visual C++ 2015-2022 runtime (https://aka.ms/vs/17/release/vc_redist.x64.exe) and
   FTDI's D2XX driver (https://ftdichip.com/drivers/d2xx-drivers/)."
2. The same two lines on the P-ROC install page.
3. Say on that page that Windows on ARM has no pypinproc build.
```
