"""Can this bundle start? The checks that catch a bundle with a file missing before it is installed (standard library only).

A bundle that lacks a Python file its start script imports used to be found only when the machine ran it (`ModuleNotFoundError`, the
service restarting every ten seconds). `problems(folder, python)` looks for that without running the game: it follows the imports at the
top level of the start script (and of every script that names, e.g. `run.py` launched by `start.py`) through the files of the bundle and
reports each module that is neither in the bundle nor importable by the game's Python. The builder (common/games/build_game_package.py)
runs it on the extracted archive and the page's installer runs it on the unpacked bundle, so a bad archive is refused and the game
that was running stays the active one.

A game can add its own test: `run.check` in bundle.json, a command run in the bundle folder that exits 0 when the game can start
(a few seconds, no display, nothing left running). `check_command(b)` returns it; the caller runs it the way it runs the game.

What this does not see: an import inside a function or a `try`, a file read at run time (media, tables), a bad value in a config.
Those need `run.check`, and the known failures in platforms/game-bundles.md.
"""
import ast
import json
import os
import re
import subprocess
import sys

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".godot", "node_modules"}
PROVIDED = {"mpf_godot"}            # the platform's own package: not in a game's bundle, found by the loader
DEFAULT_TIMEOUT = 90


def start_script(b):
    """The Python file the bundle's `run.start` runs, as a path relative to the bundle (None when it is not a Python script)."""
    run = b.get("run") or {}
    cmd = str(run.get("start", "")).split()
    for word in cmd[1:] if cmd and re.match(r"^python[0-9.]*$", os.path.basename(cmd[0])) else ():
        if word.endswith(".py"):
            return os.path.normpath(os.path.join(str(run.get("cwd") or "."), word))     # relative to the folder it runs in
    return None


def check_command(b):
    """`run.check` of bundle.json as an argument list, or None."""
    import shlex
    c = (b.get("run") or {}).get("check")
    return shlex.split(c) if c else None


def check_timeout(b):
    try:
        return int((b.get("run") or {}).get("check_timeout", DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT


def index(root):
    """{module name: path} of the Python modules of the bundle (a file `x.py` or a package `x/`), any depth, tools and caches left out."""
    found = {}
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            if n.endswith(".py"):
                found.setdefault(n[:-3], os.path.join(dirpath, n))
        if "__init__.py" in names:
            found.setdefault(os.path.basename(dirpath), os.path.join(dirpath, "__init__.py"))
    return found


def top_level_imports(path):
    """[(module, level)] imported by the statements that run when the file is imported: not in a function, a `try` or an `if`
    (those are optional or platform dependent) but in a class body, a `with`, a `for` or a `while`."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            tree = ast.parse(f.read(), path)
    except (SyntaxError, ValueError) as e:
        return [], f"{os.path.basename(path)} does not parse: {e}"
    out = []

    def walk(body):
        for node in body:
            if isinstance(node, ast.Import):
                out.extend((a.name, 0) for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    out.append((node.module, node.level))
                else:
                    out.extend((a.name, node.level) for a in node.names)
            elif isinstance(node, (ast.With, ast.For, ast.While, ast.ClassDef)):
                walk(node.body)
    walk(tree.body)
    return out, None


def string_scripts(path, mods):
    """Python files the script names in a string (`start.py` launching `run.py`): their module names, when the bundle has them."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    return [m for m in re.findall(r"""["']([A-Za-z0-9_./-]+)\.py["']""", text) if os.path.basename(m) in mods]


def importable(python, names):
    """The names `python` cannot import (no module of that name anywhere on its path)."""
    if not names:
        return set()
    code = ("import importlib.util, json, sys\nmiss = []\nfor n in json.loads(sys.argv[1]):\n"
            "    try:\n        ok = importlib.util.find_spec(n) is not None\n    except Exception:\n        ok = False\n"
            "    if not ok:\n        miss.append(n)\nprint(json.dumps(miss))")
    r = subprocess.run([python, "-I", "-c", code, json.dumps(sorted(names))], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None
    try:
        return set(json.loads(r.stdout.strip().splitlines()[-1]))
    except (ValueError, IndexError):
        return None


def python_files(folder):
    """Every Python file under `folder` (a format 2 bundle has no start script: MPF imports the game's code, so all of it is checked)."""
    out = []
    for dirpath, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        out += [os.path.join(dirpath, n) for n in sorted(names) if n.endswith(".py")]
    return out


def problems(root, python=None, b=None, source=None, starts=None):
    """[str] of what keeps the bundle in `root` from starting; [] when nothing was found. `python` is the game's Python (its venv's; None
    when there is none: third-party names are then not judged). `source` is the folder the bundle was built from, when the caller has
    it: a module that is in the source but not in the bundle is an omission whatever the Python says. `starts` (absolute paths) replaces
    the start script of `run.start` as the files the walk begins with (format 2)."""
    if starts is not None:
        return walk(root, list(starts), python, source)
    if b is None:
        try:
            with open(os.path.join(root, "bundle.json"), encoding="utf-8") as f:
                b = json.load(f)
        except (OSError, ValueError):
            return ["bundle.json cannot be read"]
    start = start_script(b)
    if not start:
        return []
    first = os.path.join(root, start)
    if not os.path.isfile(first):
        return [f"run.start runs {start}, which is not in the bundle"]
    return walk(root, [first], python, source)


def walk(root, firsts, python=None, source=None):
    """Follow the top-level imports of `firsts` through the bundle; [str] of what cannot be found."""
    mods = index(root)
    src_mods = index(source) if source else {}
    seen, queue, bad, unknown = set(), list(firsts), [], {}
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        rel = os.path.relpath(path, root)
        imports, err = top_level_imports(path)
        if err:
            bad.append(err)
            continue
        for name, level in imports:
            top = name.split(".")[0]
            if level:                                    # from . import x: next to the file
                cand = os.path.join(os.path.dirname(path), top + ".py")
                pkg = os.path.join(os.path.dirname(path), top, "__init__.py")
                hit = cand if os.path.isfile(cand) else pkg if os.path.isfile(pkg) else None
                if hit:
                    queue.append(hit)
                else:
                    bad.append(f"{rel}: the relative import '{name}' has no file in the bundle")
            elif top in mods:
                queue.append(mods[top])
            elif top in src_mods:
                bad.append(f"{rel}: imports '{top}', which is in the source ({os.path.relpath(src_mods[top], source)}) but was left out of the bundle")
            elif top not in PROVIDED:
                unknown.setdefault(top, rel)
        queue.extend(mods[m] for m in string_scripts(path, mods) if mods[m] not in seen)
    if unknown:
        known = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()
        todo = {n for n in unknown if n not in known}
        miss = importable(python, todo) if python and os.path.exists(python) else None
        if miss:
            bad += [f"{unknown[n]}: imports '{n}', which is neither in the bundle nor installed for the game's Python" for n in sorted(miss)]
    return bad
