#!/usr/bin/env python3
"""Network setup for the MPF images: Wi-Fi, SSH keys and a tiny web page, standard library only.

  mpf_netconfig.py apply   read the text file, configure Wi-Fi/SSH, erase the Wi-Fi password from the file
  mpf_netconfig.py web     serve the setup page on port 8080 (HTTP basic auth)
  mpf_netconfig.py ap      if there is no network after a delay, start the "MPF-Setup" access point

Settings (environment, defaults for the Raspberry Pi image):
  MPF_NETCONFIG_FILE  /boot/firmware/mpf-network.txt
  MPF_USER            pi      user whose authorized_keys is edited and whose password protects the page
  MPF_WLAN            wlan0
  MPF_WEB_PORT        8080
  MPF_GAMES_DIR       /opt/games          where an uploaded game bundle is installed (<dir>/<bundle id>)
  MPF_UPLOAD_DIR      /var/lib/mpf-uploads  uploads are written here, then unpacked
  MPF_GAME_ENV        /etc/default/mpf-game  KEY=VALUE lines for the game (GODOT, TRON_VENV, DISPLAY, MPF_GAME_ARGS)
  MPF_GOZEN_SO        a GoZen library built for this board, copied over the bundle's own (optional)
Must run as root.
"""
import hashlib, html, json, os, platform, pwd, re, subprocess, sys, threading, time, base64, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote as requests_unquote

CONF = os.environ.get("MPF_NETCONFIG_FILE", "/boot/firmware/mpf-network.txt")
USER = os.environ.get("MPF_USER", "pi")
WLAN = os.environ.get("MPF_WLAN", "wlan0")
PORT = int(os.environ.get("MPF_WEB_PORT", "8080"))
WPA = f"/etc/wpa_supplicant/wpa_supplicant-{WLAN}.conf"
SSHD_DROPIN = "/etc/ssh/sshd_config.d/10-mpf-netconfig.conf"
GAMES = os.environ.get("MPF_GAMES_DIR", "/opt/games")
UPLOADS = os.environ.get("MPF_UPLOAD_DIR", "/var/lib/mpf-uploads")
GAME_ENV = os.environ.get("MPF_GAME_ENV", "/etc/default/mpf-game")
GOZEN_SO = os.environ.get("MPF_GOZEN_SO", "")
AP_SSID, AP_PSK, AP_ADDR = "MPF-Setup", os.environ.get("MPF_AP_PSK", "mpf-setup"), "192.168.4.1"


