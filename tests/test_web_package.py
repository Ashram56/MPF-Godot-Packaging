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
