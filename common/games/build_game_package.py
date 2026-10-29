#!/usr/bin/env python3
"""Build the installable package (bundle) of a game from its repository, and check it the way the page does.

    build_game_package.py RECIPE [--repo PATH_OR_URL] [--ref BRANCH] [--workdir DIR] [--version V] [--target all|arm64|x86_64]
                                 [--out DIR] [--skip-setup] [--publish WEBDAV_URL] [--dry-run]

RECIPE is a name in common/games/recipes/ (`tron-legacy-mpf`) or the path of a recipe file. A recipe says where the game's repository
is, how to prepare its workspace and how to build; see common/games/README.md ("Building the package of a game"). Without a recipe
command the game's `bundle_spec.json` is built with `python -m mpf_godot bundle` (platforms/game-bundles.md).

What it does: 1. get the repository (clone it, or use the folder given by --repo: a clone you already made is used as it is);
2. run the recipe's `setup` commands there (skipped with --skip-setup: the workspace is ready); 3. run the `build` command;
4. **check the archive**: the sha256 file, `bundle.json` (format, id, version, target), the platform add-ons it asks for exist in this
repository, no cabinet data (`game/data`, `*.local.cfg`, `logs`) and, in a universal archive, no GoZen binary; 5. print the file,
its size and hash and the three ways to put it on a machine. `--publish URL` also uploads it, with its `.sha256`, to a WebDAV folder
(user and password from the environment, WEBDAV_USER and WEBDAV_PASS) laid out the way the setup page's *Updates* card reads it.
Linux (or WSL) with git and python3; standard library only.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM = os.path.dirname(os.path.dirname(HERE))
RECIPES = os.path.join(HERE, "recipes")
TARGET_ARCH = {"arm64": "arm64", "x86_64": "x86_64", "all": "arm64+x86_64"}
CABINET = re.compile(r"(^|/)(game/(data|audits|logs)(/|$)|[^/]*\.local\.cfg$|machine_vars\.yaml$|scorbit_device_key\.txt$)")


def die(msg):
    sys.exit(f"build_game_package: {msg}")


def say(msg):
    print(msg, flush=True)


def load_recipe(name):
    path = name if os.path.isfile(name) else os.path.join(RECIPES, name + ".json")
    if not os.path.isfile(path):
        die(f"no recipe {name!r}: give the name of a file in {RECIPES} or the path of a recipe file")
    with open(path, encoding="utf-8") as f:
        r = json.load(f)
    if not r.get("id"):
        die(f"{path}: the recipe has no id")
    return r


def fill(items, values):
    return [str(x).format(**values) for x in items]


def run(cmd, cwd, env=None, dry=False):
    say("   $ " + " ".join(cmd) + f"   (in {cwd})")
    if dry:
        return
    r = subprocess.run(cmd, cwd=cwd, env=env)
    if r.returncode:
        die(f"failed (exit {r.returncode}): {' '.join(cmd)}")


def get_repo(recipe, repo, ref, workdir, dry):
    repo = repo or recipe.get("repo")
    if not repo:
        die("no repository: give --repo or set `repo` in the recipe")
    if os.path.isdir(repo):
        say(f"using the repository in {repo} as it is (no clone, no checkout)")
        return os.path.abspath(repo)
    dest = os.path.join(workdir, recipe["id"])
    ref = ref or recipe.get("ref") or "main"
    if os.path.isdir(os.path.join(dest, ".git")):
        say(f"updating {dest} to {ref}")
        run(["git", "fetch", "--tags", "origin", ref], dest, dry=dry)
        run(["git", "checkout", "-q", "FETCH_HEAD"], dest, dry=dry)
    else:
        say(f"cloning {repo} ({ref}) into {dest}")
        os.makedirs(workdir, exist_ok=True)
        run(["git", "clone", "-q", "--branch", ref, repo, dest], workdir, dry=dry)
    if recipe.get("submodules"):
        run(["git", "submodule", "update", "--init", "--recursive"], dest, dry=dry)
    return dest


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(archive, recipe, target):
    """The checks of the setup page, made before the file leaves the build machine. Returns bundle.json; dies on a problem."""
    problems = []
    sumfile = archive + ".sha256"
    digest = sha256(archive)
    if os.path.isfile(sumfile):
        with open(sumfile) as f:
            want = (f.read().split() or [""])[0]
        if want != digest:
            problems.append(f"{os.path.basename(sumfile)} does not match the archive")
    else:
        with open(sumfile, "w") as f:
            f.write(f"{digest}  {os.path.basename(archive)}\n")
        say(f"wrote {os.path.basename(sumfile)}")
    meta, names = None, []
    try:
        with tarfile.open(archive, "r:xz") as t:
            for m in t:
                names.append(m.name)
                if meta is None and m.isfile() and m.name.count("/") == 1 and m.name.endswith("/bundle.json"):
                    meta = json.load(t.extractfile(m))
    except (tarfile.TarError, OSError, ValueError, EOFError) as e:
        die(f"{archive} is not a readable .tar.xz bundle: {e}")
    if meta is None:
        die(f"{archive}: no bundle.json at the top of the archive")
    if meta.get("format") != 1:
        problems.append(f"bundle.json format is {meta.get('format')!r}, the page reads 1")
    if meta.get("id") != recipe["id"]:
        problems.append(f"bundle.json id is {meta.get('id')!r}, the recipe says {recipe['id']!r}")
    if not meta.get("version"):
        problems.append("bundle.json has no version")
    arch = (meta.get("target") or {}).get("arch")
    if arch not in (TARGET_ARCH[target], "all"):
        problems.append(f"bundle.json target.arch is {arch!r}, the build asked for {TARGET_ARCH[target]!r}")
    for add in meta.get("platform_addons", []):
        if not any(os.path.isdir(os.path.join(PLATFORM, d, add)) for d in ("addons", "toolchain/addons")) and add != "mpf-gmc":
            problems.append(f"platform add-on {add!r} is not in this repository's addons/: the page could not install it")
    bad = [n for n in names if CABINET.search(n.split("/", 1)[-1])]
    if bad:
        problems.append("cabinet data in the archive: " + ", ".join(bad[:5]))
    if target == "all" and any("libgozen" in n for n in names):
        problems.append("a universal archive must not carry GoZen binaries (the platform brings its own)")
    if problems:
        die("the archive is not installable:\n  - " + "\n  - ".join(problems))
    say(f"checked: {meta['id']} {meta['version']}, target {arch}, {len(names)} files, platform add-ons {meta.get('platform_addons', [])}")
    return meta, digest


def publish(url, archive, folder):
    user, pw = os.environ.get("WEBDAV_USER", ""), os.environ.get("WEBDAV_PASS", "")
    if not user or not pw:
        die("--publish needs WEBDAV_USER and WEBDAV_PASS in the environment")
    auth = "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()
    base = url.rstrip("/") + "/" + (folder + "/" if folder else "")

    def req(method, target, data=None):
        r = urllib.request.Request(target, data=data, method=method, headers={"Authorization": auth})
        try:
            with urllib.request.urlopen(r, timeout=600) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            return e.code

    if folder:
        code = req("MKCOL", base)
        if code not in (200, 201, 301, 405):    # 405: the folder exists
            die(f"cannot create {base}: HTTP {code}")
    for path in (archive, archive + ".sha256"):
        name = urllib.parse.quote(os.path.basename(path))
        with open(path, "rb") as f:
            code = req("PUT", base + name, f.read())
        if code not in (200, 201, 204):
            die(f"upload of {name} failed: HTTP {code}")
        say(f"uploaded {base}{name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], epilog="See the top of this file for details.")
    ap.add_argument("recipe")
    ap.add_argument("--repo", help="the game's repository: a folder already cloned (used as it is) or a git URL")
    ap.add_argument("--ref", help="branch or tag to build (a cloned URL only)")
    ap.add_argument("--workdir", default=os.path.join(os.path.expanduser("~"), "mpf-game-builds"), help="where a URL is cloned")
    ap.add_argument("--version")
    ap.add_argument("--target", choices=sorted(TARGET_ARCH))
    ap.add_argument("--out", default="dist")
    ap.add_argument("--skip-setup", action="store_true")
    ap.add_argument("--publish", metavar="WEBDAV_URL")
    ap.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")
    a = ap.parse_args()

    recipe = load_recipe(a.recipe)
    target = a.target or recipe.get("target", "all")
    out = os.path.abspath(a.out)
    for need in ("git",) if not os.path.isdir(a.repo or "") else ():
        if not shutil.which(need):
            die(f"{need} is not installed")
    repo = get_repo(recipe, a.repo, a.ref, os.path.abspath(a.workdir), a.dry_run)
    version = a.version or ""
    values = {"python": sys.executable, "target": target, "version": version, "out": out, "platform": PLATFORM, "repo": repo}
    env = dict(os.environ, **dict(zip(recipe.get("env", {}), fill(recipe.get("env", {}).values(), values))))
    if not a.skip_setup:
        for cmd in recipe.get("setup", []):
            run(fill(cmd, values), repo, env, a.dry_run)
    os.makedirs(out, exist_ok=True)
    started = time.time()
    if recipe.get("build"):
        cmd = fill(recipe["build"], values)
        if not version:      # the game's builder chooses (date and commit)
            i = cmd.index("--version") if "--version" in cmd else -1
            if i >= 0:
                del cmd[i:i + 2]
    elif os.path.isfile(os.path.join(repo, "bundle_spec.json")):
        cmd = [sys.executable, "-m", "mpf_godot", "bundle", "bundle_spec.json", "--target", target, "--out", out] + (["--version", version] if version else [])
        env["PYTHONPATH"] = PLATFORM + os.pathsep + env.get("PYTHONPATH", "")
    else:
        die("the recipe has no `build` command and the repository has no bundle_spec.json "
            "(for your own MPF code without a build step: common/games/make_bundle.py)")
    run(cmd, repo, env, a.dry_run)
    if a.dry_run:
        say("dry run: nothing built")
        return
    new = sorted((p for p in os.listdir(out) if p.endswith(".tar.xz") and os.path.getmtime(os.path.join(out, p)) >= started - 1),
                 key=lambda p: os.path.getmtime(os.path.join(out, p)))
    if not new:
        die(f"the build produced no .tar.xz in {out}")
    archive = os.path.join(out, new[-1])
    meta, digest = verify(archive, recipe, target)
    say(f"\n{archive}\n  {os.path.getsize(archive) >> 20} MB, sha256 {digest}")
    if a.publish:
        publish(a.publish, archive, recipe.get("publish_folder", recipe["id"]))
    say(f"\nPut it on a machine (common/games/README.md):\n"
        f"  - the setup page, Install tab: drop {os.path.basename(archive)} (and its .sha256)\n"
        f"  - before flashing: python3 common/games/inject_image.py IMAGE --bundle {archive}\n"
        f"  - over the air: --publish a WebDAV folder, then the page's Updates card")


if __name__ == "__main__":
    main()
