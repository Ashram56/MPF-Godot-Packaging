"""Web package: the launcher uses a package only when it is compatible, intact and not marked bad."""
import json
import os
import sys
import tarfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common", "netconfig"))
import make_web_package as W  # noqa: E402
import mpf_launch as L  # noqa: E402


def test_package_roundtrip(tmp_path, monkeypatch):
    path, man = W.build(str(tmp_path))
    with tarfile.open(path) as t:
        t.extractall(tmp_path / "pl")
    pkg = tmp_path / "pl" / man["id"]
    (tmp_path / "pl" / "current").symlink_to(pkg)
    monkeypatch.setattr(L, "WEB_DIR", str(tmp_path / "pl"))
    assert L.choose()[1]["id"] == man["id"]
    (pkg / ".bad").write_text("")
    assert L.choose()[1] is None
    (pkg / ".bad").unlink()
    m = json.load(open(pkg / "manifest.json"))
    m["api"] = L.API + 1
    json.dump(m, open(pkg / "manifest.json", "w"))
    assert L.choose()[1] is None
    m["api"] = L.API
    json.dump(m, open(pkg / "manifest.json", "w"))
    (pkg / "mpf_web.py").write_text("def (:")
    assert L.choose()[1] is None


def test_switch_rollback_and_guard(tmp_path, monkeypatch):
    """A new package is armed with a start counter; 3 starts without confirm roll it back; rollback() restores the previous one."""
    import mpf_common as C
    import mpf_games as G
    import mpf_webupdate as WU
    monkeypatch.setattr(L, "WEB_DIR", str(tmp_path))
    monkeypatch.setattr(C, "STATE_DIR", str(tmp_path / "st"))
    monkeypatch.setattr(WU, "_restart", lambda: None)
    monkeypatch.setattr(G, "job_set", lambda **k: None)
    src = os.path.join(os.path.dirname(__file__), "..", "common", "netconfig")
    files = {n: open(os.path.join(src, n), "rb").read() for n in os.listdir(src) if n.startswith("mpf_") and n.endswith(".py")}
    a = WU._stage(files, {"id": "a-1"})
    WU.switch(a)
    assert L.choose()[1]["id"] == "a-1"
    b = WU._stage(files, {"id": "b-2"})
    WU.switch(b)
    assert WU.status()["current"]["id"] == "b-2" and WU.status()["pending"]
    for _ in range(3):
        L.guard()
    assert L.choose()[1]["id"] == "b-2"             # 3 starts allowed
    L.guard()                                       # the 4th start finds it unconfirmed: back to a-1
    assert L.choose()[1]["id"] == "a-1" and os.path.exists(os.path.join(b, ".bad"))
    WU.switch(b)                                    # .bad packages are refused by the launcher
    assert L.choose()[1] is None
    WU.rollback()
    assert L.choose()[1]["id"] == "a-1"
    WU.confirm()
    assert not WU.status()["pending"]


def test_stage_refuses_other_api(tmp_path, monkeypatch):
    import mpf_games as G
    import mpf_webupdate as WU
    monkeypatch.setattr(L, "WEB_DIR", str(tmp_path))
    src = os.path.join(os.path.dirname(__file__), "..", "common", "netconfig")
    files = {n: open(os.path.join(src, n), "rb").read() for n in os.listdir(src) if n.startswith("mpf_") and n.endswith(".py")}
    files["mpf_launch.py"] = files["mpf_launch.py"].replace(b"API = 1", b"API = 9")
    try:
        WU._stage(files, {"id": "x"})
        assert False
    except G.JobError as e:
        assert "new image" in str(e)


def test_config_never_keeps_a_package_name_as_branch(tmp_path, monkeypatch):
    import mpf_common as C
    import mpf_webupdate as WU
    monkeypatch.setattr(C, "STATE_DIR", str(tmp_path))
    WU.save("webdav", "", "mpf-web-x-1.tar.xz")
    assert WU.load()["branch"] == "main"
    json.dump({"source": "webdav", "repo": "a/b", "branch": "mpf-web-y.tar.xz"}, open(WU.conf_path(), "w"))
    assert WU.load()["branch"] == "main"
    WU.save("github", "", "claude/x")
    assert WU.load()["branch"] == "claude/x"
