<#
.SYNOPSIS
Installs MPF, MPF Monitor, Godot and GMC with our fixes on Windows 10/11, with Python 3.11 and Git when they are
missing (and the Visual C++ runtime with -Proc). Safe to re-run.

.DESCRIPTION
Uses winget (App Installer) when it is there, else the official installers from python.org and
git-for-windows. Python and Git are installed for the current user where possible. Windows PowerShell 5.1
or PowerShell 7. The one line (README) fetches and runs it; from a clone:

    powershell -ExecutionPolicy Bypass -File install\install_windows.ps1
    powershell -ExecutionPolicy Bypass -File install\install_windows.ps1 -NoMonitor
    powershell -ExecutionPolicy Bypass -File install\install_windows.ps1 -DryRun

Arguments that are not options of this script go to `python -m mpf_godot setup` (for example --extra pillow).
Never run it as `irm <url> | iex`: platforms/windows.md, "The one line".

.PARAMETER DryRun
Print the plan, change nothing.
.PARAMETER Monitor
Accepted for older command lines: MPF Monitor is installed by default.
.PARAMETER NoMonitor
Leave MPF Monitor out.
.PARAMETER Proc
The real machine on a P-ROC: also the Visual C++ 2015-2022 runtime that MPF's pypinproc needs, and a check for FTDI's D2XX driver.
.PARAMETER NoSetup
Prerequisites only, no `python -m mpf_godot setup`.
.PARAMETER NoWinget
Use the downloaded installers even when winget is there.
.PARAMETER Yes
No questions.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$DryRun,
    [switch]$Monitor,
    [switch]$NoMonitor,
    [switch]$Proc,
    [switch]$NoSetup,
    [switch]$NoWinget,
    [switch]$Yes,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$SetupArgs
)

$ErrorActionPreference = 'Stop'
# Run from a clone, it sets up that clone. Run on its own (the README's one line), it first clones the repository
# into $env:MPF_GODOT_DIR (default ~\MPF-Godot, outside OneDrive), branch $env:MPF_GODOT_BRANCH (default main), from
# $env:MPF_GODOT_REPO; an existing clone gets a git pull.
$Clone = -not ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot '..\mpf_godot\setup_toolchain.py')))
$Root = if (-not $Clone) { Split-Path -Parent $PSScriptRoot }
        elseif ($env:MPF_GODOT_DIR) { $env:MPF_GODOT_DIR } else { Join-Path $HOME 'MPF-Godot' }
$RepoUrl = if ($env:MPF_GODOT_REPO) { $env:MPF_GODOT_REPO } else { 'https://github.com/Ashram56/MPF-Godot-Packaging.git' }
$RepoBranch = if ($env:MPF_GODOT_BRANCH) { $env:MPF_GODOT_BRANCH } else { 'main' }

# The last Python 3.11 release with Windows installers (later 3.11 releases are source-only security fixes)
$PyOrgVersion = '3.11.9'
$GitVersion = '2.47.1'
$GitUrl = "https://github.com/git-for-windows/git/releases/download/v$GitVersion.windows.1/Git-$GitVersion-64-bit.exe"
$FtdiUrl = 'https://ftdichip.com/drivers/d2xx-drivers/'

$OnWindows = $env:OS -eq 'Windows_NT'
$Arm = $env:PROCESSOR_ARCHITECTURE -eq 'ARM64'
$PyOrgArch = if ($Arm) { 'arm64' } else { 'amd64' }
$PyOrgUrl = "https://www.python.org/ftp/python/$PyOrgVersion/python-$PyOrgVersion-$PyOrgArch.exe"
$VcArch = if ($Arm) { 'arm64' } else { 'x64' }
$VcUrl = "https://aka.ms/vs/17/release/vc_redist.$VcArch.exe"

function Write-Step([string]$Text) { Write-Host ''; Write-Host "==> $Text" }
function Write-Note([string]$Text) { Write-Host "    $Text" }

function Invoke-Step {
    param([string]$Exe, [string[]]$Arguments = @())
    Write-Host ('    $ ' + $Exe + ' ' + ($Arguments -join ' '))
    if ($DryRun) { return }
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed (exit code $LASTEXITCODE)" }
}

function Confirm-Step([string]$Question) {
    if ($DryRun -or $Yes) { return }
    $answer = Read-Host "    $Question [Y/n]"
    if ($answer -match '^[nN]') { throw 'cancelled' }
}

