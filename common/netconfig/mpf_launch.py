#!/usr/bin/env python3
"""Starts the setup page from the newest web package on the data partition, else from the copy in the image (/usr/local/bin).

The page (mpf_web, mpf_monitor, mpf_ota ...) can be updated without touching the read-only system: a "web package" is a folder
`<MPF_WEB_DIR>/<id>/` (default /data/platform) holding the mpf_*.py files and `manifest.json`; the link `<MPF_WEB_DIR>/current` names
the one in use. This launcher is what mpf-netconfig-web.service runs. It uses the package only if all of these hold, and otherwise
runs the image's own copy, so a bad package never leaves the machine without its page:
  - `manifest.json` has `"api"` equal to API below (the contract between the image and the page: bump it when the page needs
    something the image does not have: a new unit, a new path, a new tool);
  - `mpf_netconfig.py` is there and every mpf_*.py of it compiles;
  - there is no `.bad` file in the folder (written by whoever finds the package failing: the page's health check).
  mpf_launch.py [args]   default args: web
"""
import json
import os
import sys

API = 1
HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.environ.get("MPF_WEB_DIR", "/data/platform")


def usable(folder):
    """The package in `folder` if it can run here, else None."""
    try:
        if os.path.exists(os.path.join(folder, ".bad")):
            return None
        man = json.load(open(os.path.join(folder, "manifest.json"), encoding="utf-8"))
        if man.get("api") != API:
            return None
        files = [f for f in os.listdir(folder) if f.startswith("mpf_") and f.endswith(".py")]
        if "mpf_netconfig.py" not in files:
            return None
        for f in files:
            compile(open(os.path.join(folder, f), encoding="utf-8").read(), f, "exec")
        return man
    except (OSError, ValueError, SyntaxError):
        return None


def guard():
    """Count the starts of a package that the page has not confirmed (pending.json, removed by mpf_webupdate.confirm 10 s after the page
    listens). After 3 starts without a confirm the package is marked `.bad` and `current` goes back to the previous one (or is removed:
    the image's copy)."""
    pf = os.path.join(WEB_DIR, "pending.json")
    try:
        pend = json.load(open(pf))
        pend["starts"] = int(pend.get("starts", 0)) + 1
        if pend["starts"] <= 3:
            json.dump(pend, open(pf, "w"))
            return
        cur = os.path.join(WEB_DIR, "current")
        open(os.path.join(os.path.realpath(cur), ".bad"), "w").write("did not start 3 times\n")
        prev = pend.get("previous") or ""
        if os.path.lexists(cur):
            os.remove(cur)
        if prev and os.path.isdir(prev):
            os.symlink(prev, cur)
        for f in ("pending.json", "previous.json"):
            try:
                os.remove(os.path.join(WEB_DIR, f))
            except OSError:
                pass
        print("mpf_launch: package failed 3 starts, rolled back", flush=True)
    except (OSError, ValueError):
        pass


def choose():
    """(folder, manifest or None): the package in use, or the image's copy."""
    cur = os.path.join(WEB_DIR, "current")
    man = usable(cur) if os.path.isdir(cur) else None
    return (os.path.realpath(cur), man) if man else (HERE, None)


def main(argv):
    guard()
    folder, man = choose()
    os.environ["MPF_WEB_PACKAGE"] = (man or {}).get("id", "image")
    print(f"mpf_launch: {'package ' + man['id'] if man else 'image copy'} ({folder})", flush=True)
    script = os.path.join(folder, "mpf_netconfig.py")
    os.execv(sys.executable, [sys.executable, script] + (argv or ["web"]))


if __name__ == "__main__":
    main(sys.argv[1:])
