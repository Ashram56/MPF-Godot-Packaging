"""The cabinet preview: settings, capture commands, the sound copy in the ALSA configuration."""
import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common", "netconfig"))


def load(tmp, monkeypatch):
    monkeypatch.setenv("MPF_STATE_DIR", str(tmp))
    import mpf_common
    importlib.reload(mpf_common)
    import mpf_preview
    return importlib.reload(mpf_preview)


def test_settings_default_off_and_roundtrip(tmp_path, monkeypatch):
    pv = load(tmp_path, monkeypatch)
    assert pv.load() == {"enabled": False, "sound": False}
    pv.save(True, False)
    assert pv.load() == {"enabled": True, "sound": False}
    (tmp_path / "preview.json").write_text("[1]")
    assert pv.load()["enabled"] is False


def test_grab_geometry(tmp_path, monkeypatch):
    pv = load(tmp_path, monkeypatch)
    scr = [{"index": 0, "width": 1920, "height": 1080, "x": 0, "y": 0}, {"index": 1, "width": 1280, "height": 320, "x": 1920, "y": 0},
           {"index": 2, "width": 800, "height": 480, "x": 0, "y": 0}]
    assert pv.grab_geometry(scr, 0) == (1920, 1080, 0, 0)
    assert pv.grab_geometry(scr, 1) == (1280, 320, 1920, 0)
    assert pv.grab_geometry(scr, 2) is None      # a connector without a position
    assert pv.grab_geometry(scr, 5) is None


def test_commands(tmp_path, monkeypatch):
    pv = load(tmp_path, monkeypatch)
    c = pv.ffmpeg_cmd((1280, 320, 1920, 0), ":0")
    assert "x11grab" in c and ":0+1920,0" in c and "1280x320" in c and c[-1] == "-"
    assert "Loopback,1,0" in " ".join(pv.arecord_cmd())


def test_tee_conf_copies_to_loopback(tmp_path, monkeypatch):
    pv = load(tmp_path, monkeypatch)
    t = pv.tee_conf("hw:CARD=PCH,DEV=0")
    assert 'slaves.a.pcm "hw:CARD=PCH,DEV=0"' in t and "Loopback,0,0" in t and "pcm.!default" in t


def test_audio_prepare_uses_tee(tmp_path, monkeypatch):
    pv = load(tmp_path, monkeypatch)
    import mpf_audio as AU
    pv.save(True, True)
    monkeypatch.setattr(pv, "loopback_present", lambda *a: True)
    monkeypatch.setattr(AU, "effective", lambda: "hw:CARD=PCH,DEV=0")
    monkeypatch.setattr(AU, "ALSA_RUN", str(tmp_path / "run"))
    monkeypatch.setattr(AU, "ALSA_MAIN", (__file__,))
    assert AU.prepare()["ALSA_CONFIG_PATH"]
    over = (tmp_path / "run" / "override.conf").read_text()
    assert "mpf_multi" in over and "ctl.!default" in over
    pv.save(True, False)
    AU.prepare()
    assert "mpf_multi" not in (tmp_path / "run" / "override.conf").read_text()


def test_preview_windows_skip_disabled_and_merge_same_monitor(tmp_path, monkeypatch):
    load(tmp_path, monkeypatch)
    import mpf_web
    wins = [{"id": "backglass", "label": "Backglass", "index": 0, "enabled": True},
            {"id": "dmd", "label": "DMD", "index": 0, "enabled": True},
            {"id": "topper", "label": "Topper", "index": 0, "enabled": False},
            {"id": "extra", "label": "Extra", "index": 0, "enabled": True},
            {"id": "side", "label": "Side", "index": 1, "enabled": True}]
    monkeypatch.setattr(mpf_web.G, "screens_state", lambda path: wins)
    assert mpf_web.preview_windows({"path": "x"}) == [("backglass", "Backglass + Extra", 0, ""), ("side", "Side", 1, "")]


