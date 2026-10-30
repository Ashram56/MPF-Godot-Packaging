"""Sound output of the machine: which ALSA device the game plays on. Standard library only, no game knowledge.

The choice is made on the setup page (port 8080), kept in `<STATE_DIR>/audio.json` (the data partition on a read-only image) and applied
at every game start by `prepare()`, which writes an ALSA configuration in RAM (`/run/mpf-audio/alsa.conf`) and returns the environment
variable that points the game at it (`ALSA_CONFIG_PATH`). Nothing on the read-only root changes: "auto" leaves the image's own
/etc/asound.conf in charge.

The devices offered are the ones the kernel reports now (/proc/asound), sorted into kinds by what they are: hdmi (HDMI and DisplayPort),
analog (3.5 mm jack, codec line out), usb, i2s. What a platform can offer at all is `KINDS`: a PC has no I2S header, a Raspberry Pi 5
no jack. An I2S output needs a device-tree overlay read at boot, so it is a two step choice (DAC, then reboot): on a Raspberry Pi a
managed block in config.txt on the boot partition, on a Jetson the header function enabled with NVIDIA's jetson-io.
"""
import json
import math
import os
import re
import struct
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpf_common as C  # noqa: E402
from mpf_common import run  # noqa: E402

PROC_ASOUND = os.environ.get("MPF_PROC_ASOUND", "/proc/asound")
DT_MODEL = os.environ.get("MPF_DT_MODEL", "/proc/device-tree/model")
BOOT_ID = os.environ.get("MPF_BOOT_ID_FILE", "/proc/sys/kernel/random/boot_id")
ALSA_RUN = os.environ.get("MPF_AUDIO_RUN", "/run/mpf-audio")
ALSA_MAIN = ("/usr/share/alsa/alsa.conf", "/usr/share/alsa-lib/alsa.conf", "/etc/alsa/alsa.conf")
JETSON_IO = os.environ.get("MPF_JETSON_IO", "/opt/nvidia/jetson-io/config-by-function.py")

BEGIN = "# --- mpf-audio (written by the setup page, do not edit) ---"
END = "# --- end mpf-audio ---"
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")

# what each platform can offer, in the order the page shows it
KINDS = {
    "x86": ["hdmi", "analog", "usb"],
    "rpi4": ["hdmi", "analog", "i2s", "usb"],
    "rpi5": ["hdmi", "i2s", "usb"],
    "jetson": ["hdmi", "i2s", "usb"],
}
KIND_LABEL = {"hdmi": "HDMI / DisplayPort", "analog": "Analog (jack, line out)", "usb": "USB", "i2s": "I2S", "other": "Other"}

# I2S DACs and amplifiers a Raspberry Pi knows by overlay: name -> (label, overlay line). `i2s-dac` is the generic one for a DAC
# without control bus (PCM5102A boards); the HiFiBerry DAC overlay also serves those.
PI_DACS = {
    "hifiberry-dac": ("HiFiBerry DAC / DAC+ Light / Zero, PCM5102A boards", "dtoverlay=hifiberry-dac"),
    "hifiberry-dacplus": ("HiFiBerry DAC+ / DAC+ Pro", "dtoverlay=hifiberry-dacplus"),
    "hifiberry-dacplushd": ("HiFiBerry DAC2 HD", "dtoverlay=hifiberry-dacplushd"),
    "hifiberry-digi": ("HiFiBerry Digi+ (S/PDIF)", "dtoverlay=hifiberry-digi"),
    "hifiberry-amp": ("HiFiBerry Amp", "dtoverlay=hifiberry-amp"),
    "iqaudio-dac": ("IQaudIO DAC", "dtoverlay=iqaudio-dac"),
    "iqaudio-dacplus": ("IQaudIO DAC+ / Pi-DigiAMP+", "dtoverlay=iqaudio-dacplus"),
    "justboom-dac": ("JustBoom DAC / Amp", "dtoverlay=justboom-dac"),
    "justboom-digi": ("JustBoom Digi (S/PDIF)", "dtoverlay=justboom-digi"),
    "allo-boss": ("Allo Boss DAC", "dtoverlay=allo-boss-dac-pcm512x-audio"),
    "allo-piano": ("Allo Piano DAC", "dtoverlay=allo-piano-dac-pcm512x-audio"),
    "audioinjector": ("AudioInjector Stereo", "dtoverlay=audioinjector-wm8731-audio"),
    "max98357a": ("MAX98357A I2S amplifier", "dtoverlay=max98357a"),
    "i2s-dac": ("Generic I2S DAC (i2s-dac)", "dtoverlay=i2s-dac"),
}
JETSON_DACS = {"i2s2": ("40-pin header, I2S2 (jetson-io), a DAC without control bus", "i2s2")}