function Invoke-Installer {
    # Download an installer to %TEMP% and run it silently
    param([string]$Url, [string]$Arguments)
    $file = Join-Path ([IO.Path]::GetTempPath()) ([IO.Path]::GetFileName($Url))
    Write-Host "    download $Url"
    Write-Host "    $ $file $Arguments"
    if ($DryRun) { return }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $Url -OutFile $file -UseBasicParsing
    $p = Start-Process -FilePath $file -ArgumentList $Arguments -Wait -PassThru
    Remove-Item $file -ErrorAction SilentlyContinue
    # 3010: success, a reboot is pending; 1638: a newer version is already installed
    if ($p.ExitCode -notin 0, 3010, 1638) { throw "$file failed (exit code $($p.ExitCode))" }
}

function Test-Python([string]$Exe) {
    if (-not $Exe -or -not (Test-Path $Exe)) { return $false }
    & $Exe -c 'import sys, venv, ensurepip; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)' 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Find-Python {
    # The py launcher first (it knows every registered install), then the default install folders.
    # Never the bare "python": on a fresh Windows that is the Microsoft Store stub.
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $exe = & $py.Source -3.11 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Python $exe)) { return $exe }
    }
    $suffix = if ($Arm) { '-arm64' } else { '' }
    foreach ($dir in @("$env:LOCALAPPDATA\Programs\Python\Python311$suffix", "$env:ProgramFiles\Python311$suffix")) {
        $exe = Join-Path $dir 'python.exe'
        if (Test-Python $exe) { return $exe }
    }
    return $null
}

function Find-Git {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) { return $git.Source }
    foreach ($exe in @("$env:ProgramFiles\Git\cmd\git.exe", "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe")) {
        if (Test-Path $exe) { return $exe }
    }
    return $null
}

# This repository is public. A private fork of it ($env:MPF_GODOT_REPO) needs a GitHub token instead of a password:
# $env:MPF_GODOT_GITHUB_TOKEN (or GITHUB_TOKEN / GH_TOKEN), or pasted when asked. It is used for this run only
# (git's url.insteadOf in the environment) and handed to git's credential helper (Git Credential Manager), so
# later pulls work too. platforms/windows.md has why each step is there.
function Test-RepoAccess([string]$GitExe, [string]$Url, [switch]$Anonymous) {
    # no prompt of any kind: GIT_TERMINAL_PROMPT for git's own, GCM_INTERACTIVE for Git Credential Manager's
    # login window (it asks for a user and password, which GitHub then refuses for git)
    # Windows PowerShell 5.1 turns a redirected native command's stderr ("fatal: could not read Username") into
    # an error record, which 'Stop' makes fatal: only the exit code counts here
    $ErrorActionPreference = 'Continue'
    $env:GIT_TERMINAL_PROMPT = '0'
    $env:GCM_INTERACTIVE = 'never'
    try {
        if ($Anonymous) { & $GitExe -c credential.helper= ls-remote $Url HEAD *> $null }
        else { & $GitExe ls-remote $Url HEAD *> $null }
        return ($LASTEXITCODE -eq 0)
    } finally { Remove-Item Env:GIT_TERMINAL_PROMPT, Env:GCM_INTERACTIVE -ErrorAction SilentlyContinue }
}

function Clear-UntrackedInUpdate([string]$GitExe) {
    # Before a pull: files the update adds that are already here, untracked, would stop 'git pull' ("untracked
    # working tree files would be overwritten"). Godot writes a .uid next to every script it opens, so a new
    # script's .uid is often on disk before the commit that adds it. Remove those, and any copy identical to the
    # update's; move anything else aside as <file>.local so nothing of the player's is lost.
    $ErrorActionPreference = 'Continue'     # stderr is not an error here (see Test-RepoAccess)
    $up = (& $GitExe -C $Root rev-parse -q --verify '@{u}' 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $up) { return }
    $added = @(& $GitExe -C $Root -c core.quotepath=off diff --name-only --no-renames --diff-filter=A HEAD $up --)
    foreach ($f in $added) {
        if (-not $f) { continue }
        $path = Join-Path $Root $f
        if (-not (Test-Path -LiteralPath $path)) { continue }
        & $GitExe -C $Root ls-files --error-unmatch -- $f *> $null
        if ($LASTEXITCODE -eq 0) { continue }
        $generated = $f -match '\.(uid|import)$'
        $same = $false
        if (-not $generated -and (Test-Path -LiteralPath $path -PathType Leaf)) {
            $same = ((& $GitExe -C $Root hash-object -- $f) -eq (& $GitExe -C $Root rev-parse "${up}:$f"))
        }
        if ($generated -or $same) {
            Write-Host "    `$ Remove-Item $path"
            if (-not $DryRun) { Remove-Item -LiteralPath $path -Force }
        } else {
            Write-Note "kept your copy of $f as $f.local (the update adds its own)"
            Write-Host "    `$ Move-Item $path $path.local"
            if (-not $DryRun) { Move-Item -LiteralPath $path -Destination "$path.local" -Force }
        }
    }
}

