"""The setup page installs the platform's binary add-ons into a bundle that lists them (bundle.json platform_addons)."""
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mpf_netconfig", os.path.join(HERE, "..", "common", "netconfig", "mpf_netconfig.py"))
nc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nc)


class PlatformAddons(unittest.TestCase):
    def test_only_this_machines_binaries(self):
        with tempfile.TemporaryDirectory() as plat, tempfile.TemporaryDirectory() as dest:
            a = os.path.join(plat, "addons", "gde_gozen")
            os.makedirs(os.path.join(a, "bin"))
            for n in ("gozen.gdextension", "video_playback.gd", "bin/libgozen.linux.template_release.arm64.so",
                      "bin/libgozen.linux.template_release.x86_64.so", "bin/libgozen.windows.template_release.x86_64.dll"):
                open(os.path.join(a, n), "w").close()
            nc.PLATFORM_DIR = plat
            nc.install_platform_addons(dest, {"platform_addons": ["gde_gozen"]}, "x86_64")
            got = sorted(os.listdir(os.path.join(dest, "game", "addons", "gde_gozen", "bin")))
            self.assertEqual(got, ["libgozen.linux.template_release.x86_64.so"])
            self.assertTrue(os.path.isfile(os.path.join(dest, "game", "addons", "gde_gozen", "gozen.gdextension")))

    def test_missing_platform_addon(self):
        with tempfile.TemporaryDirectory() as plat, tempfile.TemporaryDirectory() as dest:
            old, nc.platform_addon = nc.platform_addon, lambda name: None
            try:
                with self.assertRaises(nc.JobError):
                    nc.install_platform_addons(dest, {"platform_addons": ["gde_gozen"]}, "arm64")
            finally:
                nc.platform_addon = old


if __name__ == "__main__":
    unittest.main()