def platform():
    """'rpi4' | 'rpi5' | 'jetson' | 'x86' | 'other', from the device tree's model (ARM boards) or the CPU."""
    try:
        model = open(DT_MODEL, "rb").read().decode("utf-8", "replace").strip("\0 \n")
    except OSError:
        model = ""
    m = model.lower()
    if "jetson" in m or "nvidia" in m:
        return "jetson"
    if "raspberry pi 5" in m:
        return "rpi5"
    if "raspberry pi 4" in m or "raspberry pi 400" in m or "compute module 4" in m:
        return "rpi4"
    import platform as _p
    return "x86" if _p.machine() in ("x86_64", "AMD64", "i686") else "other"


def _read(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def cards():
    """[{index, id, short, long, usb}] from /proc/asound/cards."""
    out = []
    lines = _read(os.path.join(PROC_ASOUND, "cards")).splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^\s*(\d+)\s+\[([^\]]*)\]:\s*(.*)$", line)
        if m:
            idx = int(m[1])
            out.append({"index": idx, "id": m[2].strip(), "short": m[3].strip(),
                        "long": lines[i + 1].strip() if i + 1 < len(lines) else "",
                        "usb": os.path.exists(os.path.join(PROC_ASOUND, f"card{idx}", "usbid"))})
    return out


def _eld_present(card_index):
    """Monitor-present flags of a card's HDMI ELD files, in device order: [True, False, ...]."""
    d = os.path.join(PROC_ASOUND, f"card{card_index}")
    try:
        names = sorted((n for n in os.listdir(d) if n.startswith("eld#")),
                       key=lambda n: [int(x) for x in re.findall(r"\d+", n)])
    except OSError:
        return []
    return [bool(re.search(r"monitor_present\s+1", _read(os.path.join(d, n)))) for n in names]


def classify(card, pcm_name):
    text = f"{card['id']} {card['short']} {card['long']} {pcm_name}"
    if card["usb"] or "usb-audio" in text.lower():
        return "usb"
    if re.search(r"hdmi|displayport|\bdp\b", text, re.I):
        return "hdmi"
    if re.search(r"sndrpi|hifiberry|iqaudio|justboom|allo|audioinjector|max98357|i2s|\bape\b|\bdac\b|pisound", text, re.I):
        return "i2s"
    return "analog"


def devices():
    """Every playback device now present: [{id, kind, label, card, connected}]. `id` is the ALSA name (card by id, so a USB stick
    keeps its name when the numbers shuffle); `connected` is True/False for an HDMI output that reports its monitor, else None."""
    out = []
    for c in cards():
        base = os.path.join(PROC_ASOUND, f"card{c['index']}")
        try:
            pcms = sorted(int(n[3:-1]) for n in os.listdir(base) if re.fullmatch(r"pcm\d+p", n))
        except OSError:
            pcms = []
        elds = _eld_present(c["index"])
        hdmi_i = 0
        for dev in pcms:
            info = _read(os.path.join(base, f"pcm{dev}p", "info"))
            m = re.search(r"^name:\s*(.*)$", info, re.M)
            pcm_name = m[1].strip() if m else ""
            kind = classify(c, pcm_name)
            connected = None
            if kind == "hdmi" and hdmi_i < len(elds):
                connected = elds[hdmi_i]
            if kind == "hdmi":
                hdmi_i += 1
            if not ID_RE.match(c["id"]):
                continue
            label = c["short"] or c["id"]
            if pcm_name and pcm_name.lower() not in label.lower():
                label += f" — {pcm_name}"
            out.append({"id": f"hw:CARD={c['id']},DEV={dev}", "kind": kind, "label": f"{label} ({c['id']})",
                        "card": c["id"], "connected": connected})
    out.sort(key=lambda d: (d["connected"] is False, d["card"], d["id"]))
    return out


# ---------------------------------------------------------------- the saved choice
def _file():
    return os.path.join(C.STATE_DIR, "audio.json")


def load():
    try:
        d = json.load(open(_file()))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(d):
    os.makedirs(os.path.dirname(_file()), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(_file()))
    with os.fdopen(fd, "w") as f:
        json.dump(d, f)
    os.replace(tmp, _file())


