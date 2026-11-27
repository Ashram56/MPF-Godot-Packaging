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


def test_branches_main_first_then_newest_open_first(monkeypatch):
    import io
    import mpf_webupdate as WU

    def br(n):
        return {"name": n, "commit": {"sha": n.ljust(40, "0")}}
    pulls = [{"number": 5, "title": "old merged", "state": "closed", "merged_at": "x", "updated_at": "2026-11-01T00:00:00Z", "head": {"ref": "a", "repo": {"full_name": "o/r"}}},
             {"number": 9, "title": "new open", "state": "open", "updated_at": "2026-11-03T00:00:00Z", "head": {"ref": "c", "repo": {"full_name": "o/r"}}},
             {"number": 7, "title": "older open", "state": "open", "updated_at": "2026-11-02T00:00:00Z", "head": {"ref": "b", "repo": {"full_name": "o/r"}}}]

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def fake(url, headers=None, limit=None):
        return R(json.dumps([br(n) for n in ("a", "z-nopr", "b", "main", "c")] if "/branches" in url else pulls).encode())
    monkeypatch.setattr(WU, "_get", fake)
    assert [b["name"] for b in WU.branches("o/r")] == ["main", "c", "b", "a", "z-nopr"]


def test_game_start_uses_the_package_and_does_not_count_as_a_page_start(tmp_path, monkeypatch):
    """mpf-game.service runs `mpf_launch.py game`: the package's script runs, and the game's restarts never arm the page's rollback counter."""
    pkg = tmp_path / "p-1"
    pkg.mkdir()
    (pkg / "mpf_netconfig.py").write_text("")
    json.dump({"id": "p-1", "api": L.API}, open(pkg / "manifest.json", "w"))
    (tmp_path / "current").symlink_to(pkg)
    (tmp_path / "pending.json").write_text(json.dumps({"starts": 0}))
    monkeypatch.setattr(L, "WEB_DIR", str(tmp_path))
    ran = []
    monkeypatch.setattr(os, "execv", lambda exe, args: ran.append(args))
    for _ in range(5):
        L.main(["game"])
    assert [a[1:] for a in ran] == [[os.path.join(os.path.realpath(pkg), "mpf_netconfig.py"), "game"]] * 5
    assert json.load(open(tmp_path / "pending.json"))["starts"] == 0
    L.main(["web"])
    assert json.load(open(tmp_path / "pending.json"))["starts"] == 1
    svc = open(os.path.join(os.path.dirname(__file__), "..", "common", "netconfig", "mpf-game.service")).read()
    assert "ExecStart=/usr/local/bin/mpf_launch.py game" in svc
