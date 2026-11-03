"""The page's live preview of the cabinet: the backglass and the topper (a capture of the screen each window is on), the sound, and
the DMD (drawn by the page from mpf_dmd's pictures). Standard library only; ffmpeg and arecord do the capturing.

Settings: STATE_DIR/preview.json {"enabled": bool, "sound": bool}. Nothing runs while the option is off or no page is open: every capture
is a child process started by the request of a page and killed when that page closes the connection.

* Picture: `ffmpeg -f x11grab` of the screen a window of the game is on (screens come from mpf_screens, the window's index from the bundle's
  `screens`), scaled down, sent as multipart MJPEG (`<img src>` shows it).
* Sound: the game's ALSA output is duplicated to the `snd-aloop` loopback (`tee_conf()`, used by mpf_audio.prepare() when `sound` is on and a
  sound output is chosen on the page); the page plays `arecord` of the loopback's other side as a never ending WAV.
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpf_common as C  # noqa: E402

FPS = 5
WIDTH = 640
RATE = 44100
LOOP_PLAY = "hw:Loopback,0,0"         # the game's copy goes here...
LOOP_CAPTURE = "plughw:Loopback,1,0"  # ...and the page reads it here
BOUNDARY = "mpfframe"


def settings_file():
    return os.path.join(C.STATE_DIR, "preview.json")


def load():
    try:
        with open(settings_file()) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    return {"enabled": d.get("enabled") is True, "sound": d.get("sound") is True}


def save(enabled, sound):
    s = {"enabled": bool(enabled), "sound": bool(sound)}
    os.makedirs(C.STATE_DIR, exist_ok=True)
    with C.writable(C.STATE_DIR):
        tmp = settings_file() + ".tmp"
        with open(tmp, "w") as f:
            json.dump(s, f)
        os.replace(tmp, settings_file())
    return s


def loopback_present(proc="/proc/asound/cards"):
    try:
        with open(proc) as f:
            return "Loopback" in f.read()
    except OSError:
        return False


def pulse():
    """True where the game plays into a PulseAudio null sink (the Docker image: no sound card, no snd-aloop): MPF_PULSE_SINK names it."""
    return bool(os.environ.get("MPF_PULSE_SINK") and shutil.which("ffmpeg"))


def tools():
    return {"ffmpeg": bool(shutil.which("ffmpeg")), "arecord": bool(shutil.which("arecord")), "parec": bool(shutil.which("parec"))}


def grab_geometry(screens, index):
    """(width, height, x, y) of screen `index`, or None when it is unknown or has no position (the kernel's connector list has none)."""
    s = next((s for s in screens if s.get("index") == index), None)
    if not s or not s.get("width") or not s.get("height"):
        return None
    if index != 0 and not s.get("x") and not s.get("y"):
        return None
    return int(s["width"]), int(s["height"]), int(s.get("x") or 0), int(s.get("y") or 0)


def ffmpeg_cmd(geom, display=":0", fps=FPS, width=WIDTH):
    w, h, x, y = geom
    return ["ffmpeg", "-loglevel", "error", "-f", "x11grab", "-framerate", str(fps), "-video_size", f"{w}x{h}", "-i", f"{display}+{x},{y}",
            "-vf", f"scale={width}:-2", "-q:v", "7", "-f", "mpjpeg", "-boundary_tag", BOUNDARY, "-"]


def sound_cmd(rate=RATE):
    """The sound capture: the sink's monitor with ffmpeg in a container, the loopback's other side with arecord elsewhere."""
    if pulse():
        # ffmpeg, not parec: parec's wav writer needs a seekable file ("Failed to open audio file" on a pipe); ffmpeg streams a wav
        return ["ffmpeg", "-loglevel", "error", "-f", "pulse", "-i", os.environ["MPF_PULSE_SINK"] + ".monitor", "-ac", "2", "-ar", str(rate), "-f", "wav", "-"]
    return arecord_cmd(rate)


def arecord_cmd(rate=RATE):
    return ["arecord", "-q", "-D", LOOP_CAPTURE, "-f", "S16_LE", "-r", str(rate), "-c", "2", "-t", "wav"]


def tee_conf(pcm):
    """ALSA text for the default pcm: plays on `pcm` (a hw: name) and on the loopback (route: stereo to four channels, on a multi)."""
    return (f'pcm.mpf_multi {{\n    type multi\n    slaves.a.pcm "{pcm}"\n    slaves.a.channels 2\n'
            f'    slaves.b.pcm "{LOOP_PLAY}"\n    slaves.b.channels 2\n'
            "    bindings.0 { slave a channel 0 }\n    bindings.1 { slave a channel 1 }\n"
            "    bindings.2 { slave b channel 0 }\n    bindings.3 { slave b channel 1 }\n}\n"
            "pcm.mpf_tee {\n    type route\n    slave.pcm mpf_multi\n    slave.channels 4\n"
            "    ttable.0.0 1\n    ttable.1.1 1\n    ttable.0.2 1\n    ttable.1.3 1\n}\n"
            "pcm.!default {\n    type plug\n    slave.pcm mpf_tee\n}\n")


def want_tee():
    """True when the game's sound is to be copied to the loopback (option on, module loaded or loadable)."""
    s = load()
    if not (s["enabled"] and s["sound"]) or pulse():
        return False
    if not loopback_present():
        C.run("modprobe", "snd-aloop")
    return loopback_present()


def start(cmd, env=None):
    """The child process of one stream (stdout piped, stderr dropped)."""
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=dict(os.environ, **(env or {})))


def stream(proc, write, chunk=16384):
    """Copy the process's output to `write` until the client or the process ends; the process is always killed."""
    try:
        while True:
            data = proc.stdout.read1(chunk)
            if not data:
                break
            write(data)
    except (BrokenPipeError, ConnectionError, OSError):
        pass
    finally:
        proc.kill()
        proc.wait()
