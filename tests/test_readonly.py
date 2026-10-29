"""Read-only production mode (common/readonly): the scripts, the build helper and the setup page's side of it."""
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RO = os.path.join(HERE, "..", "common", "readonly")
sys.path.insert(0, os.path.join(HERE, "..", "common", "netconfig"))
import mpf_common as C  # noqa: E402
import mpf_games as G  # noqa: E402
import mpf_netconfig as nc  # noqa: E402


class Scripts(unittest.TestCase):
    def test_bash_syntax(self):
        for f in ("mpf-persist.sh", "mpf-mode.sh", "mpf-ro-check.sh", "install-readonly.sh"):
            self.assertEqual(subprocess.run(["bash", "-n", os.path.join(RO, f)]).returncode, 0, f)

    def test_install_into_a_rootfs(self):
        with tempfile.TemporaryDirectory() as r:
            for d in ("etc/ssh", "etc/wpa_supplicant", "opt/games", "home/mpf", "etc/systemd/network", "lib/systemd/system", "etc/X11/xinit", "var/lib/docker"):
                os.makedirs(os.path.join(r, d))
            open(os.path.join(r, "lib/systemd/system/apt-daily.timer"), "w").close()
            open(os.path.join(r, "etc/systemd/network/20-wired.network"), "w").close()
            open(os.path.join(r, "etc/fstab"), "w").write(
                "LABEL=firmware /boot/efi vfat umask=0077,nofail 0 2\nLABEL=rootfs / ext4 defaults,noatime 0 1\n")
            script = f'. "{RO}/install-readonly.sh"; mpf_readonly_install "{r}" mpf /boot/efi "docker:/var/lib/docker gone:/not/there"'
            out = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            fstab = open(os.path.join(r, "etc/fstab")).read()
            self.assertIn("umask=0077,nofail,ro 0 2", fstab)
            self.assertIn("defaults,noatime,ro 0 1", fstab)
            self.assertIn("tmpfs /var/log tmpfs", fstab)
            conf = C.read_kv(os.path.join(r, "etc/mpf-readonly.conf"))
            self.assertEqual(conf["MPF_USER"], "mpf")
            self.assertEqual(conf["MPF_BOOT_MOUNT"], "/boot/efi")
            pairs = conf["MPF_PERSIST"].split()
            for want in ("games:/opt/games", "ssh:/etc/ssh", "usersh:/home/mpf/.ssh", "docker:/var/lib/docker"):
                self.assertIn(want, pairs)
            self.assertNotIn("gone:/not/there", pairs)
            self.assertTrue(os.path.islink(os.path.join(r, "etc/systemd/system/apt-daily.timer")))
            self.assertTrue(os.path.isfile(os.path.join(r, "etc/systemd/network/20-wired.network.d/10-mpf-mac.conf")))
            self.assertTrue(os.path.islink(os.path.join(r, "etc/systemd/system/local-fs.target.wants/mpf-persist.service")))


