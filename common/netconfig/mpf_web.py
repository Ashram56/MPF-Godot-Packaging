"""The setup page of the MPF images (port 8080): status, games, network, SSH, mode. Standard library only, no external file or font
(the page must work on the MPF-Setup access point, with no Internet).

The page is one static HTML document (PAGE) that draws itself from JSON: /api/state (everything the dashboard shows), /api/scan
(Wi-Fi networks in range), /api/logs, /api/settings/<game folder> (the form of a game's settings). Actions are POSTs that answer
{ok, msg}. HTTP basic authentication on everything (mpf_netconfig.authorized).
"""
import html
import json
import mimetypes
import os
import platform
import shutil
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpf_common as C  # noqa: E402
import mpf_games as G  # noqa: E402
import mpf_netconfig as N  # noqa: E402
import mpf_monitor as MON  # noqa: E402
import mpf_ota as O  # noqa: E402
from mpf_common import run  # noqa: E402

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}


def uptime():
    try:
        return int(float(open("/proc/uptime").read().split()[0]))
    except (OSError, ValueError):
        return 0


def cpu_temp():
    try:
        return round(int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000, 1)
    except (OSError, ValueError):
        return None


def disk(path):
    try:
        u = shutil.disk_usage(path)
        return {"total": u.total, "free": u.free}
    except OSError:
        return None


def game_icon(g):
    """URL of a game's picture (bundle.json "icon": a path inside the bundle), or None."""
    rel = str(g["bundle"].get("icon") or "")
    if not rel or os.path.splitext(rel)[1].lower() not in IMAGE_TYPES:
        return None
    p = os.path.realpath(os.path.join(g["path"], rel))
    if not p.startswith(os.path.realpath(g["path"]) + os.sep) or not os.path.isfile(p):
        return None
    return f"/media/{g['folder']}"


def state():
    games = []
    for g in G.installed_games():
        b = g["bundle"]
        games.append({
            "folder": g["folder"], "id": g["id"], "name": g["name"], "version": g["version"], "active": g["active"],
            "description": str(b.get("description", ""))[:300], "icon": game_icon(g),
            "pup": {"supported": bool(b.get("pup")), "installed": G.pup_installed(g["path"], b), "assigned": G.pup_assigned(g["path"], b)},
            "settings": bool(G.options_tool(g["path"])),
            "installed": int(g["mtime"]),
        })
    mode = C.mode_status()
    return {
        "hostname": socket.gethostname(), "arch": C.ARCH.get(platform.machine(), platform.machine()),
        "uptime": uptime(), "temp": cpu_temp(),
        "network": N.network_info(),
        "game": {"running": G.game_running(), "autostart": G.game_autostart()},
        "games": games,
        "pups": G.pup_library(),
        "storage": {"games": disk(C.GAMES if os.path.isdir(C.GAMES) else "/"), "readonly": C.READONLY,
                    "degraded": os.path.exists("/run/mpf-persist.degraded")},
        "mode": {"mode": mode[0], "stay": mode[1]} if mode else None,
        "job": G.job_state(),
        "ota": O.public(),
        "inbox": sorted(n for n in (os.listdir(C.INBOX) if os.path.isdir(C.INBOX) else []) if n.endswith((".tar.xz", ".zip"))),
    }


def settings_form(game):
    """The settings of a game as a form, built from the bundle's own schema (the board's limits already applied)."""
    try:
        schema = G.settings_schema(game)
        cur = json.loads(G.tool(game, "get").stdout or "{}")
    except (OSError, ValueError):
        return "<p>Settings unavailable.</p>"
    out = []
    for g in schema["groups"]:
        out.append(f"<fieldset><legend>{html.escape(g['label'])}</legend>")
        for o in (o for o in schema["options"] if o["group"] == g["id"]):
            name, v = "o." + o["id"], cur.get(o["id"])
            hint = f" <small>(default {html.escape(str(o['default']))})</small>" if "default" in o else ""
            if o["type"] == "bool":
                sel = {True: "true", False: "false"}.get(v, "")
                field = f"<select name='{name}'>" + "".join(
                    f"<option value='{x}'{' selected' if x == sel else ''}>{x or 'default'}</option>" for x in ("", "true", "false")) + "</select>"
            elif o["type"] == "choice":
                field = f"<select name='{name}'><option value=''>default</option>" + "".join(
                    f"<option{' selected' if c == v else ''}>{html.escape(c)}</option>" for c in o["choices"]) + "</select>"
            elif o.get("secret"):
                field = f"<input name='{name}' type=password placeholder='{'set' if v else 'not set'} (empty: unchanged)'>"
            else:
                val = "" if v is None else html.escape(str(v), quote=True)
                field = f"<input name='{name}' value='{val}' placeholder='default'>"
            note = f" <small class=limit>this board: {html.escape(o['limited'])}</small>" if o.get("limited") else ""
            out.append(f"<label title='{html.escape(o.get('help', ''), quote=True)}'><span>{html.escape(o['label'])}{hint}</span>"
                       f"{field} <small>{html.escape(o.get('unit', ''))}</small>{note}</label>")
        out.append("</fieldset>")
    return "".join(out)


