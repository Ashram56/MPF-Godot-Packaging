"""Sound output choice (common/netconfig/mpf_audio.py): devices from a fake /proc/asound per platform, the saved choice, the I2S boot
configuration, the ALSA configuration the game is started with (checked against the real alsa-lib when `aplay` is installed)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common", "netconfig"))
import mpf_audio as AU  # noqa: E402
import mpf_common as C  # noqa: E402
import mpf_web as W  # noqa: E402


def fake_asound(root, cards):
    """cards: [(index, id, short, long, {dev: pcm name}, usb, [monitor_present...])]"""
    os.makedirs(root, exist_ok=True)
    lines = []
    for idx, cid, short, long_, pcms, usb, elds in cards:
        lines += [f" {idx} [{cid:<14}]: {short}", f"                      {long_}"]
        d = os.path.join(root, f"card{idx}")
        for dev, name in pcms.items():
            os.makedirs(os.path.join(d, f"pcm{dev}p"), exist_ok=True)
            open(os.path.join(d, f"pcm{dev}p", "info"), "w").write(f"card: {idx}\ndevice: {dev}\nid: x\nname: {name}\n")
        for i, on in enumerate(elds):
            open(os.path.join(d, f"eld#0.{i}"), "w").write(f"monitor_present\t\t{int(on)}\n")
        if usb:
            open(os.path.join(d, "usbid"), "w").write("0d8c:0014\n")
    open(os.path.join(root, "cards"), "w").write("\n".join(lines) + "\n")


X86 = [(0, "PCH", "HDA-Intel - HDA Intel PCH", "HDA Intel PCH at 0xdf240000 irq 140", {0: "ALC269VC Analog", 3: "HDMI 0", 7: "HDMI 1"}, False, [True, False]),
       (1, "Device", "USB-Audio - USB PnP Sound Device", "C-Media USB PnP Sound Device at usb-0000:00:14.0-3", {0: "USB Audio"}, True, [])]
RPI5 = [(0, "vc4hdmi0", "vc4-hdmi-0 - vc4-hdmi-0", "vc4-hdmi-0", {0: "MAI PCM i2s-hifi-0"}, False, []),
        (1, "vc4hdmi1", "vc4-hdmi-1 - vc4-hdmi-1", "vc4-hdmi-1", {0: "MAI PCM i2s-hifi-0"}, False, [])]
RPI4_DAC = [(0, "Headphones", "bcm2835 Headphones - bcm2835 Headphones", "bcm2835 Headphones", {0: "bcm2835 Headphones"}, False, []),
            (1, "sndrpihifiberry", "snd_rpi_hifiberry_dac", "snd_rpi_hifiberry_dac", {0: "HiFiBerry DAC HiFi pcm5102a-hifi-0"}, False, [])]
JETSON = [(0, "HDA", "NVIDIA Jetson Xavier NX HDA - HDA NVIDIA", "HDA NVIDIA at 0x3510000", {3: "HDMI 0"}, False, [True]),
          (1, "APE", "NVIDIA Jetson Xavier NX APE - NVIDIA Jetson Xavier NX APE", "NVIDIA Jetson Xavier NX APE", {0: "admaif1"}, False, [])]


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        d = self.t.name
        self.saved = {k: getattr(AU, k) for k in ("PROC_ASOUND", "DT_MODEL", "BOOT_ID", "ALSA_RUN")}
        self.saved_c = {k: getattr(C, k) for k in ("STATE_DIR", "READONLY")}
        AU.PROC_ASOUND, AU.DT_MODEL = os.path.join(d, "asound"), os.path.join(d, "model")
        AU.BOOT_ID, AU.ALSA_RUN = os.path.join(d, "boot_id"), os.path.join(d, "run")
        C.STATE_DIR, C.READONLY = os.path.join(d, "state"), False
        open(AU.BOOT_ID, "w").write("boot-1\n")
        self.config = os.path.join(d, "config.txt")
        open(self.config, "w").write("dtparam=audio=on\nenable_uart=1\n")
        os.environ["MPF_BOOT_CONFIG"] = self.config
        self.addCleanup(os.environ.pop, "MPF_BOOT_CONFIG", None)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(AU, k, v)
        for k, v in self.saved_c.items():
            setattr(C, k, v)

    def machine(self, model, cards):
        open(AU.DT_MODEL, "wb").write(model.encode() + b"\0")
        fake_asound(AU.PROC_ASOUND, cards)


class Devices(Base):
    def test_x86_has_hdmi_analog_usb_and_no_i2s(self):
        with mock.patch("platform.machine", return_value="x86_64"):
            self.machine("", X86)
            os.unlink(AU.DT_MODEL)
            st = AU.state()
        self.assertEqual(st["platform"], "x86")
        self.assertEqual([k["id"] for k in st["kinds"]], ["hdmi", "analog", "usb"])
        self.assertEqual(st["dacs"], [])
        kind = {d["id"]: d["kind"] for d in st["devices"]}
        self.assertEqual(kind["hw:CARD=PCH,DEV=0"], "analog")
        self.assertEqual(kind["hw:CARD=PCH,DEV=3"], "hdmi")
        self.assertEqual(kind["hw:CARD=Device,DEV=0"], "usb")
        conn = {d["id"]: d["connected"] for d in st["devices"]}
        self.assertEqual((conn["hw:CARD=PCH,DEV=3"], conn["hw:CARD=PCH,DEV=7"]), (True, False))
        self.assertEqual(st["devices"][-1]["connected"], False)          # an HDMI port without a monitor comes last
        with self.assertRaises(ValueError):
            AU.choose("i2s", "hifiberry-dac")

    def test_pi5_offers_hdmi_i2s_usb_no_jack(self):
        self.machine("Raspberry Pi 5 Model B Rev 1.0", RPI5)
        st = AU.state()
        self.assertEqual(st["platform"], "rpi5")
        self.assertEqual([k["id"] for k in st["kinds"]], ["hdmi", "i2s", "usb"])
        self.assertEqual([d["id"] for d in st["devices"]], ["hw:CARD=vc4hdmi0,DEV=0", "hw:CARD=vc4hdmi1,DEV=0"])
        self.assertIn("hifiberry-dac", [d["id"] for d in st["dacs"]])

    def test_pi4_keeps_its_jack_and_sees_a_dac_card(self):
        self.machine("Raspberry Pi 4 Model B Rev 1.4", RPI4_DAC)
        st = AU.state()
        self.assertEqual([k["id"] for k in st["kinds"]], ["hdmi", "analog", "i2s", "usb"])
        kind = {d["card"]: d["kind"] for d in st["devices"]}
        self.assertEqual((kind["Headphones"], kind["sndrpihifiberry"]), ("analog", "i2s"))

    def test_jetson_apes_card_is_i2s_hda_is_hdmi(self):
        self.machine("NVIDIA Jetson Xavier NX Developer Kit", JETSON)
        st = AU.state()
        self.assertEqual(st["platform"], "jetson")
        self.assertEqual({d["card"]: d["kind"] for d in st["devices"]}, {"HDA": "hdmi", "APE": "i2s"})
        self.assertEqual([d["id"] for d in st["dacs"]], ["i2s2"])

    def test_no_sound_card_at_all(self):
        self.machine("Raspberry Pi 5", [])
        self.assertEqual(AU.state()["devices"], [])


class Choice(Base):
    def test_choose_a_present_device_is_saved_and_applied(self):
        self.machine("Raspberry Pi 5", RPI5)
        msg, restart = AU.choose("hw:CARD=vc4hdmi1,DEV=0")
        self.assertTrue(restart)
        self.assertEqual(json.load(open(os.path.join(C.STATE_DIR, "audio.json")))["output"], "hw:CARD=vc4hdmi1,DEV=0")
        self.assertEqual(AU.effective(), "hw:CARD=vc4hdmi1,DEV=0")
        env = AU.prepare()
        self.assertEqual(env, {"ALSA_CONFIG_PATH": os.path.join(AU.ALSA_RUN, "alsa.conf")})
        over = open(os.path.join(AU.ALSA_RUN, "override.conf")).read()
        self.assertIn('slave.pcm "hw:CARD=vc4hdmi1,DEV=0"', over)
        self.assertIn("card vc4hdmi1", over)

    def test_unknown_or_unplugged_device_is_refused_and_a_missing_one_falls_back(self):
        self.machine("Raspberry Pi 5", RPI5)
        for bad in ("hw:CARD=nothing,DEV=0", 'x"; evil', ""):
            with self.assertRaises(ValueError):
                AU.choose(bad)
        AU.choose("hw:CARD=vc4hdmi1,DEV=0")
        fake_asound(AU.PROC_ASOUND + "2", [])                               # the device goes away
        AU.PROC_ASOUND += "2"
        st = AU.state()
        self.assertTrue(st["missing"])
        self.assertIsNone(AU.effective())
        self.assertEqual(AU.prepare(), {})                                 # the image's default stays in charge

    def test_auto_applies_nothing(self):
        self.machine("Raspberry Pi 5", RPI5)
        AU.choose("hw:CARD=vc4hdmi1,DEV=0")
        AU.choose("auto")
        self.assertEqual(AU.prepare(), {})

    def test_pi_i2s_writes_a_managed_block_and_asks_for_a_reboot(self):
        self.machine("Raspberry Pi 4 Model B", RPI4_DAC[:1])
        with self.assertRaises(ValueError):
            AU.choose("i2s", "")                                           # a DAC must be named
        msg, restart = AU.choose("i2s", "hifiberry-dac")
        self.assertFalse(restart)
        text = open(self.config).read()
        self.assertIn(AU.BEGIN + "\ndtoverlay=hifiberry-dac\ndtparam=audio=off\n" + AU.END, text)
        self.assertTrue(text.startswith("dtparam=audio=on\nenable_uart=1\n"))
        st = AU.state()
        self.assertTrue(st["reboot"])
        self.assertEqual((st["output"], st["dac"]), ("i2s-pending", "hifiberry-dac"))
        AU.choose("i2s", "iqaudio-dac")                                    # another DAC replaces the block
        text = open(self.config).read()
        self.assertEqual(text.count(AU.BEGIN), 1)
        self.assertIn("dtoverlay=iqaudio-dac", text)
        self.assertNotIn("hifiberry", text)
        open(AU.BOOT_ID, "w").write("boot-2\n")                             # rebooted
        self.assertFalse(AU.state()["reboot"])
        AU.choose("auto")                                                  # leaving I2S removes the block
        self.assertNotIn(AU.BEGIN, open(self.config).read())

    def test_pi5_block_does_not_touch_onboard_audio_param(self):
        self.machine("Raspberry Pi 5", RPI5)
        AU.choose("i2s", "i2s-dac")
        self.assertNotIn("audio=off", open(self.config).read())

    def test_i2s_with_the_dac_card_present_selects_it(self):
        self.machine("Raspberry Pi 4 Model B", RPI4_DAC)
        AU.choose("i2s", "hifiberry-dac")                                   # config.txt already says so? first write: reboot still needed
        open(AU.BOOT_ID, "w").write("boot-2\n")
        msg, restart = AU.choose("i2s", "hifiberry-dac")                    # nothing changes: the card is there
        self.assertTrue(restart)
        self.assertEqual(AU.load()["output"], "hw:CARD=sndrpihifiberry,DEV=0")

    def test_jetson_i2s_runs_jetson_io(self):
        self.machine("NVIDIA Jetson Xavier NX", JETSON[:1])
        tool = os.path.join(self.t.name, "config-by-function.py")
        log = os.path.join(self.t.name, "log")
        open(tool, "w").write(f"import sys\nopen({log!r},'w').write(' '.join(sys.argv[1:]))\n")
        AU.JETSON_IO = tool
        AU.choose("i2s", "i2s2")
        self.assertEqual(open(log).read(), "-o dtbo i2s2")
        self.assertTrue(AU.state()["reboot"])


@unittest.skipUnless(shutil.which("aplay"), "alsa-utils not installed")
class RealAlsa(Base):
    def test_override_beats_the_images_asound_conf(self):
        """The ALSA configuration the launcher writes really replaces the default, with /etc/asound.conf pointing elsewhere."""
        if not any(os.path.isfile(p) for p in AU.ALSA_MAIN):
            self.skipTest("no alsa.conf")
        self.machine("Raspberry Pi 5", RPI5)
        AU.choose("hw:CARD=vc4hdmi0,DEV=0")
        entry, over = AU.alsa_text("hw:CARD=vc4hdmi0,DEV=0")
        os.makedirs(AU.ALSA_RUN)
        open(os.path.join(AU.ALSA_RUN, "alsa.conf"), "w").write(entry)
        # a null slave instead of the unreachable card, to see the default being ours
        open(os.path.join(AU.ALSA_RUN, "override.conf"), "w").write(over.replace('"hw:CARD=vc4hdmi0,DEV=0"', '"null"'))
        r = subprocess.run(["aplay", "-L"], env=dict(os.environ, ALSA_CONFIG_PATH=os.path.join(AU.ALSA_RUN, "alsa.conf")),
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run(["aplay", "-q", "-D", "default", "/dev/null"], env=dict(os.environ, ALSA_CONFIG_PATH=os.path.join(AU.ALSA_RUN, "alsa.conf")),
                           capture_output=True, text=True)
        self.assertNotIn("vc4hdmi0", r.stderr)


class Page(Base):
    def test_audio_api_lists_and_sets(self):
        self.machine("Raspberry Pi 5", RPI5)
        with mock.patch.object(W.N, "authorized", return_value=True), mock.patch.object(W.G, "game_running", return_value=False):
            srv = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            st = json.load(urllib.request.urlopen(base + "/api/audio"))
            self.assertEqual(st["platform"], "rpi5")
            req = urllib.request.Request(base + "/api/audio", data=b"do=set&output=hw%3ACARD%3Dvc4hdmi1%2CDEV%3D0")
            self.assertTrue(json.load(urllib.request.urlopen(req))["ok"])
            self.assertEqual(AU.load()["output"], "hw:CARD=vc4hdmi1,DEV=0")
            self.assertIn("audOut", urllib.request.urlopen(base + "/").read().decode())


if __name__ == "__main__":
    unittest.main()