def boot_id():
    return _read(BOOT_ID).strip()


# ---------------------------------------------------------------- I2S: the boot-time part
def boot_config():
    """Path of the Raspberry Pi's config.txt, or '' (not a Pi)."""
    for p in (os.environ.get("MPF_BOOT_CONFIG"), os.path.join(C.BOOT_MOUNT or "/boot/firmware", "config.txt"), "/boot/config.txt"):
        if p and os.path.isfile(p):
            return p
    return ""


def pi_block(dac, plat):
    lines = [BEGIN, PI_DACS[dac][1]]
    if plat == "rpi4":
        lines.append("dtparam=audio=off")       # the jack's card would take number 0 and the DAC's HAT docs ask for it off
    return "\n".join(lines + [END]) + "\n"


def _strip_block(text):
    return re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", "", text, flags=re.S)


def current_pi_dac():
    text = _read(boot_config())
    m = re.search(re.escape(BEGIN) + r"\n(dtoverlay=\S+)", text)
    if not m:
        return ""
    return next((k for k, v in PI_DACS.items() if v[1] == m[1]), "")


def write_pi_config(dac, plat):
    """Put (dac) or remove (dac='') the managed block in config.txt; True when the file changed."""
    path = boot_config()
    if not path:
        raise ValueError("no config.txt found: this is not a Raspberry Pi image")
    old = _read(path)
    new = _strip_block(old)
    if dac:
        if dac not in PI_DACS:
            raise ValueError("unknown DAC")
        new = new.rstrip("\n") + "\n\n" + pi_block(dac, plat)
    if new == old:
        return False
    with C.writable(path):
        tmp = path + ".mpf-new"
        with open(tmp, "w") as f:
            f.write(new)
        os.replace(tmp, path)
    return True


def jetson_io(function):
    """Enable a 40-pin header function (i2s2) with NVIDIA's jetson-io, which writes an overlay and the extlinux entry; True when it ran."""
    if not os.path.exists(JETSON_IO):
        raise ValueError("jetson-io is not installed on this image")
    with C.writable("/boot"):
        r = run("python3", JETSON_IO, "-o", "dtbo", function)
    if r.returncode:
        raise ValueError((r.stderr or r.stdout).strip()[-300:] or "jetson-io failed")
    return True


# ---------------------------------------------------------------- state and choice
def dac_list(plat):
    if plat in ("rpi4", "rpi5"):
        return [{"id": k, "label": v[0]} for k, v in PI_DACS.items()]
    if plat == "jetson":
        return [{"id": k, "label": v[0]} for k, v in JETSON_DACS.items()]
    return []


def state():
    plat = platform()
    kinds = KINDS.get(plat, ["hdmi", "analog", "usb"])
    devs = devices()
    ch = load()
    present = {d["id"] for d in devs}
    out = ch.get("output", "auto")
    reboot = bool(ch.get("reboot_boot_id")) and ch.get("reboot_boot_id") == boot_id()
    return {
        "platform": plat, "kinds": [{"id": k, "label": KIND_LABEL[k]} for k in kinds],
        "devices": [dict(d, offered=d["kind"] in kinds) for d in devs],
        "dacs": dac_list(plat),
        "output": out, "dac": ch.get("dac", ""),
        "missing": out not in ("auto", "i2s-pending") and out not in present,
        "reboot": reboot,
    }


def choose(output, dac=""):
    """Save the choice: output is 'auto', the id of a device now present, or 'i2s' with the DAC to configure (needs a reboot).
    Returns (message, game_restart_needed)."""
    plat = platform()
    ch = load()
    kinds = KINDS.get(plat, [])
    if output == "auto":
        msg = "Automatic: the image's own default."
        if plat in ("rpi4", "rpi5") and current_pi_dac():
            if write_pi_config("", plat):
                ch["reboot_boot_id"] = boot_id()
                msg += " The I2S DAC is removed from config.txt: reboot to apply."
        ch.update(output="auto", dac="")
        save(ch)
        return msg, True
    if output == "i2s":
        if "i2s" not in kinds:
            raise ValueError("this machine has no I2S output")
        if not dac:
            raise ValueError("choose the DAC")
        if plat in ("rpi4", "rpi5"):
            changed = write_pi_config(dac, plat)
        elif plat == "jetson":
            if dac not in JETSON_DACS:
                raise ValueError("unknown DAC")
            changed = jetson_io(JETSON_DACS[dac][1])
        else:
            raise ValueError("this machine has no I2S output")
        i2s = [d for d in devices() if d["kind"] == "i2s"]
        ch.update(dac=dac, output=i2s[0]["id"] if i2s and not changed else "i2s-pending")
        if changed:
            ch["reboot_boot_id"] = boot_id()
        save(ch)
        return ("I2S DAC saved: reboot to load its overlay." if changed else "I2S output selected."), not changed
    dev = next((d for d in devices() if d["id"] == output), None)
    if not dev:
        raise ValueError("that output is not present (any more)")
    if dev["kind"] not in kinds:
        raise ValueError("this machine does not offer that kind of output")
    ch.update(output=output)
    if dev["kind"] != "i2s":
        ch.pop("dac", None)
    save(ch)
    return "Output saved.", True


