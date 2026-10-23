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
Must run as root.
"""
import hashlib, html, os, pwd, re, subprocess, sys, time, base64, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

CONF = os.environ.get("MPF_NETCONFIG_FILE", "/boot/firmware/mpf-network.txt")
USER = os.environ.get("MPF_USER", "pi")
WLAN = os.environ.get("MPF_WLAN", "wlan0")
PORT = int(os.environ.get("MPF_WEB_PORT", "8080"))
WPA = f"/etc/wpa_supplicant/wpa_supplicant-{WLAN}.conf"
SSHD_DROPIN = "/etc/ssh/sshd_config.d/10-mpf-netconfig.conf"
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


def scan():
    r = run("iw", "dev", WLAN, "scan")
    names = sorted({m for m in re.findall(r"SSID: (.+)", r.stdout) if m.strip()})
    return names


def status():
    return run("ip", "-br", "addr").stdout + "\n" + run("iw", "dev", WLAN, "link").stdout


PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>MPF setup</title><body style="font-family:sans-serif;max-width:34em;margin:1em auto;padding:0 1em">
<h1>MPF setup</h1>%(msg)s
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
        self._send(200, PAGE % {"msg": f"<p><b>{html.escape(msg)}</b></p>" if msg else "", "nets": nets, "status": html.escape(status())})

    def do_GET(self):
        if self._auth():
            self._page()

    def do_POST(self):
        if not self._auth():
            return
        n = int(self.headers.get("Content-Length", 0))
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(min(n, 65536)).decode()).items()}
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
            else:
                return self._send(404, "not found", "text/plain")
        except ValueError as e:
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