function Invoke-GitHubAuth([string]$GitExe) {
    if (-not $Clone) { return }
    Write-Step 'GitHub access'
    $token = @($env:MPF_GODOT_GITHUB_TOKEN, $env:GITHUB_TOKEN, $env:GH_TOKEN) | Where-Object { $_ } | Select-Object -First 1
    if ($DryRun) {
        Write-Note '(dry run) a private repository asks for a GitHub token here'
        return
    }
    # only a repository nobody can read without a login gets the token: a token that cannot read a public
    # repository (a fine-grained one for other repositories, an expired one) would make git fail on it
    if (Test-RepoAccess $GitExe $RepoUrl -Anonymous) {
        Write-Note "$RepoUrl is public: no token needed"
        return
    }
    if (-not $token) {
        if (Test-RepoAccess $GitExe $RepoUrl) {
            Write-Note 'a private repository, readable with the GitHub credentials git already has'
            return
        }
        if ($Yes) { throw "$RepoUrl is private: set `$env:MPF_GODOT_GITHUB_TOKEN to a GitHub token that can read it" }
        Write-Note "Private: $RepoUrl"
        Write-Note 'Paste a GitHub token that can read it (github.com > Settings > Developer settings > Personal access'
        Write-Note 'tokens; a fine-grained token with Contents: read-only on this repository).'
        Write-Note 'Paste it with a right-click: Ctrl+V does not paste into this hidden prompt.'
        $secure = Read-Host '    token (not shown)' -AsSecureString
        $token = [System.Net.NetworkCredential]::new('', $secure).Password
    }
    # a token copied from a text editor can carry spaces or a line break; GitHub tokens have none
    $token = ($token -replace '\s', '')
    if (-not $token) { throw 'no token given' }
    $prefix = if ($token -match '^(github_pat_|gh[pousr]_)') { $Matches[1] } else { 'unknown' }
    Write-Note "token: $($token.Length) characters, type $prefix (a fine-grained token is about 93, a classic one 40)"
    $env:GIT_CONFIG_COUNT = '1'
    $env:GIT_CONFIG_KEY_0 = 'url.https://x-access-token:' + $token + '@' + $RepoUrl.Substring(8) + '.insteadOf'
    $env:GIT_CONFIG_VALUE_0 = $RepoUrl
    if (-not (Test-RepoAccess $GitExe $RepoUrl)) {
        throw "the GitHub token cannot read $RepoUrl (check its repository access and expiry)"
    }
    "protocol=https`nhost=github.com`nusername=x-access-token`npassword=$token`n" | & $GitExe credential approve 2>$null
    Write-Note 'token accepted'
}

function Test-VcRuntime {
    foreach ($key in @("HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\$VcArch",
                       "HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\$VcArch")) {
        $item = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
        if ($item -and $item.Installed -eq 1) { return $true }
    }
    return $false
}