def test_titled_windows_are_not_merged_even_on_one_monitor(tmp_path, monkeypatch):
    """Backglass and topper on the same monitor (a single screen, or a monitor index beyond the connected ones) are two pictures."""
    load(tmp_path, monkeypatch)
    import mpf_web
    wins = [{"id": "backglass", "label": "Backglass", "index": 1, "enabled": True, "title": "Game - backglass"},
            {"id": "dmd", "label": "DMD", "index": 2, "enabled": True, "title": "Game - dmd"},
            {"id": "topper", "label": "Topper", "index": 0, "enabled": True, "title": "Game - topper"}]
    monkeypatch.setattr(mpf_web.G, "screens_state", lambda path: wins)
    assert mpf_web.preview_windows({"path": "x"}) == [("backglass", "Backglass", 1, "Game - backglass"), ("topper", "Topper", 0, "Game - topper")]
    wins[2]["enabled"] = False                       # a topper turned off is not shown
    assert [w[0] for w in mpf_web.preview_windows({"path": "x"})] == ["backglass"]


XWININFO = """xwininfo: Window id: 0x50d (the root window) (has no name)

  Root window id: 0x50d (the root window) (has no name)
  Parent window id: 0x0 (none)
     4 children:
     0x1600008 "Game - topper": ("ffplay" "ffplay")  640x160+640+200  +640+200
     0x1200008 "Game - backglass": ("ffplay" "ffplay")  640x360+0+0  +0+0
     0xc00002 "Game (DEBUG)": ("Godot_Engine" "Game")  1024x256+128+232  +128+232
        1 child:
        0xc00003 (has no name): ()  1x1+0+0  +128+232
     0xe00008 "Game - wide": ("x" "x")  2000x400-100+500  +-100+500
"""


def test_window_geometry_from_xwininfo(tmp_path, monkeypatch):
    pv = load(tmp_path, monkeypatch)
    wins = pv.parse_windows(XWININFO)
    assert ("Game - topper", 640, 160, 640, 200) in wins and len(wins) == 4
    assert pv.window_geometry(wins, "- backglass", (1280, 720)) == (640, 360, 0, 0)
    assert pv.window_geometry(wins, "- topper", (1280, 720)) == (640, 160, 640, 200)
    assert pv.window_geometry(wins, "- nothing") is None and pv.window_geometry(wins, "") is None
    assert pv.window_geometry(wins, "- wide", (1280, 720)) == (1280, 220, 0, 500)      # clipped to the screen


def test_a_monitor_beyond_the_connected_ones_is_the_last_one(tmp_path, monkeypatch):
    pv = load(tmp_path, monkeypatch)
    scr = [{"index": 0, "width": 1920, "height": 1080, "x": 0, "y": 0}, {"index": 1, "width": 1280, "height": 320, "x": 1920, "y": 0}]
    assert pv.monitor_geometry(scr, 1) == (1280, 320, 1920, 0)
    assert pv.monitor_geometry(scr, 4) == (1280, 320, 1920, 0)       # Godot: clampi(screen, 0, screen_count - 1)
    assert pv.monitor_geometry([scr[0]], 2) == (1920, 1080, 0, 0)
    assert pv.monitor_geometry([], 1) is None


def test_capture_geometry_prefers_the_window(tmp_path, monkeypatch):
    pv = load(tmp_path, monkeypatch)
    scr = [{"index": 0, "width": 1280, "height": 720, "x": 0, "y": 0}]
    monkeypatch.setattr(pv.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(pv, "find_window", lambda title, env=None: (640, 360, 0, 0) if title == "T" else None)
    assert pv.capture_geometry(3, "T", scr) == (640, 360, 0, 0)
    assert pv.capture_geometry(3, "closed", scr) is None             # the window is not open: no picture, not the monitor's
    assert pv.capture_geometry(3, "", scr) == (1280, 720, 0, 0)      # no title: the monitor, clamped
    monkeypatch.setattr(pv.shutil, "which", lambda n: None)
    assert pv.capture_geometry(3, "T", scr) == (1280, 720, 0, 0)     # no xwininfo: the monitor


def test_pulse_sound_in_a_container(tmp_path, monkeypatch):
    """The Docker image has no sound card: the sound is the null sink's monitor (ffmpeg), and no loopback copy is wanted."""
    pv = load(tmp_path, monkeypatch)
    monkeypatch.setattr(pv.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.delenv("MPF_PULSE_SINK", raising=False)
    assert not pv.pulse() and pv.sound_cmd()[0] == "arecord"
    monkeypatch.setenv("MPF_PULSE_SINK", "mpf")
    pv.save(True, True)
    assert pv.pulse() and pv.sound_cmd()[0] == "ffmpeg" and "mpf.monitor" in pv.sound_cmd() and pv.sound_cmd()[-3:] == ["-f", "wav", "-"]
    assert pv.want_tee() is False
