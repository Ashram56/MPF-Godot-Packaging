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
    assert mpf_web.preview_windows({"path": "x"}) == [("backglass", "Backglass + Extra", 0), ("side", "Side", 1)]
