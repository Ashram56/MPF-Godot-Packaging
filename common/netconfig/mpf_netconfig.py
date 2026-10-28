#!/usr/bin/env python3
"""Network setup for the MPF images: Wi-Fi, SSH keys, the access point; the setup page and the games are in mpf_web / mpf_games.

  mpf_netconfig.py apply   read the text file, configure Wi-Fi/SSH, erase the Wi-Fi password from the file
  mpf_netconfig.py web     serve the setup page on port 8080 (HTTP basic auth)
  mpf_netconfig.py game    run the active game (mpf-game.service: waits for X, runs the bundle's start command as MPF_USER)
  mpf_netconfig.py inbox   install the bundles and PuP Packs found in the inbox folder (mpf-netconfig-inbox.service, at boot)
  mpf_netconfig.py ap      if there is no network after a delay, start the "MPF-Setup" access point

The three modules are installed together in /usr/local/bin. Settings (environment, defaults for the Raspberry Pi image):
  MPF_NETCONFIG_FILE  /boot/firmware/mpf-network.txt
  MPF_USER            pi      user whose authorized_keys is edited, whose password protects the page and who runs the game
  MPF_WLAN            wlan0
  MPF_WEB_PORT        8080
  MPF_GAMES_DIR       /opt/games          where uploaded game bundles are installed (<dir>/<id>@<version>)
  MPF_UPLOAD_DIR      /var/lib/mpf-uploads  uploads are written here, then unpacked
  MPF_INBOX_DIR       /var/lib/mpf-inbox  bundles (*.tar.xz) and packs (*.zip) put here are installed at the next boot
  MPF_STATE_DIR       /var/lib/mpf-netconfig  which game is active
  MPF_GAME_ENV        /etc/default/mpf-game  KEY=VALUE lines for the game (GODOT, MPF_GAME_VENV, DISPLAY, MPF_GAME_ARGS)
  MPF_GOZEN_SO        a GoZen library built for this board, copied over the bundle's own (optional; not when
                      the bundle's build already has MPF_GOZEN_NEEDS, bundle.json "gozen")
  MPF_PLATFORM_DIR    this platform's checkout (its addons/gde_gozen is installed into a bundle that lists
                      "platform_addons" in bundle.json; default: found from this file or from MPF_GOZEN_SO)
  MPF_GOZEN_NEEDS     v4l2m2m zero_copy   what the bundle's GoZen must carry to be kept
  MPF_READONLY_CONF   /etc/mpf-readonly.conf  read-only production mode (common/readonly): when the file exists, the page
                      shows the mode (production/maintenance), uploads go to the data partition, the game's logs and
                      Godot's user folders go to RAM, and the few files outside the data partition are written in short
                      writable windows. MODE=maintenance|production in the text file switches it at boot.
Must run as root.
"""
import base64
import hashlib
import os
import pwd
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpf_common as C  # noqa: E402
from mpf_common import run, read_conf, set_mode, mode_status  # noqa: E402,F401

WPA = f"/etc/wpa_supplicant/wpa_supplicant-{C.WLAN}.conf"
SSHD_DROPIN = "/etc/ssh/sshd_config.d/10-mpf-netconfig.conf"
AP_SSID, AP_PSK, AP_ADDR = "MPF-Setup", os.environ.get("MPF_AP_PSK", "mpf-setup"), "192.168.4.1"


def blank_key(path, key):
    """Erase the value of one key in the text file, keeping everything else."""
    try:
        with C.writable(path):
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
    run("systemctl", "restart", f"wpa_supplicant@{C.WLAN}.service")


def add_ssh_key(key):
    if not re.match(r"^(ssh-(ed25519|rsa)|ecdsa-sha2-\S+|sk-\S+) \S+( .*)?$", key) or "\n" in key:
        raise ValueError("not a valid single-line SSH public key")
    pw = pwd.getpwnam(C.USER)
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
    # MODE=maintenance|production: the way back to a writable system when the page cannot be reached (the file is on the
    # FAT boot partition, editable from any computer). Used once: the key is emptied again.
    if C.READONLY and c.get("MODE", "").lower() in ("maintenance", "production"):
        try:
            set_mode(c["MODE"].lower(), stay=True)
        except ValueError as e:
            print("MODE ignored:", e, file=sys.stderr)
        blank_key(C.CONF, "MODE")
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
            blank_key(C.CONF, "WIFI_PSK")
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
            if f[0] == C.USER and f[1].startswith("$"):
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
    run("ip", "link", "set", C.WLAN, "up")


def scan():
    """[{ssid, signal (dBm), secure}] of the networks in range, strongest first, one entry per name."""
    wifi_up()
    out = run("iw", "dev", C.WLAN, "scan").stdout
    nets = {}
    for block in re.split(r"(?m)^BSS ", out)[1:]:
        m = re.search(r"SSID: (.+)", block)
        if not m or not m.group(1).strip() or "\\x00" in m.group(1):
            continue
        sig = re.search(r"signal: (-?[\d.]+)", block)
        sec = bool(re.search(r"RSN:|WPA:", block)) or "Privacy" in block
        n = {"ssid": m.group(1).strip(), "signal": float(sig.group(1)) if sig else -100.0, "secure": sec}
        if n["ssid"] not in nets or n["signal"] > nets[n["ssid"]]["signal"]:
            nets[n["ssid"]] = n
    return sorted(nets.values(), key=lambda n: -n["signal"])


def status():
    return run("ip", "-br", "addr").stdout + "\n" + run("iw", "dev", C.WLAN, "link").stdout


def network_info():
    """{addresses: [(interface, address)], wifi: {ssid, signal} or None} for the page's header."""
    addrs = []
    for line in run("ip", "-4", "-o", "addr", "show", "scope", "global").stdout.splitlines():
        f = line.split()
        if len(f) > 3:
            addrs.append((f[1], f[3].split("/")[0]))
    link = run("iw", "dev", C.WLAN, "link").stdout
    ssid = re.search(r"SSID: (.+)", link)
    sig = re.search(r"signal: (-?\d+)", link)
    wifi = {"ssid": ssid.group(1).strip(), "signal": int(sig.group(1)) if sig else None} if ssid else None
    return {"addresses": addrs, "wifi": wifi}


def have_network():
    r = run("ip", "-4", "-o", "addr", "show", "scope", "global")
    return bool(r.stdout.strip())


def access_point():
    time.sleep(int(os.environ.get("MPF_AP_DELAY", "90")))
    if have_network():
        return
    print("no network: starting access point", AP_SSID, file=sys.stderr)
    run("systemctl", "stop", f"wpa_supplicant@{C.WLAN}.service")
    run("ip", "addr", "flush", "dev", C.WLAN)
    run("ip", "addr", "add", f"{AP_ADDR}/24", "dev", C.WLAN)
    open("/run/mpf-hostapd.conf", "w").write(
        f"interface={C.WLAN}\nssid={AP_SSID}\nhw_mode=g\nchannel=6\nwpa=2\nwpa_key_mgmt=WPA-PSK\n"
        f"rsn_pairwise=CCMP\nwpa_passphrase={AP_PSK}\n")
    open("/run/mpf-dnsmasq.conf", "w").write(
        f"interface={C.WLAN}\nbind-interfaces\ndhcp-range=192.168.4.10,192.168.4.50,12h\naddress=/#/{AP_ADDR}\n")
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
        import mpf_web
        mpf_web.serve()
    elif cmd == "ap":
        access_point()
    elif cmd == "game":
        import mpf_games
        mpf_games.game_exec()
    elif cmd == "inbox":
        import mpf_games
        mpf_games.process_inbox()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