# ---------------------------------------------------------------- applying at game start
def alsa_text(pcm):
    """The ALSA configuration that makes `pcm` (a hw: name) the default, as (entry file, override file): plug on the raw device, like
    the images' own asound.conf (dmix stalls on some SoC codecs, and only the game plays sound). The entry file loads the system's
    alsa.conf and then, as a later hook, the override: ALSA loads /etc/asound.conf lazily after everything else, so a plain
    definition after the include would lose against the image's own default."""
    m = re.fullmatch(r"hw:CARD=([A-Za-z0-9_.-]+),DEV=(\d+)", pcm)
    if not m:
        raise ValueError("bad device name")
    main = next((p for p in ALSA_MAIN if os.path.isfile(p)), "")
    if not main:
        raise ValueError("alsa-lib's alsa.conf not found")
    over = os.path.join(ALSA_RUN, "override.conf")
    entry = f'<{main}>\n@hooks.1 {{\n    func load\n    files [ "{over}" ]\n    errors false\n}}\n'
    return entry, (f'pcm.!default {{\n    type plug\n    slave.pcm "{pcm}"\n}}\n'
                   f"ctl.!default {{\n    type hw\n    card {m[1]}\n}}\n")


def effective():
    """The device the saved choice means now, or None (automatic, or the device is not there: the image's default stays)."""
    out = load().get("output", "auto")
    return out if out in {d["id"] for d in devices()} else None


def prepare():
    """Called when the game starts, as root: write the ALSA configuration in RAM and return {'ALSA_CONFIG_PATH': ...} (or {})."""
    try:
        pcm = effective()
        if not pcm:
            return {}
        os.makedirs(ALSA_RUN, exist_ok=True)
        path = os.path.join(ALSA_RUN, "alsa.conf")
        entry, over = alsa_text(pcm)
        for name, text in (("override.conf", over), ("alsa.conf", entry)):
            with open(os.path.join(ALSA_RUN, name), "w") as f:
                f.write(text)
            os.chmod(os.path.join(ALSA_RUN, name), 0o644)
        if platform() == "jetson":
            if next((d for d in devices() if d["id"] == pcm), {}).get("kind") == "i2s":      # route stream 1 to the header's I2S2 (unverified on hardware)
                run("amixer", "-q", "-c", "APE", "cset", "name=I2S2 Mux", "ADMAIF1")
        return {"ALSA_CONFIG_PATH": path}
    except (OSError, ValueError) as e:
        print(f"audio: {e}", file=sys.stderr)
        return {}


def test_tone(device=None, seconds=1.5):
    """Play a tone on the chosen output (or `device`) so the operator hears where it comes out. Raises ValueError with aplay's message."""
    dev = device or effective() or "default"
    if dev != "default" and dev not in {d["id"] for d in devices()}:
        raise ValueError("that output is not present")
    rate = 48000
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        with wave.open(tmp, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(rate)
            n = int(rate * seconds)
            w.writeframes(b"".join(struct.pack("<hh", s, s) for s in (
                int(9000 * math.sin(2 * math.pi * 440 * i / rate) * min(1, i / 2400, (n - i) / 2400)) for i in range(n))))
        r = run("aplay", "-q", "-D", ("plug:" + dev) if dev != "default" else dev, tmp, timeout=15)
    finally:
        os.unlink(tmp)
    if r.returncode:
        busy = "busy" in (r.stderr or "").lower()
        raise ValueError("The output is in use (stop the game for the test)." if busy else (r.stderr or "aplay failed").strip()[-200:])
    return "Tone played."
