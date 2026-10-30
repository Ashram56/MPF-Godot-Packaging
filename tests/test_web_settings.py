"""The page asks for a game's settings with the folder name percent-encoded (`demo%401.0`): the server must decode it."""
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_games import Base  # noqa: E402
import mpf_web as W  # noqa: E402


class SettingsUrl(Base):
    def test_encoded_folder_name_is_found(self):
        self.install()                                                   # demo@1.0
        with mock.patch.object(W.N, "authorized", return_value=True):
            srv = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
            base = f"http://127.0.0.1:{srv.server_address[1]}/api/settings/"
            for name in ("demo%401.0", "demo@1.0"):
                with urllib.request.urlopen(base + name) as r:
                    self.assertIn("html", json.load(r), name)
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + "nothing%401.0")
            self.assertEqual(e.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
