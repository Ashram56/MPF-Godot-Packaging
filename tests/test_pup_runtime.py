"""The PuP runtime's trigger engine (tools/pup/runtime/game/pup_runtime), without MPF."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "pup", "runtime", "game"))

from pup_runtime import engine, pupfiles, settings  # noqa: E402


def row(id_, trigger, screen=2, playlist="P", file="", rest="", loop=""):
    return pupfiles.Trigger({"ID": str(id_), "Active": "1", "Trigger": trigger, "ScreenNum": str(screen),
                             "PlayList": playlist, "PlayFile": file, "RestSeconds": rest, "Loop": loop})


def make(rows, **mapping):
    sent, clock = [], [0.0]
    full = {"dmd": {}, "switches": {}, "override": {}, "counters": {}}
    full.update(mapping)
    eng = engine.Engine(rows, full, sent.append, lambda: clock[0])
    return eng, sent, clock


def test_parse_event_conditions():
    assert engine.parse_event("g_deff_5") == ("g_deff_5", ())
    assert engine.parse_event("g_deff_5{award==1}") == ("g_deff_5", (("award", "1"),))
    assert engine.parse_event("g_deff_5{count==3, completed==0}") == ("g_deff_5", (("count", "3"), ("completed", "0")))
    assert engine.parse_event("g_deff_5{values.1==4}") == ("g_deff_5", (("values.1", "4"),))


def test_conditions_on_arguments_and_list_items():
    eng, sent, _ = make([row(1, "D1", file="a"), row(2, "D2", file="b")],
                        dmd={1: ["e{values.1==4}"], 2: ["e{values.0==10, x==1}"]})
    eng.on_event("e", values=[10, 4])
    assert [c["file"] for c in sent] == ["a"]
    eng.on_event("e", values=[10, 3], x=1)
    assert [c["file"] for c in sent] == ["a", "b"]


def test_counters_number_events_since_a_reset():
    rows = [row(i, "D{}".format(i), file="hit{}".format(i)) for i in (1, 2, 3)]
    eng, sent, _ = make(rows, dmd={1: ["hit{count==1}"], 2: ["hit{count==2}"], 3: ["hit{count==3}"]},
                        counters={"hit": ["intro"]})
    assert "intro" in eng.event_names and "hit" in eng.event_names
    eng.on_event("intro")
    eng.on_event("hit")
    eng.on_event("hit")
    eng.on_event("intro")
    eng.on_event("hit")
    assert [c["file"] for c in sent] == ["hit1", "hit2", "hit1"]


def test_rest_seconds_and_duplicate_commands():
    eng, sent, clock = make([row(1, "D1", file="a", rest="10"), row(2, "D2", file="a", rest="10")],
                            dmd={1: ["e"], 2: ["e"]})
    eng.on_event("e")
    assert len(sent) == 1                       # two captures of one effect send one command
    clock[0] = 5.0
    eng.on_event("e")
    assert len(sent) == 1                       # resting
    clock[0] = 11.0
    eng.on_event("e")
    assert len(sent) == 2


def test_unmapped_rows_and_switches():
    eng, sent, _ = make([row(1, "D9"), row(2, "W11", file="sw")], switches={11: "s_left_ramp"})
    assert [r.id for r in eng.unmapped] == [1]
    eng.on_switch("s_left_ramp")
    assert sent[0]["file"] == "sw"


def test_settings_env_prefix(tmp_path, monkeypatch):
    (tmp_path / "pup.cfg").write_text('[pup]\nenabled=true\nenv="TF"\npack_dir="pup_pack/tf_180"\n', encoding="utf-8")
    monkeypatch.delenv("TF_PUP", raising=False)
    monkeypatch.delenv("PUP", raising=False)
    cfg = settings.load(str(tmp_path))
    assert cfg["pup"]["enabled"] is True and settings.env_name(cfg, "PUP_ZIP") == "TF_PUP_ZIP"
    assert settings.pack_dir(cfg, "/r").replace("\\", "/") == "/r/pup_pack/tf_180"
    monkeypatch.setenv("TF_PUP", "0")
    assert settings.load(str(tmp_path))["pup"]["enabled"] is False


def test_conditions_on_state_attributes_and_dicts():
    class State(dict):
        side = 2
    eng, sent, _ = make([row(1, "D1", file="auto"), row(2, "D2", file="dec")],
                        dmd={1: ["e{state.side==1}"], 2: ["e{state.side==2}"]})
    eng.on_event("e", state=State())
    eng.on_event("e", state={"side": 1})
    eng.on_event("e")
    assert [c["file"] for c in sent] == ["dec", "auto"]
