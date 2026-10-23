# netconfig: Wi-Fi, SSH and a setup page for the MPF images

Shared by the Raspberry Pi 4 and Jetson Xavier NX images. Standard library Python, no dependencies besides
`iw`, `openssl` (always there) and `hostapd` + `dnsmasq` (fallback access point only).

| File | Role |
|---|---|
| `mpf-network.txt.template` | Text file the user edits (SSID, password, country, SSH key). Lives where the image can be mounted from Windows/macOS: the FAT boot partition |
| `mpf_netconfig.py` | `apply` (read the file at boot; the Wi-Fi password is erased from it afterwards), `web` (setup page on port 8080), `ap` (access point `MPF-Setup`, password `mpf-setup`, page at http://192.168.4.1:8080 when no network came up in 90 s) |
| `mpf-netconfig-*.service` | systemd units for the three modes |

The page asks for the password of the image user (or `WEB_PASSWORD` from the file). Per-image settings go in
`/etc/default/mpf-netconfig`: `MPF_NETCONFIG_FILE`, `MPF_USER`, `MPF_WLAN`, `MPF_WEB_PORT`, `MPF_AP_PSK`, `MPF_AP_DELAY`.
Install: copy the script to `/usr/local/bin/`, the units to `/etc/systemd/system/`, enable the three, copy the
template to the configured path as `mpf-network.txt`.