try {
    if (-not $OnWindows) {
        if (-not $DryRun) { throw 'this script is for Windows (macOS and Linux: the install_prereqs_*.sh scripts)' }
        Write-Note 'not Windows: showing the plan only'
    }
    $winget = $null
    if (-not $NoWinget) { $winget = Get-Command winget -ErrorAction SilentlyContinue }
    $mode = if ($DryRun) { ', dry run' } else { '' }
    Write-Step "MPF + Godot prerequisites on Windows ($env:PROCESSOR_ARCHITECTURE$mode)"
    if ($winget) { Write-Note "winget: $($winget.Source)" } else { Write-Note 'winget: not used (downloaded installers)' }
    $wingetArgs = @('--exact', '--silent', '--accept-package-agreements', '--accept-source-agreements', '--source', 'winget')

    # ---------------------------------------------------------------- Git
    Write-Step 'Git'
    $git = Find-Git
    if ($git) {
        Write-Note "in place: $git"
    } else {
        Confirm-Step 'Install Git?'
        if ($winget) {
            Invoke-Step $winget.Source (@('install', '--id', 'Git.Git') + $wingetArgs)
        } else {
            Invoke-Installer $GitUrl '/VERYSILENT /NORESTART /NOCANCEL /SP- /SUPPRESSMSGBOXES'
        }
        $env:Path = "$env:ProgramFiles\Git\cmd;$env:Path"
        if (-not $DryRun -and -not (Find-Git)) { throw 'Git is still missing after the install' }
    }
    $authGit = Find-Git
    # the toolchain setup and later game set-ups run `git` from the PATH: a Git found only at its install folder
    # is put on this session's PATH
    if ($authGit -and -not (Get-Command git -ErrorAction SilentlyContinue)) {
        $env:Path = (Split-Path -Parent $authGit) + ';' + $env:Path
        Write-Note "Git added to this session's PATH: $(Split-Path -Parent $authGit)"
    }
    Invoke-GitHubAuth $(if ($authGit) { $authGit } else { 'git' })

    # ---------------------------------------------------------------- Python 3.11
    Write-Step 'Python 3.11'
    $python = Find-Python
    if ($python) {
        Write-Note "in place: $python"
    } else {
        Confirm-Step "Install Python $PyOrgVersion for this user?"
        if ($winget) {
            Invoke-Step $winget.Source (@('install', '--id', 'Python.Python.3.11', '--scope', 'user') + $wingetArgs)
        } else {
            Invoke-Installer $PyOrgUrl 'InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 /quiet'
        }
        if ($DryRun) {
            $python = 'py -3.11'
        } else {
            $python = Find-Python
            if (-not $python) { throw 'Python 3.11 is still missing after the install (open a new terminal and retry)' }
        }
        Write-Note "Python: $python"
    }

    # ---------------------------------------------------------------- PATH
    # winget's per-user Python and an older install may leave python.exe off PATH: put Python and its
    # Scripts folder first in the user PATH (ahead of the Microsoft Store "python" stub in WindowsApps)
    Write-Step 'Python 3.11 on the user PATH'
    $pyDir = if ($python -and (Test-Path $python)) { Split-Path -Parent $python } else { "$env:LOCALAPPDATA\Programs\Python\Python311" }
    $want = @($pyDir, (Join-Path $pyDir 'Scripts'))
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not $userPath) { $userPath = '' }
    $parts = @($userPath -split ';' | Where-Object { $_ } | ForEach-Object { $_.TrimEnd('\') })
    $missing = @($want | Where-Object { $parts -notcontains $_.TrimEnd('\') })
    if ($missing.Count -eq 0) {
        Write-Note "in place: $($want -join ';')"
    } else {
        Write-Note "add to the user PATH: $($missing -join ';')"
        if (-not $DryRun) {
            [Environment]::SetEnvironmentVariable('Path', ((@($missing) + $parts) -join ';'), 'User')
            $env:Path = ($missing -join ';') + ';' + $env:Path
            Write-Note 'done (terminals opened from now on see it; close and reopen this one)'
        }
    }

    # ---------------------------------------------------------------- long paths
    # Windows limits paths to 260 characters unless LongPathsEnabled is set (machine-wide, needs administrator);
    # pip, Godot's import cache and the asset submodule can go past it
    Write-Step 'Windows long path support'
    $fsKey = 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem'
    $longPaths = (Get-ItemProperty -Path $fsKey -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled
    if ($longPaths -eq 1) {
        Write-Note 'in place (LongPathsEnabled = 1)'
    } else {
        Confirm-Step 'Enable long paths? (machine setting: Windows asks for administrator rights)'
        $setCmd = "Set-ItemProperty -Path '$fsKey' -Name LongPathsEnabled -Value 1 -Type DWord"
        Write-Host "    $ $setCmd"
        if (-not $DryRun) {
            $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
                [Security.Principal.WindowsBuiltInRole]::Administrator)
            try {
                if ($admin) {
                    Invoke-Expression $setCmd
                } else {
                    Start-Process -FilePath 'powershell' -Verb RunAs -Wait -WindowStyle Hidden `
                        -ArgumentList @('-NoProfile', '-Command', $setCmd)
                }
            } catch {
                Write-Note "could not change it ($($_.Exception.Message))"
            }
            $longPaths = (Get-ItemProperty -Path $fsKey -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled
            if ($longPaths -eq 1) { Write-Note 'enabled' }
            else { Write-Note 'warning: still off; run this script once from an administrator PowerShell, or keep the repository in a short folder such as C:\mpf' }
        }
    }
    $gitExe = Find-Git
    if ($gitExe -and -not $DryRun) {
        $gitLong = & $gitExe config --global --get core.longpaths 2>$null
        if ($gitLong -ne 'true') { Invoke-Step $gitExe @('config', '--global', 'core.longpaths', 'true') }
        else { Write-Note 'git core.longpaths: in place' }
    } else {
        Write-Note '$ git config --global core.longpaths true'
    }

    # ---------------------------------------------------------------- P-ROC
    if ($Proc) {
        Write-Step 'Visual C++ 2015-2022 runtime (MPF''s pypinproc needs MSVCP140.dll)'
        if (Test-VcRuntime) {
            Write-Note 'in place'
        } elseif ($winget) {
            Invoke-Step $winget.Source (@('install', '--id', "Microsoft.VCRedist.2015+.$VcArch") + $wingetArgs)
        } else {
            Invoke-Installer $VcUrl '/install /quiet /norestart'
        }
        Write-Step 'FTDI D2XX driver (the P-ROC''s USB driver)'
        if (Test-Path "$env:SystemRoot\System32\ftd2xx.dll") {
            Write-Note 'in place (ftd2xx.dll)'
        } else {
            Write-Note "not found: install it from $FtdiUrl, then plug in the P-ROC"
        }
        if ($Arm) { Write-Note 'warning: MPF has no pypinproc for Windows on ARM; the P-ROC needs an x64 PC' }
    }

    # ---------------------------------------------------------------- repository (run on its own: clone it)
    if ($Clone) {
        Write-Step "Repository: $RepoUrl ($RepoBranch) in $Root"
        $gitExe = Find-Git
        if (-not $gitExe) { $gitExe = 'git' }
        if (Test-Path (Join-Path $Root '.git')) {
            # an existing clone: update its branch, or move to $RepoBranch when that branch is gone from GitHub
            # (a deleted pull-request branch) or none is checked out
            $cur = (& $gitExe -C $Root symbolic-ref --short -q HEAD 2>$null)
            $onRemote = $false
            if ($cur) {
                $ErrorActionPreference = 'Continue'     # stderr is not an error here (see Test-RepoAccess)
                & $gitExe -C $Root ls-remote --exit-code --heads origin $cur *> $null
                $onRemote = ($LASTEXITCODE -eq 0)
                $ErrorActionPreference = 'Stop'
            }
            if ($onRemote) {
                Invoke-Step $gitExe @('-C', $Root, 'fetch', 'origin')
                Clear-UntrackedInUpdate $gitExe
                Invoke-Step $gitExe @('-C', $Root, 'pull', '--ff-only')
            }
            else {
                Write-Note "branch '$(if ($cur) { $cur } else { 'none' })' is no longer on GitHub: switching to $RepoBranch"
                Invoke-Step $gitExe @('-C', $Root, 'fetch', '--prune', 'origin')
                Invoke-Step $gitExe @('-C', $Root, 'checkout', '-B', $RepoBranch, '--track', "origin/$RepoBranch")
            }
        }
        else { Invoke-Step $gitExe @('clone', '--branch', $RepoBranch, $RepoUrl, $Root) }
    }

    # ---------------------------------------------------------------- toolchain
    if ($NoSetup) {
        Write-Note "skipping the toolchain (-NoSetup): run  $python -m mpf_godot setup  in $Root when ready"
    } else {
        Write-Step 'MPF, MPF Monitor, Godot and GMC (python -m mpf_godot setup)'
        $cmdArgs = @('-m', 'mpf_godot', 'setup')
        if ($NoMonitor) { $cmdArgs += '--no-monitor' }
        if ($DryRun) { $cmdArgs += '--dry-run' }
        if ($SetupArgs) { $cmdArgs += $SetupArgs }
        Write-Host "    $ cd $Root"
        Write-Host ('    $ ' + $python + ' ' + ($cmdArgs -join ' '))
        if (-not $DryRun) {
            Push-Location $Root
            try {
                & $python @cmdArgs
                if ($LASTEXITCODE -ne 0) { throw "python -m mpf_godot setup failed (exit code $LASTEXITCODE)" }
            } finally { Pop-Location }
        }
    }

    $suffix = if ($DryRun) { ' (dry run: nothing was changed)' } else { '' }
    Write-Step "Done$suffix"
    if (-not $NoSetup) {
        $mon = if ($NoMonitor) { '' } else { ' [--monitor]' }
        Write-Note "Toolchain in ${Root}:"
        Write-Note "Paths and versions:  $Root\.venv\Scripts\python -m mpf_godot info"
        Write-Note "Into a game:         $Root\.venv\Scripts\python -m mpf_godot addons <game folder> [--video]"
        Write-Note "Start a game:        $Root\.venv\Scripts\python -m mpf_godot run <game folder>$mon"
    }
    exit 0
} catch {
    Write-Host ''
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
