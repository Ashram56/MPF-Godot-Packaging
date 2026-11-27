"""The setup access point: dnsmasq's leases off the read-only root, and the phone's connectivity check answered."""
import sys as _sys
import unittest as _unittest

if not _sys.platform.startswith("linux"):
    raise _unittest.SkipTest("the netconfig code runs on the Linux images only")

import http.client
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common", "netconfig"))
import mpf_netconfig as nc  # noqa: E402


class AccessPoint(unittest.TestCase):
    def test_leases_in_ram(self):
        hostapd, dnsmasq = nc.ap_configs()
        self.assertIn("dhcp-leasefile=/run/", dnsmasq)   # production: the root is read-only, dnsmasq quits without it
        self.assertIn("dhcp-range=", dnsmasq)
        self.assertIn(f"ssid={nc.AP_SSID}", hostapd)
        self.assertIn(f"wpa_passphrase={nc.AP_PSK}", hostapd)

    def test_connectivity_check_redirected_to_the_page(self):
        old = nc.AP_ADDR
        nc.AP_ADDR = "127.0.0.1"
        try:
            srv = nc.portal_redirect(port=0)
            self.assertIsNotNone(srv)
            try:
                c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
                c.request("GET", "/generate_204", headers={"Host": "connectivitycheck.gstatic.com"})
                r = c.getresponse()
                self.assertEqual(r.status, 302)
                self.assertEqual(r.getheader("Location"), "http://127.0.0.1:8080/")
            finally:
                srv.shutdown()
                srv.server_close()
        finally:
            nc.AP_ADDR = old


if __name__ == "__main__":
    unittest.main()
