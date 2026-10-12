"""The one-line installers (install/, platforms/jetson/) in their dry-run modes, the standalone clone, the update of an
existing clone, the token step, and the Windows installer through pwsh when it is installed."""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTALL = os.path.join(ROOT, "install")
JETSON = os.path.join(ROOT, "platforms", "jetson")
BASH = shutil.which("bash")
PWSH = shutil.which("pwsh") or os.environ.get("PWSH")
POSIX = os.name == "posix"
SCRUB = ("GITHUB_TOKEN", "GH_TOKEN", "MPF_GODOT_GITHUB_TOKEN", "MPF_GODOT_DIR", "MPF_GODOT_REPO", "MPF_GODOT_BRANCH")


def env_with(extra=None):
    env = {k: v for k, v in os.environ.items() if k not in SCRUB}
    env.update(extra or {})
    return env


def sh(args, env=None):
    return subprocess.run([BASH] + args, capture_output=True, text=True, env=env_with(env), timeout=120, cwd=ROOT)


def git(*a, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"] + list(a),
                   cwd=cwd, check=True, capture_output=True)


@unittest.skipUnless(BASH and POSIX, "needs bash on Linux or macOS")
class TestShellInstallers(unittest.TestCase):
    SCRIPTS = [os.path.join(INSTALL, n) for n in ("install_linux.sh", "install_macos.sh", "build_pinproc.sh")] + \
        [os.path.join(JETSON, n) for n in ("install_jetson_hwdec.sh", "jetson_selftest.sh")]

    def tmp(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def os_release(self, text):
        path = os.path.join(self.tmp(), "os-release")
        with open(path, "w") as f:
            f.write(text)
        return path

    def linux_plan(self, os_release, *args):
        return sh([os.path.join(INSTALL, "install_linux.sh"), "--dry-run", "--no-setup"] + list(args),
                  env={"MPF_GODOT_OS_RELEASE": self.os_release(os_release), "DISPLAY": ":0"})

    def test_syntax(self):
        for path in self.SCRIPTS:
            with self.subTest(script=os.path.basename(path)):
                r = sh(["-n", path])
                self.assertEqual(0, r.returncode, r.stderr)

    def test_linux_families(self):
        for text, family in (('ID=ubuntu\nPRETTY_NAME="Ubuntu 24.04 LTS"\n', "apt"), ('ID=debian\n', "apt"),
                             ('ID=linuxmint\nID_LIKE="ubuntu debian"\n', "apt"), ('ID=fedora\n', "dnf"),
                             ('ID=rocky\nID_LIKE="rhel centos fedora"\n', "dnf"), ('ID=arch\n', "pacman"),
                             ('ID=endeavouros\nID_LIKE=arch\n', "pacman")):
            with self.subTest(os_release=text.split("\n")[0]):
                r = self.linux_plan(text, "--proc")
                self.assertEqual(0, r.returncode, r.stdout + r.stderr)
                self.assertIn("({},".format(family), r.stdout)
                self.assertIn("build_pinproc.sh", r.stdout)
                self.assertIn("99-pinproc.rules", r.stdout)

    def test_linux_unsupported_and_bad_option(self):
        r = self.linux_plan('ID=opensuse-tumbleweed\nID_LIKE="opensuse suse"\n')
        self.assertEqual(1, r.returncode)
        self.assertIn("unsupported distribution", r.stderr)
        self.assertEqual(2, sh([os.path.join(INSTALL, "install_linux.sh"), "--bogus"]).returncode)
        self.assertEqual(2, sh([os.path.join(INSTALL, "install_macos.sh"), "--bogus"]).returncode)

    def test_setup_args_pass_through(self):
        r = sh([os.path.join(INSTALL, "install_linux.sh"), "--dry-run", "--no-monitor", "--", "--extra", "pillow"],
               env={"MPF_GODOT_OS_RELEASE": self.os_release("ID=debian\n"), "DISPLAY": ":0"})
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("-m mpf_godot setup --no-monitor --dry-run --extra pillow", r.stdout)

    def test_macos_plan(self):
        r = sh([os.path.join(INSTALL, "install_macos.sh"), "--dry-run"])
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("Python 3.11", r.stdout)
        self.assertIn("-m mpf_godot setup --dry-run", r.stdout)
        if os.uname().sysname != "Darwin":
            self.assertIn("macos.universal", r.stdout)          # the plan is macOS's, not this host's

    def test_standalone_clones(self):
        """Run on its own (bash <(curl ...)), an installer clones the repository first; from a clone it never does."""
        tmp = self.tmp()
        target = os.path.join(tmp, "MPF-Godot")
        env = {"MPF_GODOT_OS_RELEASE": self.os_release("ID=debian\n"), "DISPLAY": ":0", "MPF_GODOT_DIR": target,
               "MPF_GODOT_BRANCH": "some-branch", "MPF_GODOT_REPO": "https://example.invalid/mpf-godot.git"}
        for name in ("install_linux.sh", "install_macos.sh"):
            with self.subTest(script=name):
                alone = os.path.join(tmp, name)
                shutil.copy(os.path.join(INSTALL, name), alone)
                r = sh([alone, "--dry-run"], env=env)
                self.assertEqual(0, r.returncode, r.stdout + r.stderr)
                self.assertIn("git clone --branch some-branch https://example.invalid/mpf-godot.git " + target, r.stdout)
                self.assertIn("cd {} && ".format(target), r.stdout)
                os.makedirs(os.path.join(target, ".git"), exist_ok=True)      # no branch: switch to the branch
                r = sh([alone, "--dry-run"], env=env)
                self.assertIn("git -C {} checkout -B some-branch --track origin/some-branch".format(target), r.stdout)
                shutil.rmtree(os.path.join(target, ".git"))
                r = sh([os.path.join(INSTALL, name), "--dry-run"], env=env)
                self.assertEqual(0, r.returncode, r.stdout + r.stderr)
                self.assertNotIn("git clone", r.stdout)
                self.assertIn("cd {} && ".format(ROOT), r.stdout)

    def test_existing_clone_branch_gone(self):
        tmp = self.tmp()
        origin, target = os.path.join(tmp, "origin"), os.path.join(tmp, "clone")
        git("init", origin, cwd=tmp)
        git("commit", "--allow-empty", "-m", "one", cwd=origin)
        git("branch", "feature", cwd=origin)
        git("clone", "--branch", "feature", origin, target, cwd=tmp)
        env = {"MPF_GODOT_OS_RELEASE": self.os_release("ID=debian\n"), "DISPLAY": ":0", "MPF_GODOT_DIR": target,
               "MPF_GODOT_REPO": origin}
        for name in ("install_linux.sh", "install_macos.sh"):
            shutil.copy(os.path.join(INSTALL, name), os.path.join(tmp, name))
            r = sh([os.path.join(tmp, name), "--dry-run"], env=env)
            self.assertIn("git -C {} pull --ff-only".format(target), r.stdout)
        git("branch", "-D", "feature", cwd=origin)
        for name in ("install_linux.sh", "install_macos.sh"):
            with self.subTest(script=name):
                r = sh([os.path.join(tmp, name), "--dry-run"], env=env)
                self.assertEqual(0, r.returncode, r.stdout + r.stderr)
                self.assertIn("'feature' is no longer on GitHub", r.stdout)
                self.assertIn("git -C {} checkout -B main --track origin/main".format(target), r.stdout)

    def test_existing_clone_untracked_files_in_update(self):
        """Godot's .uid/.import files and identical copies the update adds are removed before the pull; anything
        else is kept as <file>.local (platforms: "Untracked files before the update")."""
        tmp = self.tmp()
        origin, target = os.path.join(tmp, "origin"), os.path.join(tmp, "clone")

        def write(folder, files):
            for rel, text in files.items():
                os.makedirs(os.path.dirname(os.path.join(folder, rel)), exist_ok=True)
                with open(os.path.join(folder, rel), "w") as f:
                    f.write(text)
        git("init", origin, cwd=tmp)
        git("commit", "--allow-empty", "-m", "one", cwd=origin)
        git("clone", origin, target, cwd=tmp)
        write(origin, {"tools/new.gd.uid": "uid://tracked\n", "same.txt": "same\n", "mine.txt": "theirs\n"})
        git("add", ".", cwd=origin)
        git("commit", "-m", "two", cwd=origin)
        git("fetch", cwd=target)
        write(target, {"tools/new.gd.uid": "uid://local\n", "same.txt": "same\n", "mine.txt": "mine\n",
                       "other.txt": "untouched\n"})
        env = {"MPF_GODOT_OS_RELEASE": self.os_release("ID=debian\n"), "DISPLAY": ":0", "MPF_GODOT_DIR": target,
               "MPF_GODOT_REPO": origin}
        for name in ("install_linux.sh", "install_macos.sh"):
            with self.subTest(script=name):
                alone = os.path.join(tmp, name)
                shutil.copy(os.path.join(INSTALL, name), alone)
                r = sh([alone, "--dry-run"], env=env)
                self.assertEqual(0, r.returncode, r.stdout + r.stderr)
                self.assertIn("rm -f -- " + os.path.join(target, "tools/new.gd.uid"), r.stdout)
                self.assertIn("rm -f -- " + os.path.join(target, "same.txt"), r.stdout)
                self.assertIn("kept your copy of mine.txt as mine.txt.local", r.stdout)
                self.assertNotIn("other.txt", r.stdout)
                self.assertLess(r.stdout.index("mine.txt.local"), r.stdout.index("pull --ff-only"))

    def test_github_auth(self):
        """A public repository needs no token, even with one given; a token that cannot read a private repository
        stops the install with a clear message; the token is never printed."""
        tmp = self.tmp()
        repo = os.path.join(tmp, "repo")
        git("init", "-q", repo, cwd=tmp)
        git("commit", "-q", "--allow-empty", "-m", "one", cwd=repo)
        for name in ("install_linux.sh", "install_macos.sh"):
            with open(os.path.join(INSTALL, name), encoding="utf-8") as f:
                script = f.read()
            funcs = script[script.index("say() {"):script.index("AUTH_DONE=0")]
            for env, code, out in (({"MPF_GODOT_REPO": repo}, 0, "is public: no token needed"),
                                   ({"MPF_GODOT_REPO": repo, "GITHUB_TOKEN": "secret-token-123"}, 0,
                                    "is public: no token needed"),
                                   ({"MPF_GODOT_REPO": os.path.join(tmp, "missing"),
                                     "MPF_GODOT_GITHUB_TOKEN": "secret-token-123"}, 1, "cannot read " + tmp)):
                with self.subTest(script=name, env=sorted(env)):
                    prog = 'DRY=0 YES=1 CLONE=1; REPO_URL="$MPF_GODOT_REPO"\n' + funcs + "github_auth\n"
                    r = subprocess.run(["bash", "-c", prog], capture_output=True, text=True, timeout=60,
                                       env=env_with(dict(env, HOME=tmp)))
                    self.assertEqual(code, r.returncode, r.stdout + r.stderr)
                    self.assertIn(out, r.stdout + r.stderr)
                    self.assertNotIn("secret-token-123", r.stdout + r.stderr)

    def test_build_pinproc_plan(self):
        r = sh([os.path.join(INSTALL, "build_pinproc.sh"), "--dry-run", "--python", "/x/python"],
               env={"XDG_CACHE_HOME": self.tmp()})
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("libpinproc", r.stdout)
        self.assertIn("/x/python -m pip install", r.stdout)

    def jetson(self, release_text, model, compatible):
        tmp = self.tmp()
        release = os.path.join(tmp, "nv_tegra_release")
        with open(release, "w") as f:
            f.write(release_text)
        with open(os.path.join(tmp, "model"), "w") as f:
            f.write(model + "\0")
        with open(os.path.join(tmp, "compatible"), "w") as f:
            f.write(compatible)
        r = sh([os.path.join(JETSON, "install_jetson_hwdec.sh"), "--dry-run"],
               env={"MPF_GODOT_ARCH": "aarch64", "MPF_GODOT_NV_RELEASE": release, "MPF_GODOT_DEVICE_TREE": tmp,
                    "XDG_CACHE_HOME": tmp})
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        return r.stdout

    def test_jetson_skips_other_machines(self):
        if os.path.exists("/etc/nv_tegra_release"):
            self.skipTest("on a Jetson")
        r = sh([os.path.join(JETSON, "install_jetson_hwdec.sh"), "--dry-run"])
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("not an NVIDIA Jetson", r.stdout)

    def test_jetson_plans(self):
        out = self.jetson("# R35 (release), REVISION: 4.1, GCID: 1, BOARD: t186ref, EABI: aarch64\n",
                          "NVIDIA Jetson Xavier NX Developer Kit", "nvidia,p3509-0000+p3668-0001\0nvidia,tegra194\0")
        self.assertIn("SoC t194, NVIDIA apt release r35.4", out)
        self.assertIn("nvmpi_flush.patch", out)
        self.assertIn(os.path.join(ROOT, "platforms", "jetson", "..", "..", "build", "gozen"), out)
        out = self.jetson("# R36 (release), REVISION: 4.3, GCID: 38968081, BOARD: generic, EABI: aarch64\n",
                          "NVIDIA Jetson AGX Orin Developer Kit", "nvidia,p3701-0005\0nvidia,tegra234\0")
        self.assertIn("SoC t234, NVIDIA apt release r36.4", out)
        self.assertIn("l4t-pin.pref: nvidia-l4t-* 36.4.3-*", out)

    def test_jetson_selftest_plan(self):
        tmp = self.tmp()
        release = os.path.join(tmp, "nv_tegra_release")
        with open(release, "w") as f:
            f.write("# R35 (release), REVISION: 6.4, GCID: 1, BOARD: generic, EABI: aarch64\n")
        r = sh([os.path.join(JETSON, "jetson_selftest.sh"), "--dry-run", "--stock", "--runs", "10"],
               env={"MPF_GODOT_NV_RELEASE": release, "XDG_CACHE_HOME": tmp})
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn(os.path.join(ROOT, "fixes", "repro", "nvmpi_seek_close.c"), r.stdout)
        self.assertIn("-L/usr/lib/aarch64-linux-gnu/tegra ", r.stdout)


@unittest.skipUnless(PWSH, "needs pwsh (PowerShell 7) for the Windows installer's dry run")
class TestWindowsInstaller(unittest.TestCase):

    def pwsh(self, command, env=None):
        return subprocess.run([PWSH, "-NoProfile", "-Command", command], capture_output=True, text=True,
                              env=env_with(env), timeout=120, cwd=ROOT)

    def test_one_line_form_dry_run(self):
        """The README's one line runs the script as one scriptblock; options and pass-through arguments bind."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        script = os.path.join(INSTALL, "install_windows.ps1")
        r = self.pwsh("& ([scriptblock]::Create((Get-Content -Raw '{}'))) -DryRun -NoMonitor --extra pillow"
                      .format(script), env={"MPF_GODOT_DIR": os.path.join(tmp, "MPF-Godot")})
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("git clone --branch main https://github.com/Ashram56/MPF-Godot-Packaging.git", r.stdout)
        self.assertIn("-m mpf_godot setup --no-monitor --dry-run --extra pillow", r.stdout)

    def test_from_clone(self):
        r = self.pwsh("& '{}' -DryRun".format(os.path.join(INSTALL, "install_windows.ps1")))
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertNotIn("git clone", r.stdout)
        self.assertIn("-m mpf_godot setup --dry-run", r.stdout)


if __name__ == "__main__":
    unittest.main()