def run(*cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def read_conf(path=CONF):
    out = {}
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return out


def blank_key(path, key):
    """Erase the value of one key in the text file, keeping everything else."""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
        lines = [f"{key}=" if re.match(rf"\s*{key}\s*=", l) else l for l in lines]
        open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    except OSError as e:
        print(f"cannot rewrite {path}: {e}", file=sys.stderr)


def psk(ssid, passphrase):
    return hashlib.pbkdf2_hmac("sha1", passphrase.encode(), ssid.encode(), 4096, 32).hex()


def set_country(cc):
    text = open(WPA).read() if os.path.exists(WPA) else "ctrl_interface=DIR=/run/wpa_supplicant GROUP=sudo\nupdate_config=1\n"
    text = re.sub(r"^country=.*\n", "", text, flags=re.M)
    open(WPA, "w").write(text.rstrip("\n") + (f"\ncountry={cc}\n" if cc else "\n"))
    os.chmod(WPA, 0o600)


def add_wifi(ssid, passphrase, country=""):
    if not (1 <= len(ssid) <= 32) or not (8 <= len(passphrase) <= 63 or len(passphrase) == 0):
        raise ValueError("SSID 1-32 characters, WPA password 8-63 characters (empty for an open network)")
    if any(c in ssid for c in '"\n\r'):
        raise ValueError("unsupported character in SSID")
    if country:
        set_country(country)
    text = open(WPA).read() if os.path.exists(WPA) else "ctrl_interface=DIR=/run/wpa_supplicant GROUP=sudo\nupdate_config=1\n"
    # replace a previous block for the same SSID
    text = re.sub(r'\nnetwork=\{\n\tssid="%s"\n[^}]*\}\n' % re.escape(ssid), "\n", text)
    key = f"\tpsk={psk(ssid, passphrase)}\n" if passphrase else "\tkey_mgmt=NONE\n"
    text = text.rstrip("\n") + f'\n\nnetwork={{\n\tssid="{ssid}"\n{key}}}\n'
    os.makedirs(os.path.dirname(WPA), exist_ok=True)
    open(WPA, "w").write(text)
    os.chmod(WPA, 0o600)
    wifi_up()
    run("systemctl", "restart", f"wpa_supplicant@{WLAN}.service")


def add_ssh_key(key):
    if not re.match(r"^(ssh-(ed25519|rsa)|ecdsa-sha2-\S+|sk-\S+) \S+( .*)?$", key) or "\n" in key:
        raise ValueError("not a valid single-line SSH public key")
    pw = pwd.getpwnam(USER)
    d = os.path.join(pw.pw_dir, ".ssh")
    os.makedirs(d, mode=0o700, exist_ok=True)
    f = os.path.join(d, "authorized_keys")
    have = open(f).read().splitlines() if os.path.exists(f) else []
    if key not in have:
        open(f, "a").write(key + "\n")
    os.chmod(f, 0o600)
    for p in (d, f):
        os.chown(p, pw.pw_uid, pw.pw_gid)


def set_ssh_password_login(on):
    os.makedirs(os.path.dirname(SSHD_DROPIN), exist_ok=True)
    open(SSHD_DROPIN, "w").write(f"PasswordAuthentication {'yes' if on else 'no'}\n")
    run("systemctl", "reload", "ssh.service")


def apply_file():
    c = read_conf()
    if c.get("SSH_AUTHORIZED_KEY"):
        try:
            add_ssh_key(c["SSH_AUTHORIZED_KEY"])
        except ValueError as e:
            print("SSH_AUTHORIZED_KEY ignored:", e, file=sys.stderr)
    if c.get("SSH_PASSWORD_LOGIN", "").lower() in ("yes", "no"):
        set_ssh_password_login(c["SSH_PASSWORD_LOGIN"].lower() == "yes")
    if c.get("WIFI_SSID"):
        try:
            add_wifi(c["WIFI_SSID"], c.get("WIFI_PSK", ""), c.get("WIFI_COUNTRY", ""))
            blank_key(CONF, "WIFI_PSK")
        except ValueError as e:
            print("Wi-Fi settings ignored:", e, file=sys.stderr)
    elif c.get("WIFI_COUNTRY"):
        set_country(c["WIFI_COUNTRY"])


def web_password():
    return read_conf().get("WEB_PASSWORD") or None


def check_user_password(password):
    """Compare with the user's /etc/shadow hash using openssl (crypt is gone from Python 3.13)."""
    try:
        for line in open("/etc/shadow"):
            f = line.split(":")
            if f[0] == USER and f[1].startswith("$"):
                _, algo, salt, _h = f[1].split("$", 3)
                flag = {"6": "-6", "5": "-5", "1": "-1"}.get(algo)
                if not flag:
                    return False
                r = run("openssl", "passwd", flag, "-salt", salt, "-stdin", input=password)
                return r.stdout.strip() == f[1]
    except OSError:
        pass
    return False


def authorized(header):
    if not header or not header.startswith("Basic "):
        return False
    try:
        _, _, pw = base64.b64decode(header[6:]).decode().partition(":")
    except Exception:
        return False
    fixed = web_password()
    return pw == fixed if fixed else check_user_password(pw)


def wifi_up():
    """Make the radio usable even when the board is on Ethernet (the Pi keeps Wi-Fi blocked until a country is set)."""
    run("rfkill", "unblock", "wifi")
    run("ip", "link", "set", WLAN, "up")


def scan():
    wifi_up()
    r = run("iw", "dev", WLAN, "scan")
    names = sorted({m for m in re.findall(r"SSID: (.+)", r.stdout) if m.strip()})
    return names


def status():
    return run("ip", "-br", "addr").stdout + "\n" + run("iw", "dev", WLAN, "link").stdout


# ---------------------------------------------------------------- game bundle and PuP Pack (docs/bundle.md of the game)
JOB = {"state": "idle", "msg": "", "log": ""}      # one install at a time; the page polls /job
JOB_LOCK = threading.Lock()
ARCH = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "x86_64", "amd64": "x86_64"}


class JobError(Exception):
    pass


def job_set(**kw):
    JOB.update(kw)


def job_log(text):
    JOB["log"] = (JOB["log"] + text.rstrip("\n") + "\n")[-6000:]