@unittest.skipUnless(os.geteuid() == 0 and shutil.which("losetup") and shutil.which("sfdisk") and shutil.which("mkfs.ext4"), "needs root, losetup, sfdisk")
class DataPartition(unittest.TestCase):
    def test_first_boot_creates_then_reuses(self):
        with tempfile.TemporaryDirectory() as t:
            img = os.path.join(t, "disk.img")
            with open(img, "wb") as f:
                f.truncate(1 << 30)
            subprocess.run(["sfdisk", "-q", img], input="label: gpt\nstart=2048,size=100MiB,type=U\ntype=L,size=200MiB\n", text=True, check=True)
            lo = subprocess.run(["losetup", "-f", "--show", "-P", img], capture_output=True, text=True)
            if lo.returncode:
                self.skipTest("no loop device")
            dev = lo.stdout.strip()
            subprocess.run(["partx", "-a", dev], capture_output=True)     # a sandbox without udev does not scan them
            data, etc = os.path.join(t, "data"), os.path.join(t, "etc")
            os.makedirs(etc)
            open(os.path.join(etc, "a"), "w").write("image")
            conf = os.path.join(t, "conf")
            open(conf, "w").write(f'MPF_DATA_MOUNT={data}\nMPF_USER=root\nMPF_DATA_MIN_MB=100\nMPF_PERSIST="ssh:{etc}"\n')
            env = dict(os.environ, MPF_ROOT_DISK=dev, MPF_READONLY_CONF=conf)
            try:
                for _ in range(2):      # the second boot finds the partition and keeps what was written
                    subprocess.run(["bash", os.path.join(RO, "mpf-persist.sh")], env=env, capture_output=True, check=True)
                    self.assertTrue(os.path.ismount(data) and os.path.ismount(etc))
                    if _ == 0:
                        self.assertEqual(open(os.path.join(etc, "a")).read(), "image")
                        open(os.path.join(etc, "b"), "w").write("kept")
                    else:
                        self.assertEqual(open(os.path.join(etc, "b")).read(), "kept")
                    subprocess.run(["umount", etc, data], check=True)
                parts = subprocess.run(["lsblk", "-lno", "NAME", dev], capture_output=True, text=True).stdout.split()
                self.assertEqual(len(parts), 4)    # disk + the two partitions + the data partition
            finally:
                for m in (etc, data):
                    subprocess.run(["umount", m], capture_output=True)
                subprocess.run(["losetup", "-d", dev])

    def test_injected_partition_is_grown(self):
        with tempfile.TemporaryDirectory() as t:
            img = os.path.join(t, "disk.img")
            with open(img, "wb") as f:
                f.truncate(1 << 30)
            subprocess.run(["sfdisk", "-q", img], input="label: gpt\nstart=2048,size=100MiB,type=U\ntype=L,size=100MiB\n", text=True, check=True)
            lo = subprocess.run(["losetup", "-f", "--show", "-P", img], capture_output=True, text=True)
            if lo.returncode:
                self.skipTest("no loop device")
            dev = lo.stdout.strip()
            subprocess.run(["partx", "-a", dev], capture_output=True)
            data = os.path.join(t, "data")
            conf = os.path.join(t, "conf")
            open(conf, "w").write(f"MPF_DATA_MOUNT={data}\nMPF_USER=root\nMPF_DATA_MIN_MB=100\n")
            env = dict(os.environ, MPF_ROOT_DISK=dev, MPF_READONLY_CONF=conf)
            try:
                part = dev + "p2"
                subprocess.run(["mkfs.ext4", "-q", "-F", "-L", "mpfdata", part], check=True)
                subprocess.run(["bash", os.path.join(RO, "mpf-persist.sh")], env=env, capture_output=True, check=True)
                self.assertTrue(os.path.ismount(data))
                out = subprocess.run(["df", "-m", "--output=size", data], capture_output=True, text=True).stdout.split()[-1]
                self.assertGreater(int(out), 700)       # was 100 MB, the disk is 1 GB
                subprocess.run(["umount", data], check=True)
            finally:
                subprocess.run(["umount", data], capture_output=True)
                subprocess.run(["losetup", "-d", dev])


class NetconfigSide(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(C, k) for k in ("READONLY", "DATA", "VOLATILE_LOGS", "USER", "CONF", "XDG_RAM", "STATE_DIR")}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(C, k, v)

    def test_ordinary_image_untouched(self):
        C.READONLY = False
        self.assertIsNone(C.mode_status())
        self.assertEqual(G.ram_xdg_env(), {})
        with C.writable("/etc"):       # no remount outside the read-only mode
            pass

    def test_game_logs_go_to_ram(self):
        with tempfile.TemporaryDirectory() as t:
            C.READONLY, C.VOLATILE_LOGS, C.USER = True, os.path.join(t, "ram-logs"), pwd.getpwuid(os.getuid()).pw_name
            game = os.path.join(t, "game")
            os.makedirs(os.path.join(game, "game", "logs"))
            open(os.path.join(game, "game", "logs", "old.log"), "w").close()
            G.volatile_game_dirs(game)
            link = os.path.join(game, "game", "logs")
            self.assertTrue(os.path.islink(link))
            self.assertEqual(os.readlink(link), C.VOLATILE_LOGS)
            G.volatile_game_dirs(game)     # idempotent

    def test_mode_key_in_the_text_file_is_used_once(self):
        with tempfile.TemporaryDirectory() as t:
            C.CONF = os.path.join(t, "mpf-network.txt")
            open(C.CONF, "w").write("WIFI_SSID=\nMODE=maintenance\n")
            C.READONLY = True
            calls = []
            real, nc.set_mode = nc.set_mode, lambda m, stay=False: calls.append((m, stay))
            real_w, C.writable = C.writable, lambda p: __import__("contextlib").nullcontext()
            try:
                nc.apply_file()
            finally:
                nc.set_mode, C.writable = real, real_w
            self.assertEqual(calls, [("maintenance", True)])
            self.assertIn("MODE=\n", open(C.CONF).read())


if __name__ == "__main__":
    unittest.main()