def game_logs(lines=80):
    r = run("journalctl", "-u", "mpf-game.service", "-n", str(lines), "--no-pager", "-o", "short-iso")
    return (r.stdout or r.stderr).strip() or "(no output yet)"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=()):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json")

    def _auth(self):
        if N.authorized(self.headers.get("Authorization")):
            return True
        self._send(401, "Authentication required", "text/plain", [("WWW-Authenticate", 'Basic realm="MPF setup"')])
        return False

    def _drain(self, n):
        while n > 0:     # read the body so the browser can see the answer instead of a broken pipe
            n -= len(self.rfile.read(min(1 << 20, n)) or b"x" * n)

    # ---------------------------------------------------------------- upload
    def _upload(self, kind, q):
        """One chunk of an upload, appended at `offset` (the browser sends 4 MB at a time and resumes after a cut).
        When the file is complete it is unpacked and installed in a thread."""
        n = int(self.headers.get("Content-Length", 0))
        off, total = int(q.get("offset", ["0"])[0]), int(q.get("total", ["0"])[0])
        name = os.path.basename(q.get("name", [""])[0]) or kind
        folder = q.get("folder", [""])[0] or None
        path = os.path.join(C.UPLOADS, "game.tar.xz" if kind == "game" else "pup.zip")
        try:
            if G.JOB["state"] == "running" or G.JOB_LOCK.locked():
                raise ValueError("an install is already running")
            if off == 0:
                ok = name.endswith(".tar.xz") if kind == "game" else name.lower().endswith(".zip")
                me = C.ARCH.get(platform.machine(), platform.machine())
                if not ok:
                    raise ValueError("expected a .tar.xz bundle" if kind == "game" else "expected a .zip pack")
                if "linux-" in name and kind == "game" and not name.endswith((f"linux-{me}.tar.xz", "linux-all.tar.xz")):
                    raise ValueError(f"this machine is {me}: wrong bundle")
                if G.free_gb(C.UPLOADS) * 1e9 < total * (4 if kind == "game" else 2) + 5e8:
                    raise ValueError("not enough free disk space for this file")
                open(path, "wb").close()
                G.JOB.update(state="uploading", msg="Receiving " + name, log="")
            have = os.path.getsize(path) if os.path.exists(path) else 0
            if have != off:     # the client lost track: tell it where to resume
                self.rfile.read(n)
                return self._send(409, str(have), "text/plain")
            with open(path, "ab") as f:
                left = n
                while left:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        raise OSError("upload interrupted")
                    f.write(chunk)
                    left -= len(chunk)
        except ValueError as e:
            G.job_set(state="error", msg=str(e))
            self._drain(n)
            return self._send(400, str(e), "text/plain")
        except OSError:
            return          # the browser went away: it resumes from the file's size
        if off + n < total:
            return self._send(200, str(off + n), "text/plain")
        if not G.JOB_LOCK.acquire(blocking=False):
            return self._send(409, "busy", "text/plain")
        if kind == "game":
            fn, args = G.install_game, (path, q.get("sha", [""])[0], q.get("keep", ["1"])[0] != "0")
        else:
            fn, args = G.store_pup, (path, name)
        G.job_set(state="running", msg="Received, installing" if kind == "game" else "Received, checking the pack")
        threading.Thread(target=G.run_job, args=(fn,) + args, daemon=True).start()
        self._send(202, "installing", "text/plain")

    # ---------------------------------------------------------------- routes
    def do_GET(self):
        if not self._auth():
            return
        u = urlparse(self.path)
        p = u.path
        if p in ("/", "/index.html"):
            return self._send(200, PAGE)
        if p == "/job":
            return self._json(G.job_state())
        if p == "/api/state":
            return self._json(state())
        if p == "/api/ota/list":
            try:
                return self._json(O.list_remote())
            except ValueError as e:
                return self._json({"ok": False, "msg": str(e)}, 400)
        if p == "/api/scan":
            return self._json(N.scan())
        if p == "/api/logs":
            return self._send(200, game_logs(), "text/plain; charset=utf-8")
        if p == "/api/logs/saved":
            return self._json(MON.saved_logs()[::-1])
        if p.startswith("/api/logs/saved/"):
            text = MON.read_saved(unquote(p.rsplit("/", 1)[1]))
            if text is None:
                return self._send(404, "not found", "text/plain")
            return self._send(200, text, "text/plain; charset=utf-8", [("Content-Disposition", 'attachment; filename="%s"' % unquote(p.rsplit("/", 1)[1]))])
        if p == "/api/monitor/layout":
            return self._json(MON.layout(next((g for g in G.installed_games() if g["active"]), None)) or {})
        if p == "/api/monitor/image":
            img = MON.layout_files(next((g for g in G.installed_games() if g["active"]), None))[1]
            if not img:
                return self._send(404, "not found", "text/plain")
            with open(img, "rb") as f:
                return self._send(200, f.read(), mimetypes.guess_type(img)[0] or "image/jpeg", [("Cache-Control", "max-age=300")])
        if p == "/api/monitor":
            q = parse_qs(u.query)
            return self._json(MON.MON.snapshot(*(float(q.get(k, ["0"])[0] or 0) for k in ("since",)), *(int(q.get(k, ["0"])[0] or 0) for k in ("rev", "epoch"))))
        if p.startswith("/api/settings/"):
            game = G.installed_game(unquote(p.rsplit("/", 1)[1]))
            return self._json({"html": settings_form(game)}) if game else self._json({"error": "no such game"}, 404)
        if p.startswith("/media/"):
            for g in G.installed_games():
                if g["folder"] == p[len("/media/"):] and game_icon(g):
                    f = os.path.join(g["path"], str(g["bundle"]["icon"]))
                    return self._send(200, open(f, "rb").read(), mimetypes.guess_type(f)[0] or "application/octet-stream",
                                      [("Cache-Control", "max-age=300")])
            return self._send(404, "not found", "text/plain")
        if p.startswith("/upload/size/"):
            f = os.path.join(C.UPLOADS, "game.tar.xz" if p.endswith("game") else "pup.zip")
            return self._send(200, str(os.path.getsize(f) if os.path.exists(f) else 0), "text/plain")
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        if not self._auth():
            return
        u = urlparse(self.path)
        if u.path in ("/upload/game", "/upload/pup"):
            return self._upload(u.path.rsplit("/", 1)[1], parse_qs(u.query))
        n = int(self.headers.get("Content-Length", 0))
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(min(n, 262144)).decode()).items()}
        try:
            msg = self._action(u.path, form)
            self._json({"ok": True, "msg": msg})
        except (ValueError, TypeError, OSError, G.JobError) as e:
            self._json({"ok": False, "msg": str(e)}, 400)

    def _action(self, path, form):
        if path == "/api/wifi":
            N.add_wifi(form.get("ssid", ""), form.get("psk", ""), form.get("country", "").upper())
            return "Wi-Fi saved, connecting (the address may change)."
        if path == "/api/ota/config":
            O.save(form.get("url", ""), form.get("user", ""), form.get("password", ""), form.get("folder", ""))
            return "Update server saved."
        if path == "/api/ota/install":
            # the item comes from the server's own listing, never from the browser's address: the saved password must not be
            # sent to an address the page was handed
            item = next((i for i in O.list_remote() if i["key"] == form.get("key") and i["compatible"]), None)
            if item is None:
                raise ValueError("that file is not on the server (any more) or is not for this machine")
            if not G.JOB_LOCK.acquire(blocking=False):
                raise ValueError("an install is already running")
            G.job_set(state="running", msg="Starting the download", log="")
            threading.Thread(target=G.run_job, args=(O.install_item, item), daemon=True).start()
            return "Installing " + item["name"]
        if path in ("/api/pup/assign", "/api/pup/unassign", "/api/pup/delete"):
            if not G.JOB_LOCK.acquire(blocking=False):
                raise ValueError("an install is already running")
            G.job_set(state="running", msg="Working on the PuP Pack", log="")
            if path == "/api/pup/assign":
                fn, args = G.assign_pup, (form.get("folder", ""), form.get("pack", ""))
            elif path == "/api/pup/unassign":
                fn, args = G.unassign_pup, (form.get("folder", ""),)
            else:
                fn, args = G.delete_pup_job, (form.get("pack", ""),)
            threading.Thread(target=G.run_job, args=(fn,) + args, daemon=True).start()
            return "Working on it"
        if path == "/api/logs/save":
            name = MON.save_log(next((g for g in G.installed_games() if g["active"]), None))
            return f"Saved as {name} in {MON.SAVED}"
        if path == "/api/monitor/switch":
            MON.MON.set_switch(form.get("name", ""), form.get("do", "toggle"))
            return "ok"
        if path == "/api/ssh":
            if form.get("key"):
                N.add_ssh_key(form["key"].strip())
            if form.get("pwlogin") in ("yes", "no"):
                N.set_ssh_password_login(form["pwlogin"] == "yes")
            return "SSH settings saved."
        if path == "/api/mode":
            do = form.get("do", "")
            C.set_mode(do.split("-")[0], stay=do == "maintenance-stay")
            return "Production mode: the system is read-only again." if do == "production" else "Maintenance mode: the system is writable."
        if path == "/api/game":
            do = form.get("do")
            if do == "start":
                G.game_start()
                return "Game starting."
            if do == "restart":
                G.game_restart()
                return "Game restarting."
            if do in ("enable", "disable"):
                G.set_autostart(do == "enable")
                return "The game now starts at power-on." if do == "enable" else "The game no longer starts at power-on."
            G.game_stop()
            return "Game stopped."
        if path == "/api/activate":
            was = G.game_running()
            G.set_active(form.get("folder", ""))
            G.set_autostart(True)
            if was:
                G.game_restart()
            g = G.installed_game(form.get("folder", ""))
            pack = " with its PuP Pack" if g and G.pup_installed(g) else (" (it has no PuP Pack)" if g else "")
            return "This game now starts at power-on" + pack + (" and is restarting." if was else ".")
        if path == "/api/delete":
            G.delete_game(form.get("folder", ""))
            return "Game removed."
        if path.startswith("/api/settings/"):
            game = G.installed_game(unquote(path.rsplit("/", 1)[1]))
            if not game:
                raise ValueError("no such game")
            G.settings_save(game, form)
            return "Settings saved (restart the game to apply)."
        raise ValueError("unknown action")

    def log_message(self, *a):
        pass


