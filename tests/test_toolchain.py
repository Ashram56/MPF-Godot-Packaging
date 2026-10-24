"""mpf_godot: toolchain paths per OS, the GMC patch on a GMC-shaped tree, the launcher's helpers, setup's plan."""
import io
import os
import shutil
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from mpf_godot import gmc_patch, launcher, setup_toolchain  # noqa: E402
from mpf_godot import toolchain as tc  # noqa: E402

# the lines of GMC 1.0.0 the patch replaces, each in a file of the same name
GMC_FILES = {
    "plugin.cfg": "[plugin]\nname=\"MPF GMC\"\n",
    "scripts/bcp_server.gd": "var _client: StreamPeerTCP\nfunc a():\n\t\t_client = _server.take_connection()\n"
                             "\t\tvar messages := _client.get_string(bytes).split(\"\\n\")\n",
    "scripts/bcp_parse.gd": "\t\t\tresult.error = \"Error %s parsing trigger: %s\" % [json.error, message]\n",
    "mpf_gmc.gd": "func _input(event):\n\tif keycode in keyboard:\n\t\tpass\n",
}


def gmc_tree(crlf=False):
    d = tempfile.mkdtemp()
    for rel, text in GMC_FILES.items():
        path = os.path.join(d, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace("\n", "\r\n") if crlf else text)
    return d


class TestToolchain(unittest.TestCase):

    def test_hosts(self):
        self.assertEqual("windows", tc.host_os("Windows"))
        self.assertEqual("macos", tc.host_os("Darwin"))
        self.assertEqual("arm64", tc.host_arch("aarch64"))
        self.assertEqual("x86_64", tc.host_arch("AMD64"))
        with self.assertRaises(SystemExit):
            tc.host_arch("riscv64")

    def test_godot_assets(self):
        v = tc.GODOT_VERSION
        self.assertEqual("Godot_v%s-stable_win64.exe.zip" % v, tc.godot_asset("windows", "x86_64"))
        self.assertEqual("Godot_v%s-stable_macos.universal.zip" % v, tc.godot_asset("macos", "arm64"))
        self.assertEqual("Godot_v%s-stable_linux.arm64.zip" % v, tc.godot_asset("linux", "arm64"))
        self.assertTrue(tc.godot_url("linux", "x86_64").startswith("https://github.com/godotengine/godot/releases/"))
        self.assertTrue(tc.godot_path("macos", "arm64").endswith(os.path.join("Godot.app", "Contents", "MacOS",
                                                                               "Godot")))
        self.assertEqual("Godot_v%s-stable_linux.x86_64" % v, tc.godot_relpath("linux", "x86_64"))

    def test_venv_paths(self):
        self.assertTrue(tc.venv_exe("mpf", "windows").endswith(os.path.join("Scripts", "mpf.exe")))
        self.assertTrue(tc.venv_exe("mpf", "linux").endswith(os.path.join("bin", "mpf")))
        with mock.patch.dict(os.environ, {"MPF_GODOT_VENV": "/opt/venv"}):
            self.assertEqual("/opt/venv", tc.venv_dir())

    def test_pins_carry_their_fixes(self):
        self.assertIn('ruamel.yaml.clib==0.2.14; python_version < "3.13"', tc.REQUIREMENTS)
        self.assertTrue(any(r.startswith("PyQt6>=6.4.2,<6.8") for r in tc.MONITOR_REQUIREMENTS))
        self.assertEqual(4, len(tc.MPF_MONITOR_UI_FILES))

    def test_video_addons(self):
        self.assertTrue(tc.gozen_supported("linux", "arm64"))
        self.assertFalse(tc.gozen_supported("macos", "arm64"))
        self.assertTrue(tc.native_video_supported("macos", "x86_64"))
        for name in ("gde_gozen", "native_video"):
            self.assertTrue(os.path.isdir(tc.addon_dir(name)), name)

    def test_display(self):
        self.assertTrue(tc.needs_virtual_display("linux", {}))
        self.assertFalse(tc.needs_virtual_display("linux", {"DISPLAY": ":0"}))
        self.assertFalse(tc.needs_virtual_display("windows", {}))