def sh(*cmd, cwd=None, user=False):
    """Run a command for the job, log its output, fail the job when it fails."""
    if user:
        cmd = ("runuser", "-u", USER, "--") + cmd
    job_log("$ " + " ".join(cmd))
    r = run(*cmd, cwd=cwd)
    job_log((r.stdout + r.stderr)[-2000:])
    if r.returncode:
        raise JobError(f"{cmd[0]} failed ({r.returncode})")
    return r


def game_env():
    out = {}
    try:
        for line in open(GAME_ENV, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return out


def installed_game():
    """Folder of the installed bundle, or None (the first folder of GAMES that holds a bundle.json)."""
    try:
        for n in sorted(os.listdir(GAMES)):
            if not n.startswith(".") and os.path.isfile(os.path.join(GAMES, n, "bundle.json")):
                return os.path.join(GAMES, n)
    except OSError:
        pass
    return None


def game_python():
    venv = game_env().get("TRON_VENV")
    py = os.path.join(venv, "bin", "python") if venv else ""
    return py if py and os.path.exists(py) else "python3"


def tool(game, *args):
    """Run the bundle's own settings tool as the game user; returns the CompletedProcess."""
    return run("runuser", "-u", USER, "--", game_python(), os.path.join(game, "scripts/package/bundle_options.py"), *args, cwd=game)


def free_gb(path):
    os.makedirs(path, exist_ok=True)
    return shutil.disk_usage(path).free / 1e9


def install_game(archive, expect_sha):
    job_set(state="running", msg="Checking the archive")
    h = hashlib.sha256()
    with open(archive, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if expect_sha and h.hexdigest() != expect_sha.lower():
        raise JobError("the archive's sha256 does not match the .sha256 file: upload it again")
    os.makedirs(GAMES, exist_ok=True)
    stage = os.path.join(GAMES, ".stage")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    job_set(msg="Unpacking (a few minutes)")
    sh("tar", "-xJf", archive, "-C", stage, "--no-same-owner")
    dirs = [d for d in os.listdir(stage) if os.path.isdir(os.path.join(stage, d))]
    if len(dirs) != 1 or not os.path.isfile(os.path.join(stage, dirs[0], "bundle.json")):
        raise JobError("not a game bundle: no bundle.json in the archive")
    root = os.path.join(stage, dirs[0])
    b = json.load(open(os.path.join(root, "bundle.json")))
    if b.get("format", 1) > 1:
        raise JobError(f"bundle format {b.get('format')} is newer than this page understands")
    tgt, me = b.get("target", {}), ARCH.get(platform.machine(), platform.machine())
    if tgt.get("os", "linux") != "linux" or tgt.get("arch") != me:
        raise JobError(f"this bundle is for {tgt.get('os')}/{tgt.get('arch')}, this machine is linux/{me}")
    job_log(f"bundle {b.get('name')} {b.get('version')}")
    job_set(msg="Verifying every file (sha256sum)")
    sh("sha256sum", "-c", "SHA256SUMS", "--quiet", cwd=root)
    dest = os.path.join(GAMES, b["id"])
    old = dest + ".old"
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(dest):
        job_set(msg="Keeping settings, scores and PuP Pack")
        for rel in b.get("keep_on_update", []):
            src, dst = os.path.join(dest, rel), os.path.join(root, rel)
            if os.path.exists(src):
                shutil.rmtree(dst, ignore_errors=True) if os.path.isdir(dst) else None
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(src, dst)
        os.rename(dest, old)
    os.rename(root, dest)
    shutil.rmtree(stage, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    if GOZEN_SO and os.path.isfile(GOZEN_SO):
        bindir = os.path.join(dest, "game/addons/gde_gozen/bin")
        for n in os.listdir(bindir) if os.path.isdir(bindir) else ():
            if re.match(r"libgozen\.linux\..*arm64\.so$", n):
                shutil.copy(GOZEN_SO, os.path.join(bindir, n))
                job_log(f"{n}: replaced by this board's GoZen")
    pw = pwd.getpwnam(USER)
    sh("chown", "-R", f"{pw.pw_uid}:{pw.pw_gid}", dest)
    os.remove(archive)
    job_set(state="done", msg=f"Game {b.get('version')} installed in {dest}")


def install_pup(zipfile):
    game = installed_game()
    if not game:
        raise JobError("install the game first")
    job_set(state="running", msg="Installing the PuP Pack (videos are checked, a few minutes)")
    b = json.load(open(os.path.join(game, "bundle.json")))
    cmd = b.get("pup", {}).get("install", "python3 scripts/pup/pup_setup.py --pup-zip ZIP_PATH_OR_URL")
    args = [zipfile if a == "ZIP_PATH_OR_URL" else a for a in cmd.split()]
    if args[0] == "python3":
        args[0] = game_python()
    env = ["env"] + [f"{k}={v}" for k, v in game_env().items()]
    sh(*env, *args, cwd=game, user=True)
    os.remove(zipfile)
    job_set(state="done", msg="PuP Pack installed" + (" (restart the game)" if b.get("pup", {}).get("needs_restart") else ""))


def run_job(fn, *args):
    try:
        fn(*args)
    except JobError as e:
        job_set(state="error", msg=str(e))
    except Exception as e:   # keep the page alive whatever happens
        job_set(state="error", msg=f"{type(e).__name__}: {e}")
    finally:
        JOB_LOCK.release()


def game_running():
    return run("systemctl", "is-active", "--quiet", "mpf-game.service").returncode == 0


def game_start():
    game = installed_game()
    if not game:
        raise ValueError("no game installed")
    env = game_env()
    pw = pwd.getpwnam(USER)
    args = env.get("MPF_GAME_ARGS", "").split()
    props = ["-p", f"User={USER}", "-p", f"WorkingDirectory={game}", "-E", f"DISPLAY={env.get('DISPLAY', ':0')}",
             "-E", f"XAUTHORITY={env.get('XAUTHORITY', os.path.join(pw.pw_dir, '.Xauthority'))}"]
    for k in ("GODOT", "TRON_VENV"):
        if env.get(k):
            props += ["-E", f"{k}={env[k]}"]
    r = run("systemd-run", "--unit=mpf-game", "--collect", *props, game_python(), "scripts/package/start.py", *args)
    if r.returncode:
        raise ValueError((r.stderr or r.stdout).strip() or "could not start the game")


def game_stop():
    run("systemctl", "stop", "mpf-game.service")


def settings_html(game):
    try:
        schema = json.load(open(os.path.join(game, "scripts/package/options.json")))
        cur = json.loads(tool(game, "get").stdout or "{}")
    except (OSError, ValueError):
        return "<p>Settings unavailable.</p>"
    out = ["<form method=post action=/settings>"]
    for g in schema["groups"]:
        out.append(f"<h3>{html.escape(g['label'])}</h3>")
        for o in (o for o in schema["options"] if o["group"] == g["id"]):
            name, v = "o." + o["id"], cur.get(o["id"])
            hint = f" (default {o['default']})" if "default" in o else ""
            if o["type"] == "bool":
                sel = {True: "true", False: "false"}.get(v, "")
                field = f"<select name='{name}'>" + "".join(
                    f"<option value='{x}'{' selected' if x == sel else ''}>{x or 'default'}" for x in ("", "true", "false")) + "</select>"
            elif o["type"] == "choice":
                field = f"<select name='{name}'><option value=''>default" + "".join(
                    f"<option{' selected' if c == v else ''}>{html.escape(c)}" for c in o["choices"]) + "</select>"
            elif o.get("secret"):
                field = f"<input name='{name}' type=password placeholder='{'set' if v else 'not set'} (empty: unchanged)'>"
            else:
                val = "" if v is None else html.escape(str(v), quote=True)
                field = f"<input name='{name}' value='{val}' size=14 placeholder='default'>"
            out.append(f"<div title='{html.escape(o.get('help', ''), quote=True)}'>{html.escape(o['label'])}{hint}: {field}"
                       f" {html.escape(o.get('unit', ''))}</div>")
    out.append("<button>Save settings</button> (restart the game to apply)</form>")
    return "".join(out)


def settings_save(game, form):
    schema = json.load(open(os.path.join(game, "scripts/package/options.json")))
    cur = json.loads(tool(game, "get").stdout or "{}")
    sets, unsets = [], []
    for o in schema["options"]:
        v = form.get("o." + o["id"], "").strip()
        if v:
            sets += [o["id"], v]
        elif o["id"] in cur and not o.get("secret"):
            unsets.append(o["id"])
    if sets:
        r = tool(game, "set", *sets)
        if r.returncode:
            raise ValueError((r.stderr or r.stdout).strip()[-300:])
    if unsets:
        tool(game, "unset", *unsets)


GAME_PAGE = """<h2>Game</h2><p>%(state)s</p>
<form onsubmit="return up(this,'game')">Bundle <code>*-linux-%(arch)s.tar.xz</code> <input type=file name=f required><br>
its <code>.sha256</code> file (optional) <input type=file name=s><br><button>Upload and install</button></form>
<h2>PuP Pack</h2><form onsubmit="return up(this,'pup')">Pack <code>.zip</code> <input type=file name=f accept=.zip required>
<br><button>Upload and install</button></form>
<p id=job><b></b></p><pre id=log></pre>
%(ctl)s
<script>
async function up(form,kind){
 const f=form.f.files[0], s=form.s&&form.s.files[0]; let sha='';
 if(s){sha=(await s.text()).trim().split(/\\s+/)[0];}
 const x=new XMLHttpRequest(); x.open('POST','/upload/'+kind);
 x.setRequestHeader('X-Filename',encodeURIComponent(f.name)); x.setRequestHeader('X-Sha256',sha);
 x.upload.onprogress=e=>{document.querySelector('#job b').textContent='Uploading '+Math.round(e.loaded/1048576)+' / '+Math.round(e.total/1048576)+' MB'};
 x.onload=()=>{if(x.status!=202)document.querySelector('#job b').textContent='Error: '+x.responseText;poll();};
 x.onerror=()=>{document.querySelector('#job b').textContent='Upload interrupted'};
 x.send(f); return false;}
async function poll(){
 const j=await (await fetch('/job')).json(); const b=document.querySelector('#job b');
 if(j.state!='idle'&&!(b.textContent.startsWith('Uploading')&&j.state=='idle')){b.textContent=j.msg;}
 document.getElementById('log').textContent=j.log;
 if(j.state=='running')setTimeout(poll,2000); else if(j.state=='done')setTimeout(()=>location.reload(),1500);}
poll();
</script>"""


PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>MPF setup</title><body style="font-family:sans-serif;max-width:34em;margin:1em auto;padding:0 1em">
<h1>MPF setup</h1>%(msg)s
%(game)s
<h2>Wi-Fi</h2><form method=post action=/wifi>
SSID <input name=ssid list=nets required><datalist id=nets>%(nets)s</datalist><br>
Password <input name=psk type=password><br>Country (FR, US...) <input name=country size=3 maxlength=2><br>
<button>Save and connect</button></form>
<h2>SSH</h2><form method=post action=/ssh>
Public key <input name=key size=40><br>
Password login <select name=pwlogin><option value="">unchanged<option>yes<option>no</select><br>
<button>Save</button></form>
<h2>Status</h2><pre>%(status)s</pre></body>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=()):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _auth(self):
        if authorized(self.headers.get("Authorization")):
            return True
        self._send(401, "Authentication required", "text/plain", [("WWW-Authenticate", 'Basic realm="MPF setup"')])
        return False

    def _page(self, msg=""):
        nets = "".join(f"<option value='{html.escape(n, quote=True)}'>" for n in scan())
        game = installed_game()
        if game:
            b = json.load(open(os.path.join(game, "bundle.json")))
            state = f"Installed: <b>{html.escape(b.get('name', ''))} {html.escape(b.get('version', ''))}</b>, game "
            state += "<b>running</b>" if game_running() else "stopped"
            ctl = ("<form method=post action=/game style='display:inline'><button name=do value=%s>%s</button></form>"
                   % (("stop", "Stop the game") if game_running() else ("start", "Start the game")))
            ctl += "<h2>Game settings</h2>" + settings_html(game)
        else:
            state, ctl = "No game installed.", ""
        g = GAME_PAGE % {"state": state, "arch": ARCH.get(platform.machine(), platform.machine()), "ctl": ctl}
        self._send(200, PAGE % {"msg": f"<p><b>{html.escape(msg)}</b></p>" if msg else "", "nets": nets,
                                "status": html.escape(status()), "game": g})

    def _upload(self, kind):
        """Stream the request body to disk (never in memory), then unpack and install in a thread."""
        n = int(self.headers.get("Content-Length", 0))
        if not JOB_LOCK.acquire(blocking=False):
            return self._send(409, "an install is already running", "text/plain")
        try:
            name = os.path.basename(requests_unquote(self.headers.get("X-Filename", ""))) or kind
            ok = name.endswith(".tar.xz") if kind == "game" else name.lower().endswith(".zip")
            if not ok:
                raise ValueError("expected a .tar.xz bundle" if kind == "game" else "expected a .zip pack")
            if not n or free_gb(UPLOADS) * 1e9 < n * (4 if kind == "game" else 2) + 5e8:
                raise ValueError("not enough free disk space for this file")
            if kind == "game" and not name.endswith(f"linux-{ARCH.get(platform.machine(), platform.machine())}.tar.xz") \
                    and "linux-" in name:
                raise ValueError(f"this machine is {ARCH.get(platform.machine(), platform.machine())}: wrong bundle")
            if kind == "pup" and not installed_game():
                raise ValueError("install the game first")
            path = os.path.join(UPLOADS, "game.tar.xz" if kind == "game" else "pup.zip")
            JOB.update(state="uploading", msg="Receiving " + name, log="")
            with open(path, "wb") as f:
                left = n
                while left:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        raise ValueError("upload interrupted")
                    f.write(chunk)
                    left -= len(chunk)
        except (ValueError, OSError) as e:
            JOB_LOCK.release()
            job_set(state="error", msg=str(e))
            return self._send(400, str(e), "text/plain")
        fn, args = (install_game, (path, self.headers.get("X-Sha256", ""))) if kind == "game" else (install_pup, (path,))
        threading.Thread(target=run_job, args=(fn,) + args, daemon=True).start()
        self._send(202, "installing", "text/plain")

    def do_GET(self):
        if not self._auth():
            return
        if self.path == "/job":
            return self._send(200, json.dumps(JOB), "application/json")
        self._page()

    def do_POST(self):
        if not self._auth():
            return
        if self.path in ("/upload/game", "/upload/pup"):
            return self._upload(self.path.rsplit("/", 1)[1])
        n = int(self.headers.get("Content-Length", 0))
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(min(n, 262144)).decode()).items()}
        try:
            if self.path == "/wifi":
                add_wifi(form.get("ssid", ""), form.get("psk", ""), form.get("country", "").upper())
                msg = "Wi-Fi saved, connecting (the address may change)."
            elif self.path == "/ssh":
                if form.get("key"):
                    add_ssh_key(form["key"].strip())
                if form.get("pwlogin") in ("yes", "no"):
                    set_ssh_password_login(form["pwlogin"] == "yes")
                msg = "SSH settings saved."
            elif self.path == "/settings":
                settings_save(installed_game(), form)
                msg = "Game settings saved (restart the game to apply)."
            elif self.path == "/game":
                game_start() if form.get("do") == "start" else game_stop()
                msg = "Game " + ("starting." if form.get("do") == "start" else "stopped.")
            else:
                return self._send(404, "not found", "text/plain")
        except (ValueError, TypeError) as e:
            msg = f"Error: {e}"
        self._page(msg)

    def log_message(self, *a):
        pass