def serve():
    ThreadingHTTPServer(("", C.PORT), Handler).serve_forever()


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MPF setup</title>
<style>
:root{--bg:#0a0e1d;--bg2:#0e1428;--card:#131a33;--card2:#19224a;--line:#26315e;--text:#e8ecff;--dim:#93a0cf;--accent:#37d2ff;--accent2:#7b6bff;
--ok:#3ddc97;--warn:#ffb84d;--bad:#ff6b81;--r:16px;--shadow:0 8px 30px rgba(0,0,0,.35)}
@media (prefers-color-scheme:light){:root{--bg:#eef1fb;--bg2:#e4e9f8;--card:#fff;--card2:#f3f6ff;--line:#d4dcf2;--text:#141a33;--dim:#5a6798;--accent:#0a8fd1;--accent2:#5a49e0;--shadow:0 8px 24px rgba(30,45,110,.12)}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--text);background:radial-gradient(1200px 600px at 80% -10%,rgba(123,107,255,.18),transparent 60%),radial-gradient(900px 500px at -10% 10%,rgba(55,210,255,.14),transparent 55%),var(--bg);min-height:100vh}
header{display:flex;align-items:center;gap:14px;padding:18px clamp(14px,4vw,40px);position:sticky;top:0;z-index:5;background:linear-gradient(var(--bg),rgba(0,0,0,0));backdrop-filter:blur(10px)}
.logo{width:42px;height:42px;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));display:grid;place-items:center;box-shadow:0 0 24px rgba(55,210,255,.35)}
.logo svg{width:24px;height:24px;stroke:#fff}
h1{font-size:20px;margin:0;letter-spacing:.3px;white-space:nowrap}a{color:var(--accent)}input[type=file]{padding:6px}input[type=file]::file-selector-button{font:inherit;margin-right:10px;border:1px solid var(--line);background:var(--card2);color:var(--text);border-radius:8px;padding:5px 10px;cursor:pointer}header small{color:var(--dim);display:block;font-size:12.5px}
.sp{flex:1}.lang{width:auto;background:var(--card);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:6px 10px;font:inherit}
main{max-width:980px;margin:0 auto;padding:6px clamp(14px,4vw,40px) 60px;display:grid;gap:22px}
h2{font-size:13px;letter-spacing:1.6px;text-transform:uppercase;color:var(--dim);margin:6px 2px 10px;display:flex;align-items:center;gap:8px}
h2 svg{width:16px;height:16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(210px,100%),1fr));gap:14px}
.card{background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:var(--r);padding:16px;box-shadow:var(--shadow)}
.tile{display:flex;gap:12px;align-items:flex-start}.tile .ic{width:40px;height:40px;border-radius:11px;background:rgba(55,210,255,.12);display:grid;place-items:center;flex:none}
.tile button.ic{border:0;padding:0;cursor:pointer}.tile button.ic:hover{background:rgba(55,210,255,.28);transform:none}.tile .ic svg{width:22px;height:22px;stroke:var(--accent)}.tile b{display:block;font-size:16px}.tile span{color:var(--dim);font-size:13px;word-break:break-word}
.badge{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid var(--line);background:var(--bg2);color:var(--dim)}
.badge.ok{color:var(--ok);border-color:rgba(61,220,151,.4);background:rgba(61,220,151,.1)}.badge.warn{color:var(--warn);border-color:rgba(255,184,77,.45);background:rgba(255,184,77,.1)}
.badge.bad{color:var(--bad);border-color:rgba(255,107,129,.45);background:rgba(255,107,129,.1)}.badge.acc{color:var(--accent);border-color:rgba(55,210,255,.45);background:rgba(55,210,255,.1)}
.dot{width:8px;height:8px;border-radius:50%;background:currentColor}.pulse .dot{animation:p 1.4s infinite}@keyframes p{50%{opacity:.25}}
.games{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(280px,100%),1fr));gap:16px}
.game{display:flex;flex-direction:column;gap:12px;position:relative;overflow:hidden}.game.active{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent),0 0 32px rgba(55,210,255,.2)}
.cover{height:120px;border-radius:12px;background:linear-gradient(135deg,#1c2a63,#3a2a7a) center/cover;display:grid;place-items:center;color:rgba(255,255,255,.85)}
.cover svg{width:44px;height:44px;stroke:currentColor;opacity:.8}.game h3{margin:0;font-size:17px}.game p{margin:0;color:var(--dim);font-size:13px}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.grow{flex:1}
button,.btn{font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--card2);color:var(--text);padding:8px 14px;border-radius:11px;display:inline-flex;gap:7px;align-items:center;transition:.15s}
button:hover{border-color:var(--accent);transform:translateY(-1px)}button svg{width:16px;height:16px;stroke:currentColor}
button.pri{background:linear-gradient(135deg,var(--accent),var(--accent2));border:0;color:#fff;font-weight:600}button.dng:hover{border-color:var(--bad);color:var(--bad)}button:disabled{opacity:.5;cursor:default;transform:none}
.drop{border:2px dashed var(--line);border-radius:var(--r);padding:26px 16px;text-align:center;color:var(--dim);transition:.15s;cursor:pointer;background:rgba(55,210,255,.03)}
.drop:hover,.drop.over{border-color:var(--accent);color:var(--text);background:rgba(55,210,255,.08)}.drop svg{width:34px;height:34px;stroke:var(--accent);margin-bottom:6px}.drop b{display:block;color:var(--text)}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:16px}
.bar{height:10px;background:var(--bg2);border-radius:99px;overflow:hidden;border:1px solid var(--line)}.bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--accent),var(--accent2));transition:width .3s}
.bar.run i{background-size:200% 100%;animation:mv 1.2s linear infinite}@keyframes mv{to{background-position:-200% 0}}
input,select,textarea{font:inherit;color:var(--text);background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:8px 10px;width:100%}
input:focus,select:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
.form{display:grid;gap:10px}.form label{display:grid;gap:4px;color:var(--dim);font-size:13px}
.nets{display:grid;gap:6px;max-height:260px;overflow:auto;margin:8px 0}.net{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:10px;border:1px solid var(--line);cursor:pointer;background:var(--bg2)}
.net:hover{border-color:var(--accent)}a.net{color:var(--text);text-decoration:none}.net svg{width:16px;height:16px;flex:none}.sig{display:inline-flex;gap:2px;align-items:flex-end;height:16px}.sig i{width:4px;background:var(--line);border-radius:1px}.sig i.on{background:var(--accent)}
.sig i:nth-child(1){height:5px}.sig i:nth-child(2){height:8px}.sig i:nth-child(3){height:12px}.sig i:nth-child(4){height:16px}
main>*,.card,.two>*,.games>*,.tiles>*{min-width:0}html,body{overflow-x:hidden}
pre{margin:0;max-height:300px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:#05081a;color:#b8c4ff;padding:12px;border-radius:12px;font:12px/1.5 ui-monospace,Menlo,Consolas,monospace;border:1px solid var(--line)}
dialog{border:1px solid var(--line);border-radius:var(--r);background:var(--card);color:var(--text);max-width:min(720px,94vw);width:100%;padding:0}dialog::backdrop{background:rgba(3,6,20,.7);backdrop-filter:blur(3px)}
dialog .hd{display:flex;align-items:center;padding:14px 18px;border-bottom:1px solid var(--line)}dialog .bd{padding:14px 18px;max-height:70vh;overflow:auto}dialog .ft{padding:12px 18px;border-top:1px solid var(--line);display:flex;gap:8px;justify-content:flex-end}
fieldset{border:1px solid var(--line);border-radius:12px;margin:0 0 12px;padding:10px 12px;display:grid;gap:8px}legend{color:var(--accent);padding:0 6px;font-weight:600}
fieldset label{display:grid;grid-template-columns:minmax(120px,1fr) minmax(120px,1.2fr);gap:4px 10px;align-items:center;color:var(--text)}fieldset small{color:var(--dim)}fieldset small.limit{grid-column:1/-1;color:var(--warn)}
#toast{position:fixed;left:50%;bottom:24px;opacity:0;pointer-events:none;transform:translateX(-50%) translateY(120px);background:var(--card2);border:1px solid var(--line);padding:11px 18px;border-radius:12px;box-shadow:var(--shadow);transition:.3s;z-index:20;max-width:92vw}
#toast.show{transform:translateX(-50%);opacity:1}#toast.err{border-color:var(--bad);color:var(--bad)}
.banner{border-radius:var(--r);padding:12px 16px;border:1px solid rgba(255,184,77,.5);background:rgba(255,184,77,.1);color:var(--warn)}.banner.bad{border-color:rgba(255,107,129,.5);background:rgba(255,107,129,.1);color:var(--bad)}
.tabs{display:flex;gap:6px;border-bottom:1px solid var(--line);overflow-x:auto}.tabs button{border:0;border-bottom:2px solid transparent;border-radius:10px 10px 0 0;background:none;color:var(--dim);padding:10px 16px}
.tabs button:hover{transform:none;color:var(--text)}.tabs button.on{color:var(--accent);border-bottom-color:var(--accent)}
dialog.wide{max-width:min(980px,96vw)}.sws{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px}
.sw{justify-content:flex-start;padding:6px 10px;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block;text-align:left}
.sw.on{background:var(--ok);border-color:var(--ok);color:#04210f;font-weight:600}.sw small{display:block;opacity:.7;font-size:11px}
#monCard.fsx{position:fixed;inset:0;z-index:60;border-radius:0;overflow:auto;background:var(--bg);padding:10px}#monCard.fsx .pfw img{height:calc(var(--z,1)*(100vh - 70px));max-width:none}
#monCard.fsx #monLogBox,#monCard.fsx h2,#monCard.fsx .muted[data-t=monHint]{display:none}
.pfw{position:relative;display:inline-block;line-height:0}.pfw img{height:calc(var(--z,1)*min(80vh,860px));max-width:100%;width:auto;display:block;border-radius:10px}
.sp{position:absolute;transform:translate(-50%,-50%);aspect-ratio:1;min-width:12px;touch-action:none;user-select:none;-webkit-user-select:none;border-radius:50%;border:1.5px solid rgba(255,255,255,.6);background:rgba(0,0,0,.4);color:#fff;display:grid;place-items:center;font:bold 10px/1 sans-serif;transition:background .08s}
.sp.switch{border-radius:3px;cursor:pointer}.sp.switch.on{background:#3ddc97;border-color:#fff;box-shadow:0 0 8px #3ddc97}
.sp.light{border-width:1px;border-color:rgba(255,255,255,.35)}.sp.light.lit{box-shadow:0 0 9px 2px currentColor;border-color:#fff}
.sp.coil{border-radius:2px;border-style:dashed;opacity:.55;min-width:8px}.sp.flipper,.sp.autofire,.sp.diverter,.sp.drop_target{border-color:#7b6bff}.sp.flipper.on,.sp.autofire.on,.sp.diverter.on,.sp.drop_target.on{background:#7b6bff}
.sp.ball_device{border-radius:5px;border-color:#37d2ff}.sp.ball_device.on{background:#37d2ff;color:#04210f}.sp.dim{opacity:.12}
.hide{display:none!important}.muted{color:var(--dim)}.mt{margin-top:10px}
@media (max-width:560px){fieldset label{grid-template-columns:1fr}}
</style></head><body>
<svg width="0" height="0" style="position:absolute"><defs>
<symbol id="i-pin" viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="9" r="5"/><path d="M12 14v7M8 21h8"/></symbol>
<symbol id="i-play" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4l13 8-13 8z"/></symbol>
<symbol id="i-stop" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"/></symbol>
<symbol id="i-redo" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5"/></symbol>
<symbol id="i-wifi" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 9a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/><circle cx="12" cy="19.5" r="1"/></symbol>
<symbol id="i-disk" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></symbol>
<symbol id="i-lock" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></symbol>
<symbol id="i-up" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4M7 9l5-5 5 5M4 20h16"/></symbol>
<symbol id="i-trash" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></symbol>
<symbol id="i-gear" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14 3h-4l-.6 2.7a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2L10 21h4l.6-2.7a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z"/></symbol>
<symbol id="i-cpu" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/></symbol>
<symbol id="i-term" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 17l6-5-6-5M12 19h8"/></symbol>
</defs></svg>
<header><div class="logo"><svg><use href="#i-pin"/></svg></div><div><h1>MPF setup</h1><small id="host">&nbsp;</small></div><div class="sp"></div>
<select class="lang" id="lang"><option value="en">English</option><option value="fr">Français</option></select></header>
<main>
<div id="banners"></div>
<section><div class="tiles" id="tiles"></div></section>
<nav class="tabs" id="tabs"><button data-go="games"><span data-t="tabGames"></span></button><button data-go="install"><span data-t="tabInstall"></span></button><button data-go="config"><span data-t="tabConfig"></span></button><button data-go="monitor"><span data-t="monitor"></span></button></nav>

<section data-tab="games"><h2><svg stroke="currentColor"><use href="#i-play"/></svg><span data-t="games"></span></h2><div class="games" id="games"></div><p class="muted mt" id="autoNote"></p></section>

<section data-tab="install"><h2><svg stroke="currentColor"><use href="#i-up"/></svg><span data-t="add"></span></h2>
<div class="card"><div class="two">
 <div><div class="drop" id="dropGame"><svg><use href="#i-up"/></svg><b data-t="dropGame"></b><span data-t="dropGameHint"></span></div>
  <input type="file" id="fGame" accept=".xz" class="hide"><label class="row mt muted"><input type="checkbox" id="keepOld" checked style="width:auto"> <span data-t="keepOld"></span></label>
  <label class="muted mt" style="display:block"><span data-t="sha"></span> <input type="file" id="fSha" accept=".sha256,.txt"></label>
  <div class="row mt"><button class="pri" id="goGame" disabled><svg><use href="#i-up"/></svg><span data-t="goGame"></span></button></div></div>
 <div><div class="drop" id="dropPup"><svg><use href="#i-up"/></svg><b data-t="dropPup"></b><span data-t="dropPupHint"></span></div>
  <input type="file" id="fPup" accept=".zip" class="hide"><div class="row mt"><button class="pri" id="goPup" disabled><svg><use href="#i-up"/></svg><span data-t="goPup"></span></button></div></div>
</div>
<div class="mt hide" id="jobBox"><div class="row"><b id="jobMsg" class="grow"></b><span class="badge" id="jobBadge"></span></div><div class="bar mt" id="jobBar"><i></i></div><pre id="jobLog" class="mt hide"></pre></div>
<p class="muted mt" id="inboxNote"></p></div></section>

<section data-tab="install"><h2><svg stroke="currentColor"><use href="#i-play"/></svg><span data-t="packs"></span></h2><div class="card">
 <div class="nets" id="packList"></div><p class="muted" id="packNone"></p>
 <h3 class="mt" data-t="assign"></h3><div class="nets" id="packGrid"></div><p class="muted mt" data-t="assignHint"></p></div></section>

<section data-tab="install"><h2><svg stroke="currentColor"><use href="#i-redo"/></svg><span data-t="ota"></span></h2><div class="card">
 <form class="form" id="otaForm"><div class="two"><label><span data-t="otaUrl"></span><input name="url" id="otaUrl" placeholder="https://server.example" autocomplete="off"></label>
 <label><span data-t="otaFolder"></span><input name="folder" id="otaFolder" placeholder="MPF Games" autocomplete="off"></label></div><div class="two">
 <label><span data-t="otaUser"></span><input name="user" id="otaUser" autocomplete="off"></label>
 <label><span data-t="otaPw"></span><input name="password" id="otaPw" type="password" autocomplete="new-password"></label></div>
 <div class="row"><button type="submit"><span data-t="otaSave"></span></button><button type="button" id="otaCheck" class="pri"><span data-t="otaCheck"></span></button><span class="muted" data-t="otaHint"></span></div></form>
 <div class="nets mt" id="otaList"></div></div></section>

<div class="two" data-tab="config">
<section><h2><svg stroke="currentColor"><use href="#i-wifi"/></svg><span data-t="network"></span></h2><div class="card">
 <div class="row"><span id="netNow" class="grow"></span><button id="scanBtn"><svg><use href="#i-redo"/></svg><span data-t="scan"></span></button></div>
 <div class="nets" id="nets"></div>
 <form class="form" id="wifiForm"><label><span data-t="ssid"></span><input name="ssid" id="ssid" required autocomplete="off"></label>
 <label><span data-t="psk"></span><input name="psk" type="password" autocomplete="new-password"></label>
 <label><span data-t="country"></span><input name="country" maxlength="2" placeholder="FR" style="max-width:90px"></label>
 <div><button class="pri" type="submit"><span data-t="connect"></span></button></div></form></div></section>

<section><h2><svg stroke="currentColor"><use href="#i-lock"/></svg><span data-t="system"></span></h2><div class="card">
 <form class="form" id="sshForm"><label><span data-t="sshKey"></span><input name="key" placeholder="ssh-ed25519 AAAA…" autocomplete="off"></label>
 <label><span data-t="sshPw"></span><select name="pwlogin"><option value="" data-t="unchanged"></option><option value="yes">yes</option><option value="no">no</option></select></label>
 <div><button type="submit"><span data-t="save"></span></button></div></form>
 <div id="modeBox" class="mt hide"></div>
 </div></section>
</div>
<section data-tab="config"><h2><svg stroke="currentColor"><use href="#i-term"/></svg><span data-t="diag"></span></h2><div class="card">
 <div class="row"><button id="logsBtn"><svg><use href="#i-term"/></svg><span data-t="logs"></span></button><button id="saveLogBtn" class="pri"><svg><use href="#i-disk"/></svg><span data-t="saveLog"></span></button><button id="monBtn"><svg><use href="#i-cpu"/></svg><span data-t="monitor"></span></button></div>
 <p class="muted mt" data-t="saveLogHint"></p><div class="nets" id="savedLogs"></div></div></section>
<section data-tab="monitor"><h2><svg stroke="currentColor"><use href="#i-cpu"/></svg><span data-t="monitor"></span>&nbsp;<span class="badge" id="monBadge"></span></h2><div class="card" id="monCard"><div class="row"><button id="monFull" type="button" title="">⛶</button><input id="monFilter" style="max-width:240px" data-ph="monFilter"><span id="monZoomBox" class="row hide"><label class="muted row" style="gap:6px"><span data-t="monZoom"></span><input type="range" id="monZ" min="0.5" max="4" step="0.1" style="width:110px;padding:0"></label><label class="muted row" style="gap:6px"><span data-t="monSize"></span><input type="range" id="monK" min="0.8" max="4" step="0.1" style="width:90px;padding:0"></label><button id="monFit" type="button">1:1</button></span><select id="monView" style="width:auto" class="hide"><option value="pf" data-t="monViewPf"></option><option value="list" data-t="monViewList"></option></select><span class="muted" id="monCount"></span></div>
<p class="muted" data-t="monHint"></p><div id="monPf" class="hide" style="text-align:center;overflow-x:auto"><div class="pfw" id="pfw"><img id="pfImg" alt=""></div></div><div class="sws mt" id="monGrid"></div><h2 class="mt"><span data-t="monLog"></span></h2><pre id="monLogBox" style="max-height:160px"></pre></div></section>
</main>

<dialog id="dlg"><div class="hd"><b id="dlgTitle" class="grow"></b><button id="dlgClose">✕</button></div><div class="bd" id="dlgBody"></div><div class="ft" id="dlgFoot"></div></dialog>
<div id="toast"></div>

<script>
const T={en:{tabGames:"Games",tabInstall:"Install and updates",tabConfig:"Configuration",diag:"Diagnostics",saveLog:"Save the game log",saveLogHint:"Writes the game output, the machine state and the latest switch changes to one file on the data partition (the live logs are in RAM), to hand it over for debugging.",savedLogs:"Saved logs",monitor:"Switch monitor",monFilter:"Filter…",monToggle:"Click flips the switch",monTap:"Click taps the switch",monHint:"Live view through MPF's BCP connection (the game must be running). Short press = the switch closes and opens, long press = it stays closed while you hold, right click = flips it. Ctrl + wheel zooms.",monLog:"Latest changes",monNone:"No switch yet",monZoom:"Zoom",monSize:"Size",monViewPf:"Playfield",monViewList:"List",monOn:"on",monOff:"off",monConn:"Connected",monDisc:"Not connected",games:"Games",add:"Add a game or a PuP Pack",dropGame:"Game bundle",dropGameHint:"Drop a .tar.xz here or click",dropPup:"PuP Pack",dropPupHint:"Drop the pack's .zip here or click",
goGame:"Upload and install",goPup:"Add to the library",packs:"PuP Packs",assign:"Pack of each game",assignHint:"A pack is added to the library once, then given to a game here. Switching it costs no new upload (the game keeps a link to the pack).",noPack:"No pack",ownPack:"installed with the game",packNone:"No pack in the library yet.",del:"Delete",confirmDelPack:"Remove this pack from the library?",otaFolder:"Folder on the server",otaUpdates:"updates",otaNew:"new game",keepOld:"Keep the older versions of this game",sha:"Its .sha256 file (optional)",packFor:"Install the pack for",network:"Network",system:"System",scan:"Scan",ssid:"Network name",psk:"Password",country:"Country code",connect:"Save and connect",
sshKey:"SSH public key",sshPw:"SSH password login",unchanged:"unchanged",save:"Save",logs:"Game output",active:"Active",activate:"Activate at startup",start:"Start",stop:"Stop",restart:"Restart",settings:"Settings",delete:"Remove",
running:"Running",stopped:"Stopped",noGames:"No game installed yet. Add a bundle below.",pupYes:"PuP Pack installed",pupNo:"no PuP Pack",version:"Version",confirmDel:"Remove this game with its settings and scores?",
game:"Game",storage:"Storage",free:"free",uptime:"Up",online:"Online",offline:"Offline",autostart:"Starts at power-on",noAuto:"Does not start at power-on",enableAuto:"Start at power-on",disableAuto:"Do not start at power-on",
mode:"Mode",production:"Production",maintenance:"Maintenance",prodTxt:"The system is read-only: the flash is not worn. Games, settings, scores, Wi-Fi and SSH keys are stored on the data partition and can be changed.",
maintTxt:"The system is writable (for updates of the operating system). Go back to production when you are done.",toMaint:"Maintenance until reboot",toMaintStay:"Maintenance, also after reboots",toProd:"Back to production",
degraded:"No data partition: settings and scores are kept in RAM and are lost at power-off.",inbox:"Waiting in the inbox (installed at the next boot): ",inboxHelp:"Files copied to the inbox folder are installed at boot.",
uploading:"Uploading",installing:"Installing",done:"Done",error:"Error",hostPrefix:"Address",signal:"signal",openNet:"open",selectGame:"Pick a game",saved:"Saved",close:"Close",cancel:"Cancel",saveSettings:"Save settings",none:"none",ota:"Updates (WebDAV)",otaUrl:"Server address",otaUser:"User",otaPw:"Password",otaPwKept:"unchanged",otaSave:"Save",otaCheck:"Check for updates",otaInstall:"Install",otaDone:"Installed",otaChanged:"Changed on the server",otaNone:"Nothing found in this folder",otaGame:"Game",otaPack:"PuP Pack",otaHint:"The address is the server only; the folder (default MPF Games) holds bundles (.tar.xz, with a .sha256), in sub-folders per game if you like, and PuP Pack .zip files (they go to the library)."},
fr:{tabGames:"Jeux",tabInstall:"Installation et mises à jour",tabConfig:"Configuration",diag:"Diagnostic",saveLog:"Enregistrer le jeu (log)",saveLogHint:"Écrit la sortie du jeu, l'état de la machine et les derniers changements de switches dans un fichier sur la partition de données (les logs en cours sont en RAM), à fournir pour le débogage.",savedLogs:"Logs enregistrés",monitor:"Moniteur de switches",monFilter:"Filtrer…",monToggle:"Un clic inverse le switch",monTap:"Un clic fait une impulsion",monHint:"Vue en direct par la connexion BCP de MPF (le jeu doit être démarré). Appui court = le switch se ferme puis s'ouvre, appui long = il reste fermé tant que vous maintenez, clic droit = bascule. Ctrl + molette = zoom.",monLog:"Derniers changements",monNone:"Aucun switch",monZoom:"Zoom",monSize:"Taille",monViewPf:"Plateau",monViewList:"Liste",monOn:"actif",monOff:"inactif",monConn:"Connecté",monDisc:"Non connecté",games:"Jeux",add:"Ajouter un jeu ou un PuP Pack",dropGame:"Bundle du jeu",dropGameHint:"Déposez un .tar.xz ici ou cliquez",dropPup:"PuP Pack",dropPupHint:"Déposez le .zip du pack ici ou cliquez",
goGame:"Envoyer et installer",goPup:"Ajouter à la bibliothèque",packs:"PuP Packs",assign:"Pack de chaque jeu",assignHint:"Un pack est ajouté une fois à la bibliothèque, puis affecté à un jeu ici. Le changer ne demande pas de nouvel envoi (le jeu garde un lien vers le pack).",noPack:"Aucun pack",ownPack:"installé avec le jeu",packNone:"Aucun pack dans la bibliothèque.",del:"Supprimer",confirmDelPack:"Retirer ce pack de la bibliothèque ?",otaFolder:"Dossier sur le serveur",otaUpdates:"met à jour",otaNew:"nouveau jeu",keepOld:"Garder les anciennes versions de ce jeu",sha:"Son fichier .sha256 (facultatif)",packFor:"Installer le pack pour",network:"Réseau",system:"Système",scan:"Rechercher",ssid:"Nom du réseau",psk:"Mot de passe",country:"Code pays",connect:"Enregistrer et connecter",
sshKey:"Clé publique SSH",sshPw:"Connexion SSH par mot de passe",unchanged:"inchangé",save:"Enregistrer",logs:"Sortie du jeu",active:"Actif",activate:"Activer au démarrage",start:"Démarrer",stop:"Arrêter",restart:"Redémarrer",settings:"Réglages",delete:"Supprimer",
running:"En marche",stopped:"Arrêté",noGames:"Aucun jeu installé. Ajoutez un bundle ci-dessous.",pupYes:"PuP Pack installé",pupNo:"pas de PuP Pack",version:"Version",confirmDel:"Supprimer ce jeu avec ses réglages et ses scores ?",
game:"Jeu",storage:"Stockage",free:"libres",uptime:"Démarré depuis",online:"En ligne",offline:"Hors ligne",autostart:"Démarre à la mise sous tension",noAuto:"Ne démarre pas à la mise sous tension",enableAuto:"Démarrer à la mise sous tension",disableAuto:"Ne pas démarrer à la mise sous tension",
mode:"Mode",production:"Production",maintenance:"Maintenance",prodTxt:"Le système est en lecture seule : la flash ne s'use pas. Jeux, réglages, scores, Wi-Fi et clés SSH sont sur la partition de données et restent modifiables.",
maintTxt:"Le système est modifiable (mises à jour du système). Revenez en production quand vous avez fini.",toMaint:"Maintenance jusqu'au redémarrage",toMaintStay:"Maintenance, même après redémarrage",toProd:"Retour en production",
degraded:"Pas de partition de données : réglages et scores sont en RAM et perdus à l'extinction.",inbox:"En attente dans la boîte d'arrivée (installés au prochain démarrage) : ",inboxHelp:"Les fichiers copiés dans le dossier inbox sont installés au démarrage.",
uploading:"Envoi",installing:"Installation",done:"Terminé",error:"Erreur",hostPrefix:"Adresse",signal:"signal",openNet:"ouvert",selectGame:"Choisir un jeu",saved:"Enregistré",close:"Fermer",cancel:"Annuler",saveSettings:"Enregistrer les réglages",none:"aucun",ota:"Mises à jour (WebDAV)",otaUrl:"Adresse du serveur",otaUser:"Utilisateur",otaPw:"Mot de passe",otaPwKept:"inchangé",otaSave:"Enregistrer",otaCheck:"Chercher les mises à jour",otaInstall:"Installer",otaDone:"Installé",otaChanged:"Modifié sur le serveur",otaNone:"Rien dans ce dossier",otaGame:"Jeu",otaPack:"PuP Pack",otaHint:"L'adresse est celle du serveur seul ; le dossier (MPF Games par défaut) contient les bundles (.tar.xz, avec un .sha256), éventuellement un sous-dossier par jeu, et les PuP Packs .zip (ils vont dans la bibliothèque)."}};
let L=(localStorage.getItem('mpfLang')||navigator.language||'en').slice(0,2);if(!T[L])L='en';
const t=k=>(T[L]&&T[L][k])||T.en[k]||k, $=s=>document.querySelector(s), esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ico=(n,c='')=>`<svg class="${c}" stroke="currentColor"><use href="#i-${n}"/></svg>`;
function applyLang(){document.documentElement.lang=L;$('#lang').value=L;document.querySelectorAll('[data-t]').forEach(e=>e.textContent=t(e.dataset.t));document.querySelectorAll('[data-ph]').forEach(e=>e.placeholder=t(e.dataset.ph));if(S)render(S)}
$('#lang').onchange=e=>{L=e.target.value;localStorage.setItem('mpfLang',L);applyLang()};
let S=null,toastT;
function toast(m,err){const e=$('#toast');e.textContent=m;e.className='show'+(err?' err':'');clearTimeout(toastT);toastT=setTimeout(()=>e.className='',4200)}
async function post(url,data){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(data)});
 let j={};try{j=await r.json()}catch(e){j={ok:false,msg:'?'}}toast(j.msg||'',!j.ok);if(j.ok)refresh();return j}
const fmtB=b=>b>=1e9?(b/1e9).toFixed(1)+' GB':(b/1e6).toFixed(0)+' MB';
const fmtUp=s=>s>=86400?Math.floor(s/86400)+'d '+Math.floor(s%86400/3600)+'h':s>=3600?Math.floor(s/3600)+'h '+Math.floor(s%3600/60)+'m':Math.floor(s/60)+'m';
function sig(dbm){const n=dbm>-55?4:dbm>-65?3:dbm>-75?2:dbm>-85?1:0;return `<span class="sig">${[1,2,3,4].map(i=>`<i class="${i<=n?'on':''}"></i>`).join('')}</span>`}
function render(s){
 $('#host').textContent=s.hostname+' · '+s.arch;
 const wf=s.network.wifi,ad=s.network.addresses,on=ad.length>0,g=s.games.find(x=>x.active),st=s.storage.games;
 const tiles=[];
 tiles.push(`<div class="card tile"><button class="ic" data-a="${s.game.running?'stop':'start'}" title="${s.game.running?t('stop'):t('start')}">${ico(s.game.running?'stop':'play')}</button><div><span>${t('game')}</span><b>${g?esc(g.name):t('none')}</b>
  <span class="badge ${s.game.running?'ok pulse':'warn'}"><i class="dot"></i>${s.game.running?t('running'):t('stopped')}</span></div></div>`);
 tiles.push(`<div class="card tile"><div class="ic">${ico('wifi')}</div><div><span>${t('network')}</span><b>${on?t('online'):t('offline')}</b><span>${ad.map(a=>esc(a[0])+' '+esc(a[1])).join('<br>')}${wf?'<br>'+esc(wf.ssid)+' '+(wf.signal!=null?wf.signal+' dBm':''):''}</span></div></div>`);
 if(st){const used=st.total-st.free,pct=Math.round(used*100/st.total);tiles.push(`<div class="card tile"><div class="ic">${ico('disk')}</div><div style="flex:1"><span>${t('storage')}</span><b>${fmtB(st.free)} ${t('free')}</b><div class="bar" style="margin-top:6px"><i style="width:${pct}%"></i></div></div></div>`)}
 tiles.push(`<div class="card tile"><div class="ic">${ico('cpu')}</div><div><span>${t('uptime')}</span><b>${fmtUp(s.uptime)}</b><span>${s.temp!=null?s.temp+' °C':''}</span></div></div>`);
 $('#tiles').innerHTML=tiles.join('');
 let ban='';if(s.storage.degraded)ban+=`<div class="banner bad">${t('degraded')}</div>`;
 if(s.mode&&s.mode.mode==='maintenance')ban+=`<div class="banner">${t('maintTxt')}</div>`;
 $('#banners').innerHTML=ban;
 $('#games').innerHTML=s.games.length?s.games.map(x=>`<div class="card game ${x.active?'active':''}">
  <div class="cover" ${x.icon?`style="background-image:url('${x.icon}')"`:''}>${x.icon?'':ico('pin')}</div>
  <div><div class="row"><h3 class="grow">${esc(x.name)}</h3>${x.active?`<span class="badge acc">${t('active')}</span>`:''}</div>
  <p>${t('version')} ${esc(x.version)} · ${x.pup.supported?(x.pup.installed?t('pupYes'):t('pupNo')):''}</p>${x.description?`<p>${esc(x.description)}</p>`:''}</div>
  <div class="row">${x.active?(s.game.running?`<button data-a="stop">${ico('stop')}${t('stop')}</button><button data-a="restart">${ico('redo')}${t('restart')}</button>`:`<button class="pri" data-a="start">${ico('play')}${t('start')}</button>`)
   :`<button class="pri" data-a="activate" data-f="${esc(x.folder)}">${ico('play')}${t('activate')}</button>`}
   ${x.settings?`<button data-a="settings" data-f="${esc(x.folder)}" data-n="${esc(x.name)}">${ico('gear')}${t('settings')}</button>`:''}
   <span class="grow"></span><button class="dng" data-a="delete" data-f="${esc(x.folder)}" title="${t('delete')}">${ico('trash')}</button></div></div>`).join(''):`<div class="card muted">${t('noGames')}</div>`;
  const au=s.game.autostart;
 $('#inboxNote').innerHTML=s.inbox.length?t('inbox')+s.inbox.map(esc).join(', '):t('inboxHelp');
 $('#autoNote').innerHTML=`<span>${au?t('autostart'):t('noAuto')}</span> · <a href="#" id="autoLink">${au?t('disableAuto'):t('enableAuto')}</a>`;
 const al=$('#autoLink');if(al)al.onclick=e=>{e.preventDefault();post('/api/game',{do:au?'disable':'enable'})};
 const nn=$('#netNow');nn.innerHTML=on?`<span class="badge ok"><i class="dot"></i>${ad.map(a=>esc(a[1])).join(', ')}</span>`:`<span class="badge warn">${t('offline')}</span>`;
 const mb=$('#modeBox');if(s.mode){mb.classList.remove('hide');const m=s.mode;mb.innerHTML=`<div class="row"><b class="grow">${t('mode')}: <span class="badge ${m.mode==='production'?'ok':'warn'}">${t(m.mode)}${m.stay?' ↻':''}</span></b></div><p class="muted">${m.mode==='production'?t('prodTxt'):t('maintTxt')}</p>
  <div class="row">${m.mode==='production'?`<button data-m="maintenance">${t('toMaint')}</button><button data-m="maintenance-stay">${t('toMaintStay')}</button>`:`<button class="pri" data-m="production">${t('toProd')}</button>`}</div>`}
 renderJob(s.job)}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button[data-a],button[data-m]');if(!b)return;
 if(b.dataset.m){post('/api/mode',{do:b.dataset.m});return}
 const a=b.dataset.a,f=b.dataset.f;
 if(a==='start'||a==='stop'||a==='restart')post('/api/game',{do:a});
 else if(a==='activate')post('/api/activate',{folder:f});
 else if(a==='delete'){if(confirm(t('confirmDel')))post('/api/delete',{folder:f})}
 else if(a==='settings')openSettings(f,b.dataset.n)});
async function openSettings(folder,name){
 const d=$('#dlg');$('#dlgTitle').textContent=name+' · '+t('settings');$('#dlgBody').innerHTML='…';$('#dlgFoot').innerHTML=`<button id="dCancel">${t('cancel')}</button><button class="pri" id="dSave">${t('saveSettings')}</button>`;d.showModal();
 const j=await (await fetch('/api/settings/'+encodeURIComponent(folder))).json();$('#dlgBody').innerHTML='<form id="sForm">'+(j.html||esc(j.error||''))+'</form>';
 $('#dCancel').onclick=()=>d.close();$('#dSave').onclick=async()=>{const r=await post('/api/settings/'+encodeURIComponent(folder),Object.fromEntries(new FormData($('#sForm'))));if(r.ok)d.close()}}
$('#dlgClose').onclick=()=>$('#dlg').close();
// uploads: 4 MB chunks, resumed after a cut
function pick(drop,input){const take=f=>{input._f=f;drop.querySelector('b').textContent=f.name;input._go(f)};drop.onclick=()=>input.click();['dragenter','dragover'].forEach(v=>drop.addEventListener(v,e=>{e.preventDefault();drop.classList.add('over')}));
 ['dragleave','drop'].forEach(v=>drop.addEventListener(v,e=>{e.preventDefault();drop.classList.remove('over')}));drop.addEventListener('drop',e=>{if(e.dataTransfer.files[0])take(e.dataTransfer.files[0])});input.onchange=()=>{if(input.files[0])take(input.files[0])}}
async function upload(kind,f,extra){
 const sf=$('#fSha').files[0];let sha='';if(kind==='game'&&sf){sha=(await sf.text()).trim().split(/\s+/)[0]}
 const base='/upload/'+kind+'?total='+f.size+'&name='+encodeURIComponent(f.name)+'&sha='+sha+(extra||''),C=4*1048576;let off=0,tries=0;const box=$('#jobBox');box.classList.remove('hide');
 while(off<f.size){const end=Math.min(off+C,f.size);
  try{const ac=new AbortController(),to=setTimeout(()=>ac.abort(),20000);const r=await fetch(base+'&offset='+off,{method:'POST',body:f.slice(off,end),signal:ac.signal});clearTimeout(to);const tx=await r.text();
   if(r.status==409&&/^\d+$/.test(tx)){off=+tx;continue}if(r.status>=400){toast(tx,true);poll();return}
   off=end;tries=0;setJob(t('uploading')+' '+f.name,Math.round(off*100/f.size),'run','acc')}
  catch(e){if(++tries>40){toast('Upload failed: connection lost',true);return}await new Promise(r=>setTimeout(r,3000));try{off=+(await (await fetch('/upload/size/'+kind)).text())}catch(e2){}}}
 poll()}
function setJob(msg,pct,cls,badge){$('#jobBox').classList.remove('hide');$('#jobMsg').textContent=msg;const b=$('#jobBar');b.className='bar mt '+(cls||'');b.firstElementChild.style.width=(pct==null?100:pct)+'%'}
function renderJob(j){if(!j||j.state==='idle')return;const bd=$('#jobBadge');bd.className='badge '+(j.state==='done'?'ok':j.state==='error'?'bad':'acc');bd.textContent=t(j.state==='running'?'installing':j.state==='uploading'?'uploading':j.state);
 setJob(j.msg,j.state==='running'?null:100,j.state==='running'?'run':'');const l=$('#jobLog');if(j.log){l.textContent=j.log;l.classList.remove('hide')}}
let pt;async function poll(){clearTimeout(pt);try{const j=await (await fetch('/job')).json();renderJob(j);if(j.state==='running'||j.state==='uploading')pt=setTimeout(poll,2000);else if(j.state==='done'){refresh()}}catch(e){pt=setTimeout(poll,3000)}}
// choosing or dropping a file only selects it: the hash file can still be added, and nothing is sent until the button
$('#fGame')._go=f=>{$('#goGame').disabled=false};$('#fPup')._go=f=>{$('#goPup').disabled=false};
pick($('#dropGame'),$('#fGame'));pick($('#dropPup'),$('#fPup'));
function resetPick(drop,input,btn,key){input._f=null;input.value='';drop.querySelector('b').textContent=t(key);btn.disabled=true}
$('#goGame').onclick=async()=>{const f=$('#fGame')._f;if(!f)return;$('#goGame').disabled=true;await upload('game',f,'&keep='+($('#keepOld').checked?1:0));$('#fSha').value='';resetPick($('#dropGame'),$('#fGame'),$('#goGame'),'dropGame')};
$('#goPup').onclick=async()=>{const f=$('#fPup')._f;if(!f)return;$('#goPup').disabled=true;await upload('pup',f,'');resetPick($('#dropPup'),$('#fPup'),$('#goPup'),'dropPup')};
let packBusy=false;
function packs(s){const lib=s.pups||[],gs=s.games.filter(g=>g.pup.supported);
 $('#packList').innerHTML=lib.map(p=>`<div class="net"><b class="grow">${esc(p.name)}</b><span class="muted">${fmtB(p.size)}</span><button data-pdel="${esc(p.name)}" title="${t('del')}">${ico('trash')}</button></div>`).join('');
 $('#packNone').textContent=lib.length?'':t('packNone');
 if(packBusy||document.activeElement&&document.activeElement.closest&&document.activeElement.closest('#packGrid'))return;
 $('#packGrid').innerHTML=gs.map(g=>`<div class="net"><b class="grow">${esc(g.name)} ${esc(g.version)}</b><select data-pg="${esc(g.folder)}"><option value="">${t('noPack')}</option>${lib.map(p=>`<option value="${esc(p.name)}"${g.pup.assigned===p.name?' selected':''}>${esc(p.name)}</option>`).join('')}${g.pup.installed&&!g.pup.assigned?`<option value="" selected hidden>${t('ownPack')}</option>`:''}</select></div>`).join('')||'<span class="muted">—</span>'}
$('#packGrid').onchange=async e=>{const sel=e.target.closest('select[data-pg]');if(!sel)return;sel.blur();packBusy=true;const r=sel.value?await post('/api/pup/assign',{folder:sel.dataset.pg,pack:sel.value}):await post('/api/pup/unassign',{folder:sel.dataset.pg});packBusy=false;poll()};
$('#packList').onclick=async e=>{const b=e.target.closest('button[data-pdel]');if(!b)return;if(!confirm(t('confirmDelPack')))return;await post('/api/pup/delete',{pack:b.dataset.pdel});poll()};
// network
async function scan(){const b=$('#scanBtn');b.disabled=true;$('#nets').innerHTML='<span class="muted">…</span>';
 try{const n=await (await fetch('/api/scan')).json();$('#nets').innerHTML=n.map(x=>`<div class="net" data-s="${esc(x.ssid)}">${sig(x.signal)}<b class="grow">${esc(x.ssid)}</b><span class="muted">${x.secure?ico('lock'):t('openNet')}</span></div>`).join('')||'<span class="muted">—</span>'}catch(e){$('#nets').innerHTML=''}b.disabled=false}
$('#scanBtn').onclick=scan;$('#nets').onclick=e=>{const n=e.target.closest('.net');if(n){$('#ssid').value=n.dataset.s;document.querySelector('#wifiForm [name=psk]').focus()}};
$('#wifiForm').onsubmit=e=>{e.preventDefault();post('/api/wifi',Object.fromEntries(new FormData(e.target)))};
$('#sshForm').onsubmit=e=>{e.preventDefault();post('/api/ssh',Object.fromEntries(new FormData(e.target)))};
let logT=null;$('#dlg').addEventListener('close',()=>clearInterval(logT));
$('#logsBtn').onclick=()=>{const d=$('#dlg');$('#dlgTitle').textContent=t('logs');$('#dlgBody').innerHTML='<pre id="logView" style="max-height:60vh">…</pre>';$('#dlgFoot').innerHTML='';d.showModal();
 const load=async()=>{const p=$('#logView');if(!p||!d.open)return;try{const r=await (await fetch('/api/logs')).text();const end=p.scrollTop+p.clientHeight>=p.scrollHeight-30;if(p.textContent!==r){p.textContent=r;if(end||p.textContent==='…')p.scrollTop=p.scrollHeight}}catch(e){}};
 load();clearInterval(logT);logT=setInterval(load,3000)};
let otaDirty=false,otaFilled=false;
function otaFill(o){if(!o)return;if(!otaDirty&&(!otaFilled||!$('#otaForm').contains(document.activeElement))){$('#otaUrl').value=o.url||'';$('#otaFolder').value=o.folder==null?'MPF Games':o.folder;$('#otaUser').value=o.user||'';otaFilled=true}$('#otaPw').placeholder=o.has_password?t('otaPwKept'):''}
$('#otaForm').addEventListener('input',()=>{otaDirty=true});
$('#otaForm').onsubmit=async e=>{e.preventDefault();const r=await post('/api/ota/config',Object.fromEntries(new FormData(e.target)));if(r&&r.ok)otaDirty=false};
$('#otaCheck').onclick=async()=>{const b=$('#otaCheck');b.disabled=true;$('#otaList').innerHTML='<span class="muted">…</span>';
 try{const r=await fetch('/api/ota/list');const j=await r.json();if(!r.ok){toast(j.msg||'?',true);$('#otaList').innerHTML='';b.disabled=false;return}
 $('#otaList').innerHTML=j.map(i=>`<div class="net"><b class="grow">${esc(i.version?i.label+' '+i.version:(i.group?i.group+' / ':'')+i.name)}</b>${i.kind==='game'&&!(i.version&&i.installed&&!i.update)?`<span class="badge">${i.for?t('otaUpdates')+' '+esc(i.for):t('otaNew')}</span>`:''}<span class="muted">${i.kind==='game'?t('otaGame'):t('otaPack')} · ${fmtB(i.size)}</span>${i.changed?`<span class="badge">${t('otaChanged')}</span>`:i.installed?`<span class="badge">${t('otaDone')}</span>`:''}${i.compatible?`<button data-k="${esc(i.key)}">${t('otaInstall')}</button>`:''}</div>`).join('')||'<span class="muted">'+t('otaNone')+'</span>'}catch(e){toast('?',true)}b.disabled=false};
$('#otaList').onclick=async e=>{const b=e.target.closest('button[data-k]');if(!b)return;b.disabled=true;await post('/api/ota/install',{key:b.dataset.k});poll()};
async function refresh(){try{S=await (await fetch('/api/state')).json();render(S);packs(S);otaFill(S.ota)}catch(e){}}
const TABS=['games','install','config','monitor'];let TAB=(location.hash||'').slice(1);if(!TABS.includes(TAB))TAB='games';
function showTab(){if(TAB==='monitor')monStart();else monStop();document.querySelectorAll('[data-tab]').forEach(e=>e.classList.toggle('hide',e.dataset.tab!==TAB));document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.go===TAB))}
$('#tabs').onclick=e=>{const b=e.target.closest('button[data-go]');if(!b)return;TAB=b.dataset.go;history.replaceState(null,'','#'+TAB);showTab();if(TAB==='config')savedList()};
async function savedList(){try{const l=await (await fetch('/api/logs/saved')).json();$('#savedLogs').innerHTML=l.map(n=>`<a class="net" href="/api/logs/saved/${encodeURIComponent(n)}" download>${ico('disk')}<b class="grow">${esc(n)}</b></a>`).join('')}catch(e){}}
$('#saveLogBtn').onclick=async()=>{const b=$('#saveLogBtn');b.disabled=true;await post('/api/logs/save',{});b.disabled=false;savedList()};
let monT=null,monSince=0,monLast='',monLog=[],monLay=null,monRev=0,monEpoch=0,monSw={},monOrder=[],monDev={},monBusy=false,monQ=Promise.resolve();
const monPref=(()=>{try{return JSON.parse(localStorage.getItem('mpfMon')||'{}')}catch(e){return{}}})();
function monSave(){try{localStorage.setItem('mpfMon',JSON.stringify(monPref))}catch(e){}}
function monApply(){const z=monPref.z||1,k=monPref.k||1.8,w=$('#pfw');w.style.setProperty('--z',z);w.style.setProperty('--k',k);$('#monZ').value=z;$('#monK').value=k}
function monMerge(j){if(j.full){monSw={};monOrder=[];monDev={}}
 j.switches.forEach(x=>{if(!(x.name in monSw))monOrder.push(x.name);monSw[x.name]=x});
 Object.entries(j.devices||{}).forEach(([k,v])=>{monDev[k]=Object.assign(monDev[k]||{},v)});
 monRev=j.rev;monEpoch=j.epoch;
 return {connected:j.connected,error:j.error,log:j.log,switches:monOrder.map(n=>monSw[n]),devices:monDev}}
function monDraw(j){const b=$('#monBadge');b.className='badge '+(j.connected?'ok':'bad');b.textContent=j.connected?t('monConn'):t('monDisc');
 $('#monCount').textContent=j.error||(j.switches.filter(x=>x.state).length+' / '+j.switches.length);
 if(monLay&&!$('#monPf').classList.contains('hide'))monPf(j);
 else if(!$('#monGrid').classList.contains('hide')){const f=$('#monFilter').value.toLowerCase(),sw=j.switches.filter(x=>!f||(x.name+' '+x.label).toLowerCase().includes(f));
  const key=sw.map(x=>x.name).join();
  if(key!==monLast){monLast=key;$('#monGrid').innerHTML=sw.map(x=>`<button class="sw" data-n="${esc(x.name)}" title="${esc(x.board+' '+x.number+' '+x.label)}">${esc(x.name)}<small>${esc(x.number)}</small></button>`).join('')||`<span class="muted">${t('monNone')}</span>`}
  const st={};sw.forEach(x=>st[x.name]=x.state);$('#monGrid').querySelectorAll('button[data-n]').forEach(e=>e.classList.toggle('on',!!st[e.dataset.n]))}
 if(j.log.length){monLog=monLog.concat(j.log).slice(-100);monSince=j.log[j.log.length-1][0];
  $('#monLogBox').textContent=monLog.slice().reverse().map(e=>new Date(e[0]*1000).toTimeString().slice(0,8)+' '+e[1]+' '+(e[2]?t('monOn'):t('monOff'))).join('\n')}}
function monPf(j){const f=$('#monFilter').value.toLowerCase(),sw={};j.switches.forEach(x=>sw[x.name]=x);const dv=j.devices||{};
 document.querySelectorAll('#pfw .sp').forEach(e=>{const k=e.dataset.k,n=e.dataset.n;let on=false,v;
  if(k==='switch'){on=sw[n]&&sw[n].state}else if(k==='light'){v=(dv.light||{})[n];on=!!v;e.style.background=v||'';e.style.color=v||'';e.classList.toggle('lit',on)}
  else if(k==='ball_device'){v=(dv.ball_device||{})[n]||0;on=v>0;e.textContent=v||''}else if(dv[k]&&n in dv[k]){on=!!dv[k][n]}
  e.classList.toggle('on',!!on);e.classList.toggle('dim',!!f&&!n.toLowerCase().includes(f))})}
async function monLayout(){monLay=null;try{const l=await (await fetch('/api/monitor/layout')).json();if(l&&l.image)monLay=l}catch(e){}
 const w=$('#pfw');w.querySelectorAll('.sp').forEach(e=>e.remove());$('#monView').classList.toggle('hide',!monLay);$('#monZoomBox').classList.toggle('hide',!monLay);
 if(!monLay){monView();return}
 $('#pfImg').src=monLay.image;const order=['coil','light','autofire','flipper','diverter','drop_target','ball_device','switch'];
 order.forEach(k=>Object.entries(monLay.spots[k]||{}).forEach(([n,d])=>{const e=document.createElement('div');e.className='sp '+k;e.dataset.k=k;e.dataset.n=n;e.title=k+' '+n;
  e.style.cssText=`left:${d.x*100}%;top:${d.y*100}%;width:calc(var(--k,1.8) * ${(d.size||monLay.size)*100}%)`;
  if(d.rotation){e.style.transform=`translate(-50%,-50%) rotate(${d.rotation}deg)`;e.style.aspectRatio='3/1';e.style.borderRadius='6px'}w.appendChild(e)}));
 monApply();$('#monView').value='pf';monView()}
function monView(){const pf=monLay&&$('#monView').value==='pf';$('#monPf').classList.toggle('hide',!pf);$('#monGrid').classList.toggle('hide',!!pf);monLast=''}
async function monPoll(){if(monBusy)return;monBusy=true;try{monDraw(monMerge(await (await fetch(`/api/monitor?since=${monSince}&rev=${monRev}&epoch=${monEpoch}`)).json()))}catch(e){}monBusy=false}
async function monStart(){if(monT)return;monT=setInterval(monPoll,100);monSince=0;monLog=[];monLast='';monRev=0;await monLayout();monPoll()}
function monStop(){clearInterval(monT);monT=null}
$('#monView').onchange=monView;$('#monBtn').onclick=()=>$('#tabs button[data-go=monitor]').click();$('#monFilter').oninput=monPoll;
$('#monZ').oninput=e=>{monPref.z=+e.target.value;monSave();monApply()};$('#monK').oninput=e=>{monPref.k=+e.target.value;monSave();monApply()};$('#monFit').onclick=()=>{monPref.z=1;monSave();monApply()};
$('#monPf').addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();monPref.z=Math.min(4,Math.max(.5,Math.round(((monPref.z||1)*(e.deltaY<0?1.1:1/1.1))*10)/10));monSave();monApply()},{passive:false});
function monSend(n,d){monQ=monQ.then(()=>fetch('/api/monitor/switch',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({name:n,do:d})}).then(r=>r.json()).then(j=>{if(!j.ok)toast(j.msg||'?',true)}).catch(()=>{}))}
function monBind(root,sel){root.addEventListener('pointerdown',e=>{const b=e.target.closest(sel);if(!b||e.button!==0)return;e.preventDefault();try{b.setPointerCapture(e.pointerId)}catch(x){}b.dataset.held='1';monSend(b.dataset.n,'on')});
 const up=e=>{const b=e.target.closest(sel);if(!b||!b.dataset.held)return;delete b.dataset.held;monSend(b.dataset.n,'off')};
 root.addEventListener('pointerup',up);root.addEventListener('pointercancel',up);
 root.addEventListener('contextmenu',e=>{const b=e.target.closest(sel);if(!b)return;e.preventDefault();monSend(b.dataset.n,'toggle')})}
const fsOff=()=>{$('#monCard').classList.remove('fsx')};
$('#monFull').onclick=()=>{const c=$('#monCard'),on=!c.classList.contains('fsx');c.classList.toggle('fsx',on);
 try{if(on&&c.requestFullscreen)c.requestFullscreen().catch(()=>{});else if(!on&&document.fullscreenElement)document.exitFullscreen()}catch(e){}};
document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement)fsOff()});
document.addEventListener('keydown',e=>{if(e.key==='Escape')fsOff()});
monBind($('#pfw'),'.sp.switch');monBind($('#monGrid'),'button[data-n]');monApply();
applyLang();showTab();if(TAB==="config")savedList();refresh();poll();setInterval(refresh,4000);
</script></body></html>
"""
