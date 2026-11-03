#!/usr/bin/env python3
"""Builds the web package: the page's modules of this checkout as `mpf-web-<branch>-<sha>.tar.xz` + `.sha256`.

  python3 make_web_package.py [OUT_DIR]     (default: the current folder; run it from a git checkout)

The archive holds a folder `<id>/` with every mpf_*.py and `manifest.json` {format, id, api, branch, sha, built, files{name: sha256}}.
Install: unpack it under /data/platform and point /data/platform/current at it (mpf_launch.py does the rest); `install_web_package.sh`
does it by hand. `api` is mpf_launch.API.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mpf_launch  # noqa: E402


def git(*a):
    try:
        return subprocess.run(["git", "-C", HERE, *a], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def build(out_dir="."):
    sha = git("rev-parse", "--short=8", "HEAD") or "nogit"
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    pid = f"{re.sub(r'[^A-Za-z0-9._-]+', '_', branch)}-{sha}"
    names = sorted(f for f in os.listdir(HERE) if f.startswith("mpf_") and f.endswith(".py"))
    files = {n: hashlib.sha256(open(os.path.join(HERE, n), "rb").read()).hexdigest() for n in names}
    man = {"format": 1, "id": pid, "api": mpf_launch.API, "branch": branch, "sha": sha,
           "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": files}
    path = os.path.join(out_dir, f"mpf-web-{pid}.tar.xz")
    with tarfile.open(path, "w:xz") as t:
        for n in names:
            t.add(os.path.join(HERE, n), arcname=f"{pid}/{n}", filter=lambda i: (setattr(i, "mode", 0o755), i)[1])
        data = json.dumps(man, indent=1).encode()
        ti = tarfile.TarInfo(f"{pid}/manifest.json")
        ti.size, ti.mtime, ti.mode = len(data), int(time.time()), 0o644
        t.addfile(ti, io.BytesIO(data))
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    open(path + ".sha256", "w").write(f"{digest}  {os.path.basename(path)}\n")
    return path, man


if __name__ == "__main__":
    p, m = build(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(p, m["id"], f"api {m['api']}")