class TestGmcPatch(unittest.TestCase):

    def test_patch_is_idempotent(self):
        for crlf in (False, True):
            with self.subTest(crlf=crlf):
                d = gmc_tree(crlf)
                self.addCleanup(shutil.rmtree, d)
                self.assertEqual("unpatched", gmc_patch.status(d))
                self.assertEqual("patched", gmc_patch.patch(d, quiet=True))
                self.assertEqual("in place", gmc_patch.patch(d, quiet=True))
                with open(os.path.join(d, "scripts", "bcp_server.gd"), encoding="utf-8", newline="") as f:
                    text = f.read()
                self.assertIn("_rx_partial", text)
                self.assertEqual(crlf, "\r\n" in text)
                with open(os.path.join(d, "mpf_gmc.gd"), encoding="utf-8") as f:
                    self.assertIn("get_physical_keycode_with_modifiers", f.read())

    def test_missing_and_unknown(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        self.assertEqual("missing", gmc_patch.patch(d))
        d = gmc_tree()
        self.addCleanup(shutil.rmtree, d)
        with open(os.path.join(d, "mpf_gmc.gd"), "w") as f:
            f.write("something else\n")
        with self.assertRaises(SystemExit):
            gmc_patch.patch(d, quiet=True)

    def test_older_tag_counts_as_patched(self):
        d = gmc_tree()
        self.addCleanup(shutil.rmtree, d)
        for rel in ("scripts/bcp_server.gd", "scripts/bcp_parse.gd", "mpf_gmc.gd"):
            with open(os.path.join(d, *rel.split("/")), "a") as f:
                f.write("# tron patch\n")
        self.assertEqual("in place", gmc_patch.status(d))


class TestLauncher(unittest.TestCase):

    def test_port_in_use(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen()
        self.addCleanup(s.close)
        self.assertTrue(launcher.port_in_use(s.getsockname()[1]))
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()
        self.assertFalse(launcher.port_in_use(port))

    def test_godot_command(self):
        with mock.patch.dict(os.environ, {"GODOT": sys.executable}):
            cmd = launcher.godot_command("/game", ["--x"], virtual_display=False)
            self.assertEqual([sys.executable, "--path", "/game", "--x"], cmd)
            cmd = launcher.godot_command("/game", [], virtual_display=False, render_thread=False)
            self.assertEqual(["--render-thread", "safe"], cmd[3:5])
            cmd = launcher.godot_command("/game", ["--rendering-driver", "opengl3"], virtual_display=False)
            self.assertIn("--render-thread", cmd)
            if shutil.which("xvfb-run"):
                self.assertEqual("xvfb-run", launcher.godot_command("/game", [], virtual_display=True)[0])

    def test_godot_command_on_a_pi4_uses_opengl(self):
        with mock.patch.dict(os.environ, {"GODOT": sys.executable}), \
                mock.patch.object(tc, "is_raspberry_pi4", return_value=True):
            cmd = launcher.godot_command("/game", [], virtual_display=False)
            self.assertEqual(["--rendering-driver", "opengl3"], cmd[3:5])
            cmd = launcher.godot_command("/game", ["--rendering-driver", "vulkan"], virtual_display=False)
            self.assertEqual(1, cmd.count("--rendering-driver"))
            self.assertEqual("vulkan", cmd[cmd.index("--rendering-driver") + 1])
            with mock.patch.dict(os.environ, {"MPF_GODOT_RENDERER": "vulkan"}):
                self.assertNotIn("--rendering-driver", launcher.godot_command("/game", [], virtual_display=False))
        with mock.patch.dict(os.environ, {"GODOT": sys.executable}), \
                mock.patch.object(tc, "is_raspberry_pi4", return_value=False):
            self.assertNotIn("--rendering-driver", launcher.godot_command("/game", [], virtual_display=False))

    def test_main_sends_everything_after_dashes_to_godot(self):
        with mock.patch.object(launcher, "run", return_value=0) as run:
            launcher.main(["g", "--seconds", "25", "--", "--rendering-driver", "opengl3"])
            self.assertEqual(["--rendering-driver", "opengl3"], run.call_args.kwargs["godot_args"])
            self.assertEqual(25.0, run.call_args.kwargs["seconds"])
            launcher.main(["g"])
            self.assertEqual([], run.call_args.kwargs["godot_args"])

    def test_is_raspberry_pi4_reads_the_device_tree(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        path = os.path.join(d, "model")
        with open(path, "wb") as f:
            f.write(b"Raspberry Pi 4 Model B Rev 1.1\0")
        self.assertTrue(tc.is_raspberry_pi4(path))
        with open(path, "wb") as f:
            f.write(b"NVIDIA Jetson Xavier NX\0")
        self.assertFalse(tc.is_raspberry_pi4(path))
        self.assertFalse(tc.is_raspberry_pi4(os.path.join(d, "missing")))

    def test_run_needs_a_project(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        with self.assertRaises(SystemExit):
            launcher.run(d)


class TestSetupPlan(unittest.TestCase):

    def test_dry_run_for_every_host(self):
        for os_name in ("windows", "macos", "linux"):
            for arch in ("x86_64", "arm64"):
                with self.subTest(os=os_name, arch=arch):
                    out = io.StringIO()
                    with redirect_stdout(out):
                        self.assertEqual(0, setup_toolchain.main(["--os", os_name, "--arch", arch, "--proc"]))
                    text = out.getvalue()
                    self.assertIn("(dry run)", text)
                    self.assertIn(tc.godot_url(os_name, arch), text)
                    self.assertIn("mpf==" + tc.MPF_VERSION, text)
                    self.assertIn("bcp-partial-lines", text)
                    self.assertIn("P-ROC", text)


if __name__ == "__main__":
    unittest.main()
