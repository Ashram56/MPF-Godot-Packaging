"""The screens of the cabinet and which window of the game goes on which (the page's "Screens" card). Standard library only.

A bundle declares its windows in bundle.json: `"screens": [{"id": "backglass", "label": "Backglass", "setting": "pup.backglass.screen"}, ...]`;
`setting` is an integer option of its settings schema (the monitor index the game puts that window on, 0 = the main one). The page lists the
connected screens, the platform stores the index in the game's settings and the game places its windows as it always did: the platform
only chooses. These settings are hidden from the game's own settings form (the card is their place).

Screens are listed as the game's engine numbers them: left to right (then top to bottom) on X11.
"""
import os
import re
import subprocess

XRANDR_RE = re.compile(r"^(\S+) connected( primary)? (\d+)x(\d+)\+(-?\d+)\+(-?\d+)", re.M)


def parse_xrandr(text):
    """[{"name", "width", "height", "x", "y", "primary"}] of the connected outputs that show a picture, left to right then top to bottom."""
    out = [{"name": m[1], "primary": bool(m[2]), "width": int(m[3]), "height": int(m[4]), "x": int(m[5]), "y": int(m[6])}
           for m in XRANDR_RE.finditer(text or "")]
    return sorted(out, key=lambda s: (s["x"], s["y"]))


def parse_drm(root="/sys/class/drm"):
    """The connected connectors with their preferred mode (no X session to ask)."""
    out = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return out
    for n in names:
        try:
            if open(os.path.join(root, n, "status")).read().strip() != "connected":
                continue
            mode = open(os.path.join(root, n, "modes")).readline().strip()
        except OSError:
            continue
        m = re.fullmatch(r"(\d+)x(\d+).*", mode)
        out.append({"name": re.sub(r"^card\d+-", "", n), "primary": False, "width": int(m[1]) if m else 0, "height": int(m[2]) if m else 0,
                    "x": 0, "y": 0})
    return out


def detect(user_home=None):
    """The connected screens, the engine's order. xrandr on the game user's X session, else the kernel's list of connectors."""
    env = dict(os.environ, DISPLAY=os.environ.get("DISPLAY") or ":0")
    if user_home and os.path.exists(os.path.join(user_home, ".Xauthority")):
        env.setdefault("XAUTHORITY", os.path.join(user_home, ".Xauthority"))
    try:
        r = subprocess.run(["xrandr", "--query"], capture_output=True, text=True, timeout=5, env=env)
        found = parse_xrandr(r.stdout)
    except (OSError, subprocess.SubprocessError):
        found = []
    found = found or parse_drm()
    for i, s in enumerate(found):
        s["index"] = i
    return found


def windows(bundle):
    """[{"id", "label", "setting"}] the bundle declares."""
    return [w for w in ((bundle or {}).get("screens") or []) if isinstance(w, dict) and w.get("id") and w.get("setting")]


def settings(bundle):
    return {w["setting"] for w in windows(bundle)}