def have_network():
    r = run("ip", "-4", "-o", "addr", "show", "scope", "global")
    return bool(r.stdout.strip())


def access_point():
    time.sleep(int(os.environ.get("MPF_AP_DELAY", "90")))
    if have_network():
        return
    print("no network: starting access point", AP_SSID, file=sys.stderr)
    run("systemctl", "stop", f"wpa_supplicant@{WLAN}.service")
    run("ip", "addr", "flush", "dev", WLAN)
    run("ip", "addr", "add", f"{AP_ADDR}/24", "dev", WLAN)
    open("/run/mpf-hostapd.conf", "w").write(
        f"interface={WLAN}\nssid={AP_SSID}\nhw_mode=g\nchannel=6\nwpa=2\nwpa_key_mgmt=WPA-PSK\n"
        f"rsn_pairwise=CCMP\nwpa_passphrase={AP_PSK}\n")
    open("/run/mpf-dnsmasq.conf", "w").write(
        f"interface={WLAN}\nbind-interfaces\ndhcp-range=192.168.4.10,192.168.4.50,12h\naddress=/#/{AP_ADDR}\n")
    h = subprocess.Popen(["hostapd", "/run/mpf-hostapd.conf"])
    d = subprocess.Popen(["dnsmasq", "-k", "-C", "/run/mpf-dnsmasq.conf"])
    h.wait()
    d.terminate()


def main():
    if os.geteuid() != 0:
        sys.exit("run as root")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "apply":
        apply_file()
    elif cmd == "web":
        ThreadingHTTPServer(("", PORT), Handler).serve_forever()
    elif cmd == "ap":
        access_point()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
