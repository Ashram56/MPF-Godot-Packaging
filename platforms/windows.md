# Windows

Windows 10 (1809+) or 11, x86_64 or ARM64, Windows PowerShell 5.1 or PowerShell 7. Installer:
`install/install_windows.ps1`. Back to [all platforms](README.md).

## The one line

```powershell
powershell -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/Ashram56/MPF-Godot-Packaging/main/install/install_windows.ps1) -join [char]10))"
```

Options go at the end, inside the quotes: `... -join [char]10)) -NoMonitor -Proc"`. Settings go first:
`$env:MPF_GODOT_DIR = "C:\mpf"` (then the line). Never `irm <url> | iex` ([finding 1](#1-irm--iex-stops-on-line-1)).

From a clone: `powershell -ExecutionPolicy Bypass -File install\install_windows.ps1 [-DryRun] [-NoMonitor]`.

## Requirements

| Item | Value |
|---|---|
| OS | Windows 10 (1809+) or 11, 64-bit |
| CPU | x86_64; ARM64 works without GoZen and without the P-ROC |
| Graphics | Vulkan 1.0 or OpenGL 3.3 (Intel HD 4000 and newer, AMD GCN, NVIDIA Kepler) |
| Disk | about 2 GB free (3 GB with MPF Monitor) |
| Rights | a normal user; one administrator prompt to turn on long paths |
| Network | first setup only: pypi.org, files.pythonhosted.org, github.com, raw.githubusercontent.com, python.org or winget |

## What the installer does

| Step | What | How |
|---|---|---|
| 1 | Check the OS | not Windows: only `-DryRun` is allowed, which prints the plan |
| 2 | Pick the route | `winget` when it is there (unless `-NoWinget`), else downloaded installers |
| 3 | Git | `Find-Git` (PATH, `%ProgramFiles%\Git\cmd`, `%LOCALAPPDATA%\Programs\Git\cmd`); else `winget install Git.Git`, else Git for Windows 2.47.1 (`/VERYSILENT`). A Git found only in its folder goes on this session's PATH |
| 4 | GitHub access | `Invoke-GitHubAuth`: only when cloning; a public repository needs nothing; a private fork asks for a token |
| 5 | Python 3.11 | `Find-Python`: the `py -3.11` launcher, then `%LOCALAPPDATA%\Programs\Python\Python311[-arm64]`, `%ProgramFiles%\Python311[-arm64]`; else `winget install Python.Python.3.11 --scope user`, else python.org 3.11.9 (`InstallAllUsers=0 PrependPath=1 Include_launcher=1`) |
| 6 | User PATH | Python's folder and its `Scripts` put first in the user PATH, ahead of the Store stub |
| 7 | Long paths | `LongPathsEnabled = 1` (elevated PowerShell when not administrator) and `git config --global core.longpaths true` |
| 8 | P-ROC (`-Proc`) | Visual C++ 2015-2022 runtime (`winget Microsoft.VCRedist.2015+.x64`/`arm64`, else `vc_redist`); checks `ftd2xx.dll` (FTDI D2XX driver, installed by hand) |
| 9 | Repository | clone into `MPF_GODOT_DIR`; an existing clone: `Clear-UntrackedInUpdate`, then `git pull --ff-only`, or switch to `MPF_GODOT_BRANCH` when its branch is gone |
| 10 | Toolchain | `python -m mpf_godot setup` with `--no-monitor`, `--dry-run` and the extra arguments |
| 11 | Done | prints `.venv\Scripts\python -m mpf_godot info`, `addons`, `run` |

Installer exit codes 0, 3010 (reboot pending) and 1638 (newer version present) count as success
(`Invoke-Installer`).

## Options

| Option | Effect |
|---|---|
| `-DryRun` | print the plan, change nothing |
| `-NoMonitor` | leave MPF Monitor out (`-Monitor` is accepted for older command lines) |
| `-Proc` | the Visual C++ runtime and the FTDI D2XX check for a P-ROC |
| `-NoSetup` | prerequisites only, no `python -m mpf_godot setup` |
| `-NoWinget` | downloaded installers even when winget is there |
| `-Yes` | no questions (a private fork then needs `MPF_GODOT_GITHUB_TOKEN`) |
| anything else | passed to `python -m mpf_godot setup` (for example `--extra pillow`) |

| Environment | Default | Meaning |
|---|---|---|
| `MPF_GODOT_DIR` | `%USERPROFILE%\MPF-Godot` | clone folder; keep it out of OneDrive and short |
| `MPF_GODOT_BRANCH` | `main` | branch |
| `MPF_GODOT_REPO` | this repository | repository to clone |
| `MPF_GODOT_GITHUB_TOKEN` | unset (`GITHUB_TOKEN`, `GH_TOKEN`) | token for a private fork |
| `GODOT` | unset | a Godot 4.6.x installed by hand instead of the downloaded one |
| `GOZEN_HWDEC` | unset | at run time: `0` software decoding, `d3d11va` or `dxva2` only that one |

`MPF_GODOT_HWDEC` is for the Jetson only and has no effect here.

## Findings

### 1. `irm | iex` stops on line 1
- **Problem:** `irm <url> | iex` failed with "the terminator #> is missing from the multiline comment".
- **Cause:** Windows PowerShell ran the downloaded script line by line, so the comment-based help block was
  never closed (reproduced with `Get-Content <script> | iex` in pwsh).
- **Fix:** the one line builds one script block: `& ([scriptblock]::Create((irm URL) -join [char]10))`, which
  works whether `irm` returns one string or lines. The script's help says never to pipe it to `iex`.
- **Versions:** Windows PowerShell 5.1; checked as a dry run with pwsh 7.4.
- **Found:** 2026-10-10, observed (on a Transformers MPF owner's PC; fix found on Tron Legacy MPF, commit 37ef409).

### 2. A stray argument binds to a named parameter
- **Problem:** in the one line's `& ([scriptblock]::Create(...))` form, a bare extra argument meant for setup
  bound to a string parameter of the script.
- **Cause:** PowerShell binds positional arguments to parameters by default; `ValueFromRemainingArguments` does not
  stop it.
- **Fix:** `[CmdletBinding(PositionalBinding = $false)]` at the top of `install/install_windows.ps1`; leftovers go
  to `$SetupArgs`. Keep it when adding a string parameter.
- **Versions:** verified with pwsh 7.4 on Linux; a `-File` run did not show it.
- **Found:** 2026-10-10, observed (found on Tron Legacy MPF).

### 3. Windows PowerShell 5.1 turns git's stderr into a fatal error
- **Problem:** the access check stopped the installer on "fatal: could not read Username".
- **Cause:** with `$ErrorActionPreference = 'Stop'`, PowerShell 5.1 makes a redirected native command's stderr a
  terminating error record.
- **Fix:** `'Continue'` around git calls and the exit code only: `Test-RepoAccess`, `Clear-UntrackedInUpdate`
  and the branch check in the repository step.
- **Versions:** Windows PowerShell 5.1 (PowerShell 7 does not do this).
- **Found:** 2026-10-05, observed (found on Tron Legacy MPF).

### 4. Git Credential Manager opens a login window
- **Problem:** the private-repository check opened GCM's login window, which asks for a user and password that
  GitHub then refuses for git.
- **Cause:** GCM is git's credential helper on Windows and prompts on any failed read.
- **Fix:** `Test-RepoAccess` sets `GIT_TERMINAL_PROMPT=0` and `GCM_INTERACTIVE=never` for the check, and tests
  anonymously first with `-c credential.helper=`.
- **Versions:** Git for Windows with GCM.
- **Found:** 2026-10-04, observed (found on Tron Legacy MPF).

### 5. Ctrl+V does not paste the token
- **Problem:** at the hidden token prompt, Ctrl+V did nothing.
- **Cause:** `Read-Host -AsSecureString` in the classic console does not take Ctrl+V in every console.
- **Fix:** the prompt in `Invoke-GitHubAuth` says to paste with a right-click; the token is stripped of
  whitespace and its length and type are printed (never the token).
- **Versions:** Windows PowerShell console.
- **Found:** 2026-10-07, observed (owner test on Windows, Tron Legacy MPF).

### 6. Git just installed is not on the PATH
- **Problem:** setup, which runs `git`, failed right after Git was installed.
- **Cause:** the installer updates the PATH for new terminals, not for the running session.
- **Fix:** `$env:Path` gets Git's folder (`%ProgramFiles%\Git\cmd`, or the folder `Find-Git` found) in the Git step.
- **Versions:** all.
- **Found:** 2026-10-05, observed (found on Tron Legacy MPF).

### 7. The bare `python` is the Microsoft Store stub
- **Problem:** on a fresh Windows, `python` opens the Store instead of running Python.
- **Cause:** `WindowsApps\python.exe` is an App Execution Alias.
- **Fix:** `Find-Python` never calls the bare `python`: the `py -3.11` launcher, then the default install
  folders. Step 6 puts the real Python first in the user PATH.
- **Versions:** Windows 10 and 11.
- **Found:** 2026-10-03, code (found on Tron Legacy MPF).

### 8. winget's per-user Python is not on the PATH
- **Problem:** after `winget install Python.Python.3.11 --scope user`, `python` and `pip` were not found in a new
  terminal.
- **Cause:** winget's per-user install does not prepend Python to the PATH.
- **Fix:** step 6 adds Python's folder and `Scripts` to the user PATH (`[Environment]::SetEnvironmentVariable`)
  and to this session. Open a new terminal afterwards.
- **Versions:** winget; Python 3.11.9 is the last 3.11 release with a Windows installer.
- **Found:** 2026-10-03, observed (found on Tron Legacy MPF, commit e18dbb6).

### 9. Paths over 260 characters
- **Problem:** pip, Godot's import cache and deep git trees can pass Windows' 260-character limit.
- **Cause:** `LongPathsEnabled` is off by default, and git has its own `core.longpaths`.
- **Fix:** step 7: `LongPathsEnabled = 1` through one elevated PowerShell, and `git config --global
  core.longpaths true`. When it stays off the installer says to keep the clone in a short folder such as `C:\mpf`.
- **Versions:** Windows 10 1607+ for the setting.
- **Found:** 2026-10-03, code (found on Tron Legacy MPF).

### 10. OneDrive: deletes and renames fail for a moment
- **Problem:** setup failed with `FileExistsError` or `PermissionError` in a folder synced by OneDrive.
- **Cause:** a folder can still "exist" just after `rmtree` returns, and files there can be read-only or held
  while OneDrive syncs them.
- **Fix:** every build-time folder wipe, copy and rename goes through `mpf_godot/fsutil.py` (`remove_dir`,
  `clear_dir`, `replace`, `copy_file`, `copy_tree`): retries for about 5 s and clears the read-only flag. The
  default install folder is outside OneDrive.
- **Versions:** Windows with OneDrive folder backup (Documents, Desktop).
- **Found:** 2026-10-04, observed (found on Tron Legacy MPF, commit 182408d).

### 11. A video add-on folder Windows will not remove
- **Problem:** re-running setup over an add-on folder failed when Windows held a file in it (a loaded DLL).
- **Cause:** a DLL Godot has loaded cannot be deleted while Godot runs, and OneDrive holds files.
- **Fix:** the add-on copy uses `fsutil.copy_tree`, which copies over what will not go (`mpf_godot/__main__.py`,
  `addons()`).
- **Versions:** all.
- **Found:** 2026-10-04, observed (found on Tron Legacy MPF, commit 6bdb035).

### 12. MPF never started: Godot listens on IPv6 only
- **Problem:** the launcher waited forever for GMC's port, so MPF never started.
- **Cause:** Godot listens on an IPv6 socket that on Windows leaves IPv4 free; the port probe only tried IPv4.
- **Fix:** `mpf_godot/launcher.py`, `port_in_use()`: binds on IPv4 and IPv6 (`IPV6_V6ONLY`), with
  `SO_EXCLUSIVEADDRUSE` on Windows; it binds, never connects, because GMC quits when a client hangs up.
- **Versions:** Godot 4.x on Windows.
- **Found:** 2026-10-03, observed (found on Tron Legacy MPF, commit e18dbb6).

### 13. P-ROC on Windows: VC++ runtime and D2XX
- **Problem:** `--hw proc` needs MPF's bundled `pinproc.cp3xx-win_amd64.pyd`, which loads only with
  `MSVCP140.dll` and FTDI's `ftd2xx.dll`.
- **Cause:** neither is part of a fresh Windows.
- **Fix:** `-Proc` installs the Visual C++ 2015-2022 runtime (`Test-VcRuntime` reads the registry) and checks
  `%SystemRoot%\System32\ftd2xx.dll`; the D2XX driver comes from ftdichip.com by hand. Windows on ARM: no
  pypinproc build, the installer warns.
- **Versions:** MPF 0.80.1 ships pypinproc for Python 3.8 to 3.14, x64 and 32-bit.
- **Found:** 2026-10-03, code (found on Tron Legacy MPF). Not run on a real P-ROC from Windows in the sources.

### 14. Video: GoZen with GPU decoding, native_video as the fallback
- **Problem:** videos through the native_video add-on (Media Foundation) stuttered.
- **Cause:** not investigated further; GoZen gave smooth playback with the GPU.
- **Fix:** GDE GoZen built for Windows x86_64 (MinGW-w64 cross build, one static DLL,
  `addons/gde_gozen/bin/libgozen.windows.template_release.x86_64.dll`) with FFmpeg's Direct3D 11 Video, else DXVA2,
  decoding; native_video stays beside it as the fallback. `GOZEN_HWDEC=0` forces software.
  [../fixes/gde-gozen/d3d11va-dxva2-windows.md](../fixes/gde-gozen/d3d11va-dxva2-windows.md).
- **Versions:** Godot 4.6.3, FFmpeg 7.1; tested on a Ryzen 7800X3D with d3d11va.
- **Found:** 2026-10-10, observed (owner decision and test on Tron Legacy MPF, PR #15).

### 15. native_video crashed or failed to open videos
- **Problem:** 21 to 24 of 80 opens failed (panic, `OpenFailed`, heap corruption `0xC0000374`).
- **Cause:** gdzig's `engine_allocator` under-allocated aligned blocks, so a wide-string NUL terminator overran the
  block by 2 bytes.
- **Fix:** the add-on rebuilt with a fixed `heap.zig` (`addons/native_video/FIX.md`): 0 failures in 80. The arm64
  and x86_32 Windows DLLs were not rebuilt with it (FIX.md), so Windows on ARM may still have the bug (inferred).
- **Versions:** native_video v0.3.1, gdzig 14458fb, Godot 4.6.
- **Found:** 2026-09-30, observed.

### 16. pywin32 COM server: DLL error
- **Problem:** a game that registers a COM server with pywin32 (a VPX bridge) got "cannot load ... DLL error".
- **Cause:** pywin32's DLLs are not registered when it comes from pip into a venv.
- **Fix:** once, as Administrator: `.venv\Scripts\python .venv\Scripts\pywin32_postinstall.py -install`. Register
  the COM server from an Administrator terminal too. Not part of this installer.
- **Versions:** pywin32 from pip.
- **Found:** 2026-10-04, code (Tron Legacy MPF `docs/vpx.md`).

### 17. Firewall prompt
- **Problem:** Windows asks to let Godot and Python through the firewall.
- **Cause:** GMC listens on TCP 5050, MPF's BCP server for MPF Monitor on 5051.
- **Fix:** "Private networks" is enough: everything talks over localhost.
- **Versions:** all.
- **Found:** 2026-10-03, observed (found on Tron Legacy MPF).
