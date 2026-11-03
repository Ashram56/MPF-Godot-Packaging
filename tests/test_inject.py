"""Own code in a bundle (common/games/make_bundle.py) and bundles in an image before flashing (common/games/inject_image.py)."""
import sys as _sys
import unittest as _unittest

if not _sys.platform.startswith("linux"):
    raise _unittest.SkipTest("the platform page and its netconfig code run on the Linux images only")

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests import test_games as TG

HERE = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.join(HERE, "..", "common", "games")
G, C = TG.G, TG.C
sys.path.insert(0, os.path.join(HERE, "..", "common", "netconfig"))
import mpf_contract as K  # noqa: E402


def tool(name, *args, **kw):
    return subprocess.run([sys.executable, os.path.join(GAMES, name), *args], capture_output=True, text=True, **kw)


class MakeBundle(TG.Base):
    def src(self):
        s = os.path.join(self.t.name, "mygame")
        for d in ("config", "logs", "__pycache__", ".godot", "addons/mpf-gmc", "addons/mine", "pup"):
            os.makedirs(os.path.join(s, d))
        for rel, data in (("project.godot", "[application]\n"), ("config/config.yaml", "x: 1\n"), ("config/hw_virtual.yaml", "x: 1\n"),
                          ("config/hw_proc.yaml", "x: 1\n"), (".godot/uid_cache.bin", "u"), ("addons/mpf-gmc/plugin.cfg", "own copy"),
                          ("addons/mine/a.gd", "x"), ("pup/manifest.json", "{}"), ("logs/a.log", "log"), ("__pycache__/x.pyc", "c")):
            with open(os.path.join(s, rel), "w") as f:
                f.write(data)
        return s

    def unpack(self, arc):
        import tarfile
        with tarfile.open(arc) as t:
            names = t.getnames()
            b = json.load(t.extractfile([n for n in names if n.endswith("/bundle.json")][0]))
        return b, names

    def test_format_2_bundle_installs_and_the_platform_starts_it(self):
        out = os.path.join(self.t.name, "out")
        r = tool("make_bundle.py", self.src(), "--id", "my-game", "--name", "My game", "--version", "2.1", "--keep", "data",
                 "--hardware", "virtual=hw_virtual", "--hardware", "proc=hw_proc", "--dmd-rom", "mygame_100",
                 "--pup-rom", "mygame_100", "--pup-manifest", "pup/manifest.json",
                 "--platform-addon", "gde_gozen", "-o", out)            # mpf-gmc: built by `mpf_godot setup`, absent from a test machine
        self.assertEqual(r.returncode, 0, r.stderr)
        arc = os.path.join(out, "my-game@2.1.tar.xz")
        b, names = self.unpack(arc)
        self.assertEqual(b["format"], 2)
        self.assertEqual(b["mpf"], {"configs": ["config"], "hardware": {"virtual": ["hw_virtual"], "proc": ["hw_proc"]}})
        self.assertEqual(b["pup"], {"rom": "mygame_100", "manifest": "game/pup/manifest.json"})
        self.assertEqual(b["platform_addons"], ["gde_gozen"])
        self.assertEqual(b["keep_on_update"], ["game/data"])
        for k in ("run", "options", "launch", "extra", "requires"):
            self.assertNotIn(k, b)
        self.assertEqual(K.problems(b), [])
        self.assertIn("my-game@2.1/game/addons/mine/a.gd", names)                       # the game's own add-on stays
        self.assertIn("my-game@2.1/game/addons/mpf-gmc/plugin.cfg", names)              # not a platform add-on here: the game's copy
        self.assertFalse(any("scripts/package" in n or "/logs/" in n or "__pycache__" in n for n in names))
        sha = open(arc + ".sha256").read().split()[0]
        G.JOB_LOCK.acquire()
        G.run_job(G.install_game, arc, sha)
        self.assertEqual(G.JOB["state"], "done", G.JOB["msg"] + G.JOB["log"])
        game = os.path.join(C.GAMES, "my-game@2.1")
        self.assertTrue(os.path.isfile(os.path.join(game, "game", "config", "hw_proc.yaml")))
        self.assertEqual(K.plan(game, b, "x86")["configs"], ["config", "hw_virtual"])
        K.set_values(game, b, [("machine.hardware", "proc")])
        self.assertEqual(K.plan(game, b, "x86")["configs"], ["config", "hw_proc"])
        self.assertRaises(ValueError, K.set_values, game, b, [("machine.hardware", "bogus")])

    def test_one_hardware_set_needs_no_setting(self):
        out = os.path.join(self.t.name, "out")
        r = tool("make_bundle.py", self.src(), "--id", "one", "--version", "1", "--hardware", "virtual=hw_virtual", "-o", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        b, names = self.unpack(os.path.join(out, "one@1.tar.xz"))
        self.assertNotIn("settings", b)
        self.assertNotIn("one@1/settings.json", names)
        self.assertEqual(b["platform_addons"], ["gde_gozen", "mpf-gmc"])                # the default
        self.assertNotIn("one@1/game/addons/mpf-gmc/plugin.cfg", names)                 # the platform's copy is used

    def test_refuses_what_breaks_the_contract(self):
        s = self.src()
        out = self.t.name
        r = tool("make_bundle.py", s, "--id", "x", "--version", "1", "--hardware", "virtual=no_such", "-o", out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no_such.yaml", r.stderr)
        os.remove(os.path.join(s, "project.godot"))
        r = tool("make_bundle.py", s, "--id", "x", "--version", "1", "-o", out)
        self.assertIn("project.godot", r.stderr)

    def test_bad_arguments(self):
        s = self.src()
        for extra in (["--id", "Bad Id", "--version", "1"], ["--id", "ok", "--version", "bad version"], ["--id", "ok", "--version", "1", "--keep", "../x"],
                      ["--id", "ok", "--version", "1", "--hardware", "virtual"], ["--id", "ok", "--version", "1", "--pup-rom", "r"],
                      ["--id", "ok", "--version", "1", "--start", "mpf both"]):
            self.assertNotEqual(tool("make_bundle.py", s, *extra, "-o", self.t.name).returncode, 0, extra)


@unittest.skipUnless(shutil.which("sfdisk") or os.path.exists("/usr/sbin/sfdisk"), "needs sfdisk")
@unittest.skipUnless(shutil.which("debugfs") or os.path.exists("/usr/sbin/debugfs"), "needs debugfs")
def read_fat32(img, offset):
    """{name: bytes} of the files in /inbox of the FAT32 volume at byte OFFSET (a small reader, long names included)."""
    import struct
    with open(img, "rb") as f:
        f.seek(offset)
        boot = f.read(512)
        bps, spc, res, nfat = struct.unpack_from("<HBHB", boot, 11)
        fatsz, = struct.unpack_from("<I", boot, 36)
        root, = struct.unpack_from("<I", boot, 44)
        assert boot[71:82] == b"MPFSEED    " and boot[510:512] == b"\x55\xaa"
        f.seek(offset + res * bps)
        fat = f.read(fatsz * bps)
        data = res + nfat * fatsz

        def chain(c):
            while c < 0x0FFFFFF8:
                yield c
                c = struct.unpack_from("<I", fat, c * 4)[0] & 0x0FFFFFFF

        def read(c, size=None):
            out = b""
            for k in chain(c):
                f.seek(offset + (data + (k - 2) * spc) * bps)
                out += f.read(spc * bps)
            return out if size is None else out[:size]

        def entries(c):
            raw, lfn, res_ = read(c), [], {}
            for i in range(0, len(raw), 32):
                e = raw[i:i + 32]
                if e[0] == 0:
                    break
                if e[0] == 0xE5:
                    continue
                if e[11] == 0x0F:
                    lfn.insert(0, e[1:11] + e[14:26] + e[28:32])
                    continue
                if e[11] & 0x08:
                    lfn = []
                    continue
                name = b"".join(lfn).decode("utf-16-le").split("\0")[0] if lfn else e[:11].decode().strip()
                lfn = []
                c_ = (struct.unpack_from("<H", e, 20)[0] << 16) | struct.unpack_from("<H", e, 26)[0]
                res_[name] = (e[11], c_, struct.unpack_from("<I", e, 28)[0])
            return res_

        top = entries(root)
        assert top["inbox"][0] & 0x10
        return {n: read(c, sz) if sz else b"" for n, (a, c, sz) in entries(top["inbox"][1]).items() if not a & 0x10}


class InjectImage(unittest.TestCase):
    def disk(self, t, label="gpt"):
        """A 64 MB image with two partitions, made by hand: GPT (with its backup at the end) or MBR."""
        import struct, uuid, zlib
        img = os.path.join(t, "disk.img")
        n = 64 << 20 >> 9
        with open(img, "wb") as f:
            f.truncate(n * 512)
            parts = [(2048, 2048 + 32768 - 1, 0), (34816, 34816 + 65536 - 1, 1)]
            if label == "dos":
                mbr = bytearray(512)
                for i, (a, b, _) in enumerate(parts):
                    mbr[446 + 16 * i + 4] = 0x0C if i == 0 else 0x83
                    struct.pack_into("<II", mbr, 446 + 16 * i + 8, a, b - a + 1)
                mbr[510:512] = b"\x55\xaa"
                f.write(mbr)
                return img
            pm = bytearray(512)
            pm[446 + 4] = 0xEE
            struct.pack_into("<II", pm, 446 + 8, 1, n - 1)
            pm[510:512] = b"\x55\xaa"
            f.write(pm)
            ent = bytearray(128 * 128)
            for i, (a, b, k) in enumerate(parts):
                e = ent[i * 128:(i + 1) * 128]
                e[0:16] = uuid.uuid4().bytes_le
                e[16:32] = uuid.uuid4().bytes_le
                struct.pack_into("<QQQ", e, 32, a, b, 0)
                ent[i * 128:(i + 1) * 128] = e
            for cur, other, elba in ((1, n - 1, 2), (n - 1, 1, n - 33)):
                h = bytearray(92)
                h[0:8] = b"EFI PART"
                struct.pack_into("<IIIIQQQQ", h, 8, 0x10000, 92, 0, 0, cur, other, 34, n - 34)
                h[56:72] = uuid.uuid4().bytes_le
                struct.pack_into("<QIII", h, 72, elba, 128, 128, zlib.crc32(bytes(ent)) & 0xFFFFFFFF)
                struct.pack_into("<I", h, 16, zlib.crc32(bytes(h)) & 0xFFFFFFFF)
                f.seek(cur * 512)
                f.write(h)
                f.seek(elba * 512)
                f.write(ent)
        return img

    def seed(self, img):
        """(start sector, size in sectors) of the MPFSEED partition, and the GPT checked: both headers and the entry array CRC."""
        import struct, zlib
        with open(img, "rb") as f:
            mbr = f.read(512)
            if mbr[446 + 4] != 0xEE:
                i = 2
                a, b = struct.unpack_from("<II", mbr, 446 + 16 * i + 8)
                self.assertEqual(mbr[446 + 16 * i + 4], 0x0C)
                return a, b
            size = os.path.getsize(img) // 512
            res = None
            for lba in (1, size - 1):
                f.seek(lba * 512)
                h = bytearray(f.read(92))
                crc = struct.unpack_from("<I", h, 16)[0]
                struct.pack_into("<I", h, 16, 0)
                self.assertEqual(zlib.crc32(bytes(h)) & 0xFFFFFFFF, crc, f"header at {lba}")
                cur, other, first, last, elba = struct.unpack_from("<QQQQ", h, 24)[0], *struct.unpack_from("<Q", h, 32), *struct.unpack_from("<QQ", h, 40), struct.unpack_from("<Q", h, 72)[0]
                self.assertEqual((cur, last), (lba, size - 34))
                nent, esz, ecrc = struct.unpack_from("<III", h, 80)
                f.seek(elba * 512)
                ent = f.read(nent * esz)
                self.assertEqual(zlib.crc32(ent) & 0xFFFFFFFF, ecrc, f"entries of {lba}")
                for i in range(nent):
                    e = ent[i * esz:(i + 1) * esz]
                    if e[56:70].decode("utf-16-le") == "MPFSEED":
                        res = struct.unpack_from("<QQ", e, 32)
            self.assertIsNotNone(res)
            return res[0], res[1] - res[0] + 1

    def bundle(self, t):
        src = os.path.join(t, "g")
        os.makedirs(src)
        os.makedirs(os.path.join(src, "config"))
        for rel in ("project.godot", "config/config.yaml", "config/hw_virtual.yaml"):
            open(os.path.join(src, rel), "w").write("x: 1\n")
        tool("make_bundle.py", src, "--id", "x", "--version", "1", "--hardware", "virtual=hw_virtual", "-o", t)
        with open(os.path.join(t, "pack.zip"), "wb") as f:
            f.write(b"PK" + os.urandom(2 << 20))
        return os.path.join(t, "x@1.tar.xz"), os.path.join(t, "pack.zip")

    def test_gpt_and_dos_images(self):
        for label in ("gpt", "dos"):
            with tempfile.TemporaryDirectory() as t:
                img = self.disk(t, label)
                bundle, pack = self.bundle(t)
                before = open(img, "rb").read(48 << 20)
                r = tool("inject_image.py", img, "--bundle", bundle, "--pup", pack + ":x", "-o", os.path.join(t, "out.img"))
                self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
                self.assertEqual(open(img, "rb").read(48 << 20), before)         # the original is not touched
                out = os.path.join(t, "out.img")
                start, size = self.seed(out)
                self.assertGreaterEqual(start, 100352, label)
                files = read_fat32(out, start * 512)
                self.assertEqual(sorted(files), ["01_x@1.tar.xz", "01_x@1.tar.xz.sha256", "x.pup.zip"], label)
                self.assertEqual(files["x.pup.zip"], open(pack, "rb").read())
                self.assertEqual(files["01_x@1.tar.xz"], open(bundle, "rb").read())
                self.assertIn(files["01_x@1.tar.xz.sha256"].split()[0].decode(), [__import__("hashlib").sha256(files["01_x@1.tar.xz"]).hexdigest()])
                if shutil.which("fsck.vfat") or os.path.exists("/usr/sbin/fsck.vfat"):
                    part = os.path.join(t, "seed.img")
                    with open(out, "rb") as f, open(part, "wb") as g:
                        f.seek(start * 512)
                        g.write(f.read(size * 512))
                    r = subprocess.run([shutil.which("fsck.vfat") or "/usr/sbin/fsck.vfat", "-n", part], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                again = tool("inject_image.py", out, "--bundle", bundle, "-o", os.path.join(t, "again.img"))
                if label == "gpt":
                    self.assertNotEqual(again.returncode, 0)                    # a seed partition is there already

    def test_in_place_and_xz(self):
        with tempfile.TemporaryDirectory() as t:
            img = self.disk(t)
            import lzma
            with open(img, "rb") as f, lzma.open(img + ".xz", "wb") as g:
                g.write(f.read())
            bundle, _ = self.bundle(t)
            r = tool("inject_image.py", img + ".xz", "--bundle", bundle, "-o", os.path.join(t, "o.img"))
            self.assertEqual(r.returncode, 0, r.stderr)
            start, _ = self.seed(os.path.join(t, "o.img"))
            self.assertIn("01_x@1.tar.xz", read_fat32(os.path.join(t, "o.img"), start * 512))
            self.assertEqual(tool("inject_image.py", img, "--bundle", bundle, "--in-place").returncode, 0)

    def test_nothing_to_add_and_missing_files(self):
        with tempfile.TemporaryDirectory() as t:
            img = self.disk(t)
            self.assertNotEqual(tool("inject_image.py", img).returncode, 0)
            self.assertNotEqual(tool("inject_image.py", img, "--bundle", os.path.join(t, "none.tar.xz")).returncode, 0)


if __name__ == "__main__":
    unittest.main()
