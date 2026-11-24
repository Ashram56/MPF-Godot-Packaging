# Agent F: packaging (install and run on every platform)

> **Feed back what you learn.** Whatever game you run this agent on, report every game-agnostic learning to
> Ashram56/MPF-Godot-Packaging (this repository) in the same session, without being asked: a pull request if you
> have write access, otherwise a GitHub issue opened directly. How and what: [CONTRIBUTING.md](../CONTRIBUTING.md).
> **Route it:** MPF implementation learnings (rules, display, sound, VPX bridge, PuP, install kit, Godot, GoZen,
> GMC, MPF, platforms and boards) stay here. Taking a ROM or a VPX table apart (formats, decompile, traces, IO
> tables) goes to [Ashram56/Stern-SAM-Decryption](https://github.com/Ashram56/Stern-SAM-Decryption) instead (its
> CONTRIBUTING.md), with at most a pointer here.

Make the game installable and runnable by the owner on every platform the master plan targets, with **one
line to install** and **one command to run** per platform: Windows, macOS, Linux, plus the options for each
hardware target (virtual + MPF Monitor, the real machine on a P-ROC, Visual Pinball X). Part of the
[master plan](README.md) (A to G in full: [Stern-SAM-Decryption `agents/README.md`](https://github.com/Ashram56/Stern-SAM-Decryption/blob/main/agents/README.md)). Tron Legacy MPF ([Tron-Legacy-MPF](https://github.com/Ashram56/Tron-Legacy-MPF)) is the worked example: copy its
scripts, rename, and keep them in step. File paths in `code` are the Tron game repo's ([Tron-Legacy-MPF](https://github.com/Ashram56/Tron-Legacy-MPF)) unless said otherwise.

"Packaging" here is the game's **install and run kit**. It is not the ROM extraction's MPF asset package
(`mpf_package/`, agent A's `AGENTS.md` section 10) and not the game itself (agent C).

> **Routing rule (Vincent, 2026-11-23):** the ROM and VPX table extraction (agents A and B, decompile, traces, IO
> tables) lives in Stern-SAM-Decryption; the MPF implementation (agents C to G, the install kit, MPF, Godot, GMC,
> platforms, boards) lives here, in MPF-Godot-Packaging.
>
> **The game-agnostic kit:** this repository installs
> MPF, MPF Monitor, Godot and the patched GMC with one line per OS (Jetson included), documents every fix to MPF,
> GMC, Godot and the video add-ons one file each with an upstream issue draft (`fixes/`), and every platform finding
> (`platforms/`). Take new pins, patches and installer lessons from there and add new ones there; a game's kit
> (below) keeps only what is the game's own. A game can point its launcher at that toolchain (`GODOT`, the venv) or
> copy the patched GMC with `python -m mpf_godot addons GAME` (2026-10-12).

## 1. What this agent owns

Every file below is this agent's, in the game repo. Other agents may add a feature flag to `setup.py` or
`run.py` for their own work (C: `--hw proc`, `--machine le`; D: `--hw vpx`, `--vpx`; E: `--dmd ...`); this agent
then carries it into every installer, the one-line commands, Docker, CI and the docs, on every platform.

| File (Tron) | What it does |
|---|---|
| `scripts/toolchain.py` | the pinned versions (Python, MPF, Godot, GMC, MPF Monitor, extra packages per option) and every per-OS path; standard library only |
| `scripts/setup.py` | the workspace on any OS: assets submodule, `.venv/`, Godot for the host, GMC (patched), MPF Monitor and its missing `.ui` files, generated config and media, Godot import. Idempotent; `--dry-run`, `--os/--arch` plan for another host; `--no-monitor`, `--vpx`, `--scorbit` (Scorbit SDK wrapper + its Linux-only native library, improvement.md 2b), `--skip-godot`, `--skip-media`, `--upgrade` |
| `scripts/run.py` | starts Godot (GMC, BCP 5050) first, then MPF, optionally MPF Monitor; one option per hardware target (`--hw virtual/proc/vpx`, `--machine`, `--monitor`); stale media regenerated on launch; Xvfb on Linux without a display |
| `scripts/install/install_prereqs_windows.ps1` | Windows 10/11, PowerShell 5.1 or 7: Git, Python 3.11 (winget or the official installers), long paths, the clone, `setup.py`; `-Proc` (VC++ runtime, FTDI check). Transformers adds `-Vpx` / `-Table` (section 4) |
| `scripts/install/install_prereqs_macos.sh` | macOS 12+, Intel or Apple silicon: Homebrew or python.org 3.11, Git, `setup.py`; `--proc` |
| `scripts/install/install_prereqs_linux.sh` | apt, dnf, pacman; x86_64 or arm64; Python 3.11 from the distribution, deadsnakes or uv; Qt and Xvfb libraries; `--proc` builds the driver and installs the udev rule |
| `scripts/install/build_pinproc.sh`, `99-pinproc.rules` | libpinproc and pypinproc from pinned commits (Linux, macOS) |
| `scripts/setup.bat`, `setup.ps1`, `setup_workspace.sh` | thin wrappers that find Python and run `setup.py` |
| `docker/` | Linux alternative: one image, compose services (setup, godot, mpf, monitor), overlays for GPU, audio, P-ROC; `docker/tron.sh` |
| `.github/workflows/test.yml` | CI on Windows, macOS and Linux: `setup.py`, `pytest`, render check on Linux; pushes to `main` only |
| `tests/test_install.py`, `tests/test_toolchain.py` | installers in `--dry-run`, standalone clone, private-repo token flow, Docker plans, toolchain paths, `run.py` arguments |
| Docs: the whole README (section 3, item 7), `docs/requirements.md`, `docs/development.md` "Getting started", `docker/README.md`, the set-up parts of `docs/vpx.md` and `docs/hardware.md` (P-ROC driver) | what the owner reads to install and start the game |

## 2. Inputs

- The game repo from agent C, once its toolchain step boots MPF + GMC (playbook section 4, step 1).
- The asset repo's location and visibility (submodule at `assets/`, or a folder in the game repo: Transformers
  keeps the ROM extraction in `rom/`, so it has no second repository to check).
- The owner's hardware line from the kickoff message (desktop, VPX, P-ROC, ...): which options to build.
- D's bridge (`vpx_bridge.py --register`, `vpx_table.py`) and E's display options, as they land.

## 3. Definition of done

1. **One line to install, per platform**, given in the README, that works on a computer with nothing
   installed. It installs what is missing (Git, Python 3.11, system libraries), clones the repo (or pulls an
   existing clone), runs `setup.py`, and ends by printing the run command. Tron:

   ```powershell
   powershell -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/<owner>/<repo>/main/scripts/install/install_prereqs_windows.ps1) -join [char]10))"
   ```
   ```sh
   bash <(curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/scripts/install/install_prereqs_macos.sh)   # or ..._linux.sh
   ```

   Options go at the end of the Windows line: `... -join [char]10)) -Vpx -Table '<table.vpx>'"`. **Never
   `irm <URL> | iex`**: on the Transformers owner's Windows PowerShell it ran the script line by line and stopped
   on line 1 ("the terminator #> is missing from the multiline comment"; reproduced in pwsh with
   `Get-Content <script> | iex`, observed 2026-10-10). The `-join [char]10` makes one script whether `irm` returns
   a string or lines; dry-run the README's exact line with pwsh before publishing it.
2. **One command to run**, per platform and target, from the install folder:
   `.venv\Scripts\python scripts\run.py [--monitor | --hw proc | --hw vpx]` (Windows), `.venv/bin/python
   scripts/run.py ...` (macOS, Linux). The installer prints it at the end, with the options it was given.
3. **Every option on every installer** the platform can support: dry run (plan only, changes nothing), no
   questions, no MPF Monitor, P-ROC, VPX (Windows only: VPX runs only there), prerequisites only, and
   pass-through arguments to `setup.py`. The same names everywhere (`--dry-run` / `-DryRun`, and so on).
4. **Safe to re-run**: every step is skipped when in place; a second run updates the clone and redoes only
   what changed. A clone whose branch was deleted on GitHub (a merged PR) moves to the default branch.
   Before the pull, fetch and clear the files the update adds that already sit untracked in the clone, or
   `git pull` aborts ("untracked working tree files would be overwritten"): Godot writes a `.uid` next to each
   script and shader it opens, so a player's PC often has one before the commit that tracks it. Remove Godot's
   `.uid`/`.import` files and identical copies, move anything else to `<file>.local`, never delete a user's
   file. Commit every `.uid` with its script; ignore `.import`. Observed on Tron, 2026-10-10:
   `game/tools/bake_fonts.gd.uid` stopped the Windows update (Tron-Legacy-MPF PR #43 has the bash and
   PowerShell functions).
5. **Settings by environment**, one prefix per game (Tron `TRON_`, Transformers `TF_`): `<P>_DIR` (install
   folder), `<P>_BRANCH`, `<P>_REPO`, `<P>_ASSETS_REPO` when there is a second repository, `<P>_GITHUB_TOKEN`.
6. **Tests**: every installer runs in its dry-run mode in `tests/test_install.py` (Linux families, macOS plan,
   standalone clone, branch gone, token flow); `pytest -q tests` green before pushing.
7. **A full README** at the game repo's root, the player's front page, owned by this agent (Tron's
   [README.md](https://github.com/Ashram56/Tron-Legacy-MPF/blob/main/README.md) is the model; Transformers-MPF's
   follows it). In this order: what the game is (game, model, ROM version, MPF / GMC / Godot versions, the
   platforms) and a pointer to the master plan; **Install** (the one line per platform, Windows with VPX when
   D's bridge exists; folder, branch, token and pack-zip settings; the options; clone-first fallback);
   **Play** (the run command per platform and target, free play, the key table from `gmc.cfg`); **Settings**
   (every `run.py` option and environment override); optional parts (PuP Pack with its author named, VPX);
   the status table; **Update**; **Tests**; **More** (links to every doc in `docs/`, the asset package);
   **Credits** (the manufacturer, pack and table authors, MPF, Godot). Plus `docs/requirements.md` per OS. A
   game's README that is only a status page is not done: on Transformers it had no macOS / Linux line and no
   Play or Settings section until the owner asked (2026-10-10).
8. **Docs** say the one line, the run command, the options and the requirements, in the owner's words, and are
   updated in the same change as any installer or `run.py` option.

## 4. Porting the kit to a new game

On Transformers the kit was not ported with the game: its VPX bridge thread had to port the Windows installer
by hand to give the owner a one-line VPX set-up (Transformers-MPF commit 85e87a3). Port it all at once, as
soon as the game repo exists:

1. Copy `scripts/toolchain.py`, `setup.py`, `run.py`, `fsutil.py`, `gmc_patch.py`, `scripts/install/`, the
   wrappers, `docker/`, the CI workflow and `tests/test_install.py` / `test_toolchain.py`.
   `gmc_patch.py` must also accept the GMC that a platform image provides (MPF-Godot-Packaging, `platform_addons: ["mpf-gmc"]`):
   it carries the same fixes under the tag `# mpf-godot fix`, so a file with that tag counts as patched (Transformers
   `PLATFORM_TAGS`, `scripts/gmc_patch.py`); else run.py stops with "unexpected scripts/bcp_server.gd". A bundle without
   GMC needs a Godot re-import after the platform installs it (Godot's class cache is empty otherwise): the platform loader does it.
2. Rename, in one block at the top of each installer: the environment prefix, repository URL, default
   branch, install folder name (`~/Tron-Legacy-MPF`), the assets repository (or drop that check when there
   is none), the banner text, the short-path hint (`C:\tron`), the Docker image and service names, the COM
   ProgID (`TronMPF.Controller`).
3. **Default branch**: a repository without `main` yet (Transformers, during the build) needs the working
   branch as the default and in the raw URL of the one line; switch both to `main` once it exists (Transformers:
   2026-10-10, together with `docs/vpx.md`'s line). Also set `main` as the GitHub default branch (Settings >
   General): only the owner can, and until then `raw.githubusercontent.com/<repo>/HEAD/...` and the repo page
   show the old branch.
4. **VPX set-up on Windows** (Transformers, worth porting back to Tron): `-Vpx` runs `setup.py --vpx` (olefile,
   pywin32), registers the COM server elevated (`Start-Process ... -Verb RunAs -Wait`, then check the exit
   code; the rest of the script stays unelevated), and with `-Table <path>` writes the table's `.vbs` with
   `vpx_table.py` (the `.vpx` itself is never changed). The final notes add the `run.py --hw vpx` line.
   `-Table` is a string parameter next to the `ValueFromRemainingArguments` pass-through, so the script needs
   `[CmdletBinding(PositionalBinding = $false)]`: without it, in the one line's `& ([scriptblock]::Create(...))`
   form, a bare extra argument binds to `-Table` (verified with pwsh 7.4 on Linux; a `-File` run did not show it).
   Dry-run the published one line with pwsh on Linux (the linux-x64 tarball runs from the scratchpad).
5. Run every installer with its dry-run option and the tests; on Windows, ask the owner to run the one line
   (`-DryRun` first) and report the output.

## 5. Learned so far

- **Private repositories**: test read access anonymously first (`git -c credential.helper= ls-remote`), then
  ask for a fine-grained GitHub token (Contents: read-only) and pass it to git for this run only (`url.insteadOf`
  in the environment, inherited by `setup.py`), and hand it to the credential helper for later pulls. Never
  open Git Credential Manager's window. A private repository answers 404 to `curl`/`irm` without a token, so
  the one line cannot fetch itself: document clone-then-run for that case.
- **Testing the token step on macOS CI**: run it with `GIT_CONFIG_NOSYSTEM=1` as well as a temporary HOME.
  Homebrew git's system config sets `credential.helper=osxkeychain`, which hangs in `git credential approve` when
  HOME has no keychain, so the test times out on `macos-latest` only (observed, Transformers `tests/test_install.py`
  `test_github_auth`, red on every main push from 2026-10-10 until the fix, 2026-10-22).
- **A private pack repository next to a public game**: when the only private repository is an optional one
  (Transformers: the PuP Pack's submodule, the owner's copy), the token step must not stop the install. With no
  token, `--yes`, an empty answer or a token that cannot read it, say the game installs without that part and
  go on; skip the check entirely when the pack comes from its zip (`<P>_PUP_ZIP`) or is off (`<P>_PUP=0`).
  `setup.py` must already treat a failed submodule fetch as "without the PuP", not an error. Test each case in
  `test_install.py` (Transformers-MPF's `test_github_auth`).
- **Run this agent, not only its file**: on Transformers the packaging thread wrote this file but the kit was
  never ported (only the Windows installer existed, from the VPX bridge thread) until the owner asked for the
  README. The coordinator starts F on the game as soon as C boots, per the master plan's section 3.
- **Windows PowerShell 5.1** turns a native command's stderr into a terminating error under
  `$ErrorActionPreference = 'Stop'`: run git quietly and test `$LASTEXITCODE` only.
- **Never the bare `python` on Windows**: on a fresh install it is the Microsoft Store stub. Use the `py`
  launcher, then the default install folders.
- **Long paths**: turn on `LongPathsEnabled` (needs administrator once), or keep the clone in a short folder.
- **OneDrive**: deletes and renames fail transiently; every build-time file operation goes through
  `scripts/fsutil.py`, and the default install folder is outside OneDrive.
- **Pins and launch order**: every pin carries its reason in `toolchain.py` (the playbook's toolchain table
  lists them: `ruamel.yaml.clib`, MPF Monitor's missing `.ui` files, Godot from GitHub releases); probing
  GMC's port and the start order are in the playbook's section 6 (MPF, GMC). Re-read both before changing
  `setup.py` or `run.py`.
- **macOS and Linux one lines** use `bash <(curl ...)`, not `curl | bash`, so the script keeps the terminal as
  stdin for its questions and takes options after the line (inferred from the scripts' prompts).
- **Third-party packs install from their author's zip**: a game that plays a PuP Pack takes it from the zip the
  author publishes, as an option of setup and of every installer (Tron: `TRON_PUP_ZIP`, `--pup-zip`, `-PupZip`;
  the [PuP Pack agent](pup_pack.md), section 2), and the README names the author next to it. With a zip the
  installers skip the pack repository's token check; without one, see "A private pack repository next to a public
  game" above (Tron: the pack's repository joins the check only with a token given or credentials that read it). Windows installer parameters need
  `[CmdletBinding(PositionalBinding = $false)]` once a string parameter is added, or a stray setup argument binds to
  it. (verified 2026-10-10 with pwsh 7.4 on Linux)
- **CI runs only on pushes to `main`**: test the installers locally in dry-run mode; on Windows only the
  owner can run them for real.
- **Pasting a token on Windows**: in the PowerShell / cmd console, paste with a right-click; Ctrl+V did nothing at
  the installer's token prompt (observed, Tron owner test on Windows). Say so next to the prompt in the README.
- **Release tags from a cloud session**: the session's git proxy refuses tag pushes (403), so the owner creates
  the tag on GitHub or from a clone (observed, Tron-Legacy-MPF-PuP `jetson-agx-orin-l4t-r36.4.3`). Name the tag and
  the commit in the report.

- **A thin kit on the platform** (Terminator 2, 2026-11-21: Ashram56/Terminator-2-Decryption `scripts/`, private):
  a new game need not copy Tron's `toolchain.py`/`setup.py`. Its installers run MPF-Godot-Packaging's own one-line
  installer (Git, Python, MPF, Godot, GMC into `~/MPF-Godot`, `-- --extra pillow` for the game's packages), then
  clone the game and run its `setup.py` with the platform's venv; `scripts/toolchain.py` finds the platform
  (`<P>_TOOLCHAIN`, the folder saved by the last setup, `~/MPF-Godot`, a sibling clone) and re-exports its pins and
  `ROOT`, `GAME`, `venv_python`, `host_os` for the PuP runtime's scripts; `run.py` calls `mpf_godot run`. One
  `install.sh` serves macOS and Linux (it calls the platform's `install_macos.sh` or `install_linux.sh`). Tested
  end to end on Linux (clone, setup, attract); the platform's installer can be swapped for a fake one in tests
  (`T2_PLATFORM_INSTALLER`), so the update cases (untracked `.uid`, branch gone) run on local repositories.
- **A private game's one line**: `raw.githubusercontent.com` serves a private file with the token in a header, so
  the line can still fetch itself: `bash <(curl -fsSL -H "Authorization: Bearer $T2_GITHUB_TOKEN" URL)`; Windows
  `irm -Headers @{Authorization=('Bearer ' + `$env:T2_GITHUB_TOKEN)} URL` inside the `-Command "..."` string, the
  backtick keeping `$env:` for the child shell (unescaped, the outer shell pastes the bare token into the code).
  Inferred from GitHub's documented behaviour; not run by the owner yet.
- **The PuP runtime's video add-ons without binaries in the game**: `scripts/pup_setup.py` (tools/pup/runtime) copies
  GoZen and native_video from the repository's `pup_addons/`, and removes `game/addons/gde_gozen` when that folder is
  missing. A game on the platform fills `pup_addons/` (git-ignored) from MPF-Godot-Packaging's `addons/` during setup
  instead of committing 30 MB of binaries. A pack placed by hand (no submodule) works: call `pup_setup.setup()` only
  when `pup_pack/triggers.pup` exists or a zip is given, else it tries a submodule the game does not have.
- **Media stale checks hash every input folder**, not a list of file types: agent C's `gen_media.py` began reading
  `dmd/fonts/fonts.json` the same day, and a check on `deff*.gif`/`*.ogg` only would have missed it (T2, 2026-11-21).
- **Bundles and the PuP**: a format 2 bundle of a PuP game builds and boots (T2: 11 MB, `mpf_godot local install`,
  attract), but the PuP runtime (`tools/pup/runtime`, @ fb238ad) does not read the platform's `MPF_PUP_PACK` and wants
  `pup_media/manifest.json`, so such a bundle plays without the pack until the runtime does (open).
- **Third-party sound packs and the sound source as setup options**: a PinSound pack (or any media pack) is never
  committed; `setup.py --pinsound-zip ZIP` extracts the folder holding `config.pinsound` (at any depth, path
  traversal refused, once per zip by a sha256 stamp) into a git-ignored folder, and `--music` / `--effects` write the
  cabinet's git-ignored `sound.local.cfg`, keeping its other keys. Giving a pack turns its effects on; the music
  changes only when asked (T2, 2026-11-21: Averell's pack, 463 files, 51 sound commands loaded).
- **The VPX option in one step (`-Vpx -Table`)**: the COM server's registration and pywin32's post-install need
  Administrator. Rather than asking the player for a second, elevated shell, `setup.py` relaunches itself with a hidden
  `--vpx-register` through `Start-Process -Verb RunAs -Wait -PassThru` (one UAC prompt, exit code kept) and, elevated,
  uses `sys.executable`, not the environment (an elevated process may not inherit it). Then the table's `.vbs` is
  written unelevated. Not run on Windows yet (T2, 2026-11-21).

## 5a. Jetson and 5d. Raspberry Pi 4: moved to MPF-Godot-Packaging

Board and platform findings (Jetson Xavier NX / AGX Orin install order, power modes, screens, hardware decoding;
Raspberry Pi 4 checks, V4L2 decoder, kernel bug, measuring, cross-building) are Godot / GoZen / platform content and
live in [Ashram56/MPF-Godot-Packaging](https://github.com/Ashram56/MPF-Godot-Packaging): [platforms/jetson.md](https://github.com/Ashram56/MPF-Godot-Packaging/blob/main/platforms/jetson.md),
[platforms/frame-rate-method.md](https://github.com/Ashram56/MPF-Godot-Packaging/blob/main/platforms/frame-rate-method.md), [platforms/video-playback.md](https://github.com/Ashram56/MPF-Godot-Packaging/blob/main/platforms/video-playback.md),
[platforms/godot-performance.md](https://github.com/Ashram56/MPF-Godot-Packaging/blob/main/platforms/godot-performance.md). Add new board findings there (see
[CONTRIBUTING.md](../CONTRIBUTING.md), section 2). What stays here: a game's kit must carry what those pages say
(the Jetson / Pi install step, run options such as `--no-render-thread`, the game's settings) into every installer.
(Moved 2026-10-27.)

## 5b. A signed Raspberry Pi image: design facts (not built yet)

Facts found while designing a signed Raspberry Pi 4 image for Tron (2026-10-19; the design itself is on the game's
page). Doc = Raspberry Pi's documentation read that day; inferred = reasoning, not tried.

- **Signing is not secrecy.** A signed image stops a board running a changed image; it hides nothing. A
  downloadable image can be opened on any PC, so a shared secret (a Scorbit provider key) never goes in it, signed
  or encrypted: provision it per cabinet onto a writable data partition after flashing (inferred).
- **"Only official images" needs the board's fuses.** On a stock Pi the SD card can always be reflashed; only a
  board whose OTP holds the hash of your RSA-2048 key (`program_pubkey`) refuses other boot images. That is
  permanent, and `revoke_devkey` before the bootloader is signed bricks the board (doc, `usbboot/secure-boot-recovery`).
  On any other board, the reachable goal is signed updates (RAUC bundles) and a read-only, dm-verity system (inferred).
- **Pi 4 (BCM2711) vs Pi 5:** on the Pi 4 the boot ROM checks the EEPROM bootloader against Raspberry Pi's key only,
  and your key checks `boot.img`/`boot.sig` (firmware, kernel, initramfs); the BCM2712 also requires your signature
  on the EEPROM (doc). Raspberry Pi's `rpi-sb-provisioner` supports CM4, CM4S, CM5 and Pi 5/500, **not the Pi 4
  Model B**, which is provisioned by hand with `usbboot` and a GPIO set as RPIBOOT (`program_rpiboot_gpio=8`) (doc).
- **Disk encryption tied to the board:** the provisioner's initramfs derives a LUKS key from a device-unique OTP secret
  (`rpi-fw-crypto`) (doc). A root shell on the running board can still read the data, so a locked board ships with no
  login (inferred).
- **A/B updates:** Raspberry Pi's own `autoboot.txt` with `tryboot` boots the new slot once and falls back (doc);
  updates are then whole system images, not `git pull`, so every writable file of the game (settings, audits,
  credentials, logs, the PuP Pack) must live on the data partition.
- **A public image for anyone to flash (balenaEtcher) cannot be kept unmodified:** before first boot it is files
  on a card, and a stock Pi boots whatever is there, so any check on the card can be edited out. Reachable: a
  dm-verity system whose root hash the initramfs checks, the game starting Scorbit only from a verified release,
  and the adjustments that change scoring held at factory values while Scorbit is on, so scores stay comparable
  (inferred design, Tron 2026-10-19). A shared key in such an image is one leak from revocation for every cabinet:
  ask Scorbit for per-release or per-cabinet credentials.
- **Signing keys stay off CI:** sign `boot.img` and the update bundles on the owner's PC with a hardware token; CI may
  build the unsigned image. A lost secure boot key means provisioned boards never take a new image.
- **A PuP Pack on a locked board:** the player downloads the author's zip and hands it over (USB stick, or an upload
  page on the local network); the game accepts only the zip SHA-256s of the releases its trigger map was checked on
  (inferred design).

## 6. Status and open work per game

## 5c. Prebuilt bundles: the game with nothing left to build

**Rule for every game (MPF-Godot-Packaging `platforms/game-bundles.md`, rules 12 and 13):** everything extra made for a game (media derived from a third-party pack, HD art, clips, converted files) is made offline when the bundle is built and ships in that bundle. Nothing is made, converted or pip-installed on the machine that runs the game (it only starts MPF and serves the settings page). Only what the owner downloads untouched from its author (a PuP Pack zip, a ROM) stays apart, and the page only unpacks it. Tron: `build_bundle.py --pup-zip`.

A ready-made system image (or any base install that already has MPF, Godot and ffmpeg) does not want to run
`setup.py`: on Tron that is 4 to 8 minutes on a 4-core PC, and 85% of it is computation (media generation, the Godot
import, the font bake), not downloads (observed). Everything that computation makes is the same on every machine of a
GPU family, so a **bundle** ships it built: one archive of the game, its generated config, media and sounds, its baked
fonts and its Godot import (Tron: `scripts/package/build_bundle.py`, `docs/bundle.md`; 235 MB packed, 633 MB
unpacked). **The builder is the platform's, not the game's, and the platform knows no game** (since 2026-10-29, owner rule):
MPF-Godot-Packaging [`platforms/game-bundles.md`](https://github.com/Ashram56/MPF-Godot-Packaging/blob/main/platforms/game-bundles.md)
is the method, `python -m mpf_godot bundle <description> --target all` the tool. It holds **no recipe, spec, file list or name
of any game**; it takes the **complete game package** that the game's repository (or the session that creates the game) produces
and describes, checks it, adds the platform add-ons, imports the textures and packs. The contract is in MPF-Godot-Packaging
`common/games/README.md` ("What the game provides") and `schema/game_package.schema.json`. A game does only this:

1. **Produce a complete package.** Every file needed at run time exists in the repository folder when the build starts,
   **generated and git-ignored files included** (config, media, sounds, baked fonts, generated slides and data tables). The
   game's own setup or build step makes them; the platform generates nothing. Transformers' first bundle lacked
   `game/slides/deffs` and `game/tf/media_data.json` (generated, ignored) and the platform's answer was a game spec in the
   platform repository, which is the wrong fix: the game lists them in its own description and a test in the game checks they exist.
2. Write the **description** in the game's repository: `bundle_spec.json` (or `game_package.json`, at the root or in
   `scripts/package/`; example `examples/bundle/bundle_spec.json` there): which tracked and generated folders to pack
   (`copy` lists must exist, `optional` for the rest), which cabinet files must never be in it, which `.import` files to write
   again, `platform_addons: ["gde_gozen", "mpf-gmc"]`, and the `run`, `options`, `pup` (`install`, `pack_dir`), `requires.env`
   and `keep_on_update` entries the setup page reads from `bundle.json`. The platform validates the keys and refuses a typo.
2. Keep **no binary** in the game: GoZen and the other add-ons come from the platform, identical for every game; a
   **universal bundle** (`--target all`) holds both texture formats, imported offline, and installs on any machine.
3. Add what is the game's own: a stale-media check before the build, its settings schema and tool, board profiles,
   its PuP install command. Tron's `scripts/package/build_bundle.py` is only that, around the platform's builder.
4. **Never put game content in MPF-Godot-Packaging** (its CONTRIBUTING.md and `tests/test_no_game_content.py` enforce it): no
   recipe, no spec, no game or PuP Pack name outside the provenance of a finding in `fixes/` and `platforms/`. A missing
   file or add-on is fixed in the game's package, or by a generic check in the platform, never by a game entry there.

The platform's setup web page then installs the bundle (and the PuP Pack zip through `pup.install`) on a machine with
nothing in it but the platform image. The rules the builder enforces, kept here as the reasons:

- **Texture formats.** Godot's import always writes the variant the *host* prefers (S3TC/BPTC on a PC) whatever
  `import_s3tc_bptc` says, and `import_etc2_astc=true` adds ETC2; ARM GPUs (Pi 4's V3D, Jetson) use ETC2 and a PC
  uses S3TC (observed: 2 595 VRAM-compressed frames came out as both `.s3tc.ctex` and `.etc2.ctex`). Build an ARM bundle on a PC
  with ETC2 added, then delete the S3TC files **and take `path.s3tc` / the `dest_files` entries / `imported_formats`
  out of every `.import`**: a GPU that supports both picks the first `path.*` in the file, and its file would be
  missing (code, from the file's format). A PC without Vulkan (OpenGL fallback) cannot show ETC2 and crashes in
  `_get_gl_image_and_format`; with Vulkan Godot logs "ETC2_RGB8 not supported by hardware, converting to RGBA8" and runs
  (observed, lavapipe, whose ETC2 and ASTC are off and BC on).
- **A universal bundle needs VRAM-compressed textures, and Godot only makes them for textures whose `.import` says
  `compress/mode=2`.** The default for a new PNG is lossless (`compress/mode=0`): such a game's bundle has no S3TC and
  no ETC2 variant, and a Pi 4 or Jetson then decompresses on the CPU at load (observed: another game's first bundle).
  Every game should therefore write VRAM-compressed `.import` files for the pictures its slides load (improvement.md,
  "When adding media"), except pictures a script reads back; the platform's builder warns when none is compressed and
  has `force_vram` for tracked `.import` files (MPF-Godot-Packaging `platforms/game-bundles.md`).
- **`.import` files you generate yourself are not tracked**, so a copy that skips `*.import` silently loses their
  settings: Tron's HD effect frames (VRAM-compressed) came out lossless, 2 765 textures instead of 2 595 + 2 765
  (observed, the first bundle build). Write them again before the import and check the variant counts after it.
- **A stale-media check that hashes generator inputs must not run in a bundle** (the inputs are not there): make
  "bundle.json exists" mean current.
- **An installer step that copies an add-on from the repository** (Tron: GoZen from `pup_addons/`) must keep what the
  bundle carries when the source folder is not there; Tron's step deleted the add-on from `game/` and then failed
  (observed).
- **Refuse cabinet data**: `game/data`, audits, logs, any `*.local.cfg` and device keys stay out, checked by the builder.
- **Run only what the game reads from the extraction repo** (Tron: 16 MB of its 460 MB `assets/`): found by running the
  game under `strace -f -e trace=openat,stat`, not by guessing.
- **A settings schema** (`options.json`: id, type, range, default, group, where stored) and a small tool that
  validates and writes it lets a web page configure the game without knowing its files; keep secrets write-only.
- **The PuP Pack stays out** (the author's zip, installed by the game's own step, `pup_setup.py --pup-zip`, declared in `bundle.json` `pup.install`); its install
  needs ffmpeg with libtheora even when the videos are not converted (Tron's `gen_pup.py` looks for it first).
- **The game's PuP step must keep the platform's GoZen.** With `platform_addons: ["gde_gozen"]` the platform puts its GoZen build in
  `game/addons/gde_gozen`; a `pup_setup.py` that only trusts `pup_addons/gde_gozen` in the game's repository deleted it and converted every video to
  Theora (256 videos, about an hour, no hardware decoding; Transformers on an Intel N100 mini PC, 2026-10-28). `tools/pup/runtime/scripts/pup_setup.py`
  now keeps an installed `game/addons/gde_gozen/gozen.gdextension` (`platform_gozen()`). The platform also passes the game its venv under the
  name the game declares in `requires.env` (a name ending in `VENV`); a game's toolchain should read that name and `MPF_GAME_VENV`.

Checked on a PC only (Tron, 2026-10-24); the arm64 bundle on a real Pi 4 or Jetson is the next test.

On each game's page (Tron: [Tron-Legacy-MPF `docs/agents/README.md`](https://github.com/Ashram56/Tron-Legacy-MPF/blob/main/docs/agents/README.md), "F, packaging").

Keep this file current with every installer change and owner test. Last updated 2026-11-21 (a thin kit on MPF-Godot-Packaging, a private game's one line, PuP add-ons from the platform, Terminator 2; 2026-10-29: the platform holds no game: the game provides a complete package and its description, section 5c; 2026-10-27: setup.py --scorbit; 5b, signed Raspberry Pi image design facts; prebuilt bundles, section 5c; Jetson and Pi 4 sections moved to MPF-Godot-Packaging; before 2026-10-25: Raspberry Pi 4, 5d: Godot's EGL fix for the separate render thread, one window to keep the page flip, vsync rounding and a 30 fps cap, D: building off the board; the bcm2835-codec STREAMOFF bug and its module fix, hardware decoding keyed to one board, video lag in every comparison; 2026-10-24: section 5d, the checks before promising a frame rate, the V4L2 decoder and zero-copy, Mesa v3d, sound and screens; before 2026-10-22: macOS CI: no system git config in the token test; the game-agnostic kit in MPF-Godot-Packaging; Xavier NX power modes and hitches, submodules on a reused board; before 2026-10-10: untracked Godot .uid files before the update's pull; PuP fork merged into Tron's game repo; the full README in the definition of done; optional private pack repository; main as default branch; GoZen on Windows; token paste on Windows, tags from cloud sessions, patches from the board; Jetson doc paths;
before: moved to Stern-SAM-Decryption; Tron status to the Tron game page; PuP Pack zip option).

## Test a prebuilt bundle before it goes to a machine (lessons of Transformers, 2026-10-28)

A bundle built on a PC and first started on the cabinet failed four times in a row (launcher options it does not take,
the venv not passed, the platform's GoZen deleted and 256 clips converted, media regenerated without the ROM's frames,
GMC not shipped). All of it shows on any x86 Linux box with no GPU; run it before sending:

1. Build with `scripts/package/build_bundle.py`; check the archive's sha256 and `xz -t`.
2. Install it with the platform loader's own function (`mpf_games.install_game`) into a scratch games folder, with the
   platform's add-ons folder (`MPF_PLATFORM_DIR`): this is what the cabinet does, including `override.cfg`, GoZen, GMC and
   the Godot re-import that rebuilds the class cache.
3. Start `scripts/run.py` from the installed folder under `xvfb-run` with the venv and Godot the board would set
   (`GODOT`, `MPF_GAME_VENV`, a `*_VENV` the bundle names in `requires.env`); expect GMC connected, the attract deff event and no
   `SCRIPT ERROR` in `game/logs/godot.log` (Vulkan and ALSA errors are the sandbox).
4. A bundle detects itself by `bundle.json` (the media are never regenerated, the ROM's frames are not in it); it never
   embeds GMC or GoZen when the platform provides them (`platform_addons`).
5. Ship every file of the media fingerprint (`toolchain.MEDIA_INPUTS`: Transformers needed `mpf_names.json`, `fonts.json`,
   `dmd/images.csv` in `bundle_spec.json` `copy`), then check in the unpacked bundle that `game/media/.generated` equals
   `media_fingerprint()`. A bundle that only skips the check (`bundle.json` present) hides the gap.
