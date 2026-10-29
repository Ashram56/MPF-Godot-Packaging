#!/usr/bin/env python3
"""Our fixes to GMC 1.0.0 (the mpf-gmc Godot add-on), applied to a copy of it, idempotently.

Each edit carries the id of its fix document in fixes/gmc/:

  bcp-partial-lines       GMC parsed each socket read as whole lines; MPF's large "settings" message at connect
                          splits across reads, the half message fails to parse and the BCP thread stops (no sound
                          or music for the rest of the session). The unfinished end of a read is kept for the next.
  bcp-parse-error         a message that fails to parse raised a script error (`json.error` on a null result)
                          that stopped the BCP thread; it is now logged and skipped.
  keyboard-layout         gmc.cfg [keyboard] matched keys by their layout label only: on AZERTY the number row and
                          "/" never matched. A key not found by label is also looked up by its US position.

    python -m mpf_godot patch-gmc [GMC_DIR]     # default: toolchain/addons/mpf-gmc; prints what it did
"""
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mpf_godot import toolchain as tc  # noqa: E402

# every edit carries TAG, so a file holds the patch when TAG is in it. OLD_TAGS: the tag earlier installs wrote (compatibility
# only: a copy that holds one is already patched and must not be patched twice)
TAG = "# mpf-godot fix"
OLD_TAGS = ("# tron patch",)

EDITS = [
    ("bcp-partial-lines", "scripts/bcp_server.gd",
     "var _client: StreamPeerTCP\n",
     "var _client: StreamPeerTCP\n" + TAG + " bcp-partial-lines: the unfinished end of the last read\n"
     "var _rx_partial := \"\"\n"),
    ("bcp-partial-lines", "scripts/bcp_server.gd",
     "\t\t_client = _server.take_connection()\n",
     "\t\t_client = _server.take_connection()\n\t\t_rx_partial = \"\"\n"),
    ("bcp-partial-lines", "scripts/bcp_server.gd",
     "\t\tvar messages := _client.get_string(bytes).split(\"\\n\")\n",
     "\t\t" + TAG + " bcp-partial-lines: parse complete lines only, keep the rest for the next read\n"
     "\t\tvar data := _rx_partial + _client.get_string(bytes)\n"
     "\t\tvar cut := data.rfind(\"\\n\")\n"
     "\t\t_rx_partial = data.substr(cut + 1)\n"
     "\t\tvar messages := PackedStringArray()\n"
     "\t\tif cut >= 0:\n"
     "\t\t\tmessages = data.substr(0, cut).split(\"\\n\")\n"),
    ("bcp-parse-error", "scripts/bcp_parse.gd",
     "\t\t\tresult.error = \"Error %s parsing trigger: %s\" % [json.error, message]\n",
     "\t\t\tresult.error = \"Error parsing trigger: %s\" % message   " + TAG + " bcp-parse-error\n"),
    ("keyboard-layout", "mpf_gmc.gd",
     "\tif keycode in keyboard:\n",
     "\t" + TAG + " keyboard-layout: a key that is not in [keyboard] by its label is looked up by its\n"
     "\t# position on a US QWERTY keyboard (on AZERTY the '(' key is the 5 key)\n"
     "\tif not keycode in keyboard:\n"
     "\t\tvar physical = OS.get_keycode_string(event.get_physical_keycode_with_modifiers()).to_upper()\n"
     "\t\tif physical in keyboard:\n"
     "\t\t\tkeycode = physical\n"
     "\tif keycode in keyboard:\n"),
]

FIX_IDS = sorted({e[0] for e in EDITS})


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def status(gmc_dir=None):
    """'missing' (no GMC there), 'in place' (every file patched) or 'unpatched'."""
    gmc_dir = gmc_dir or tc.gmc_dir()
    if not os.path.exists(os.path.join(gmc_dir, "plugin.cfg")):
        return "missing"
    files = {rel for _id, rel, _o, _n in EDITS}
    texts = [_read(os.path.join(gmc_dir, *rel.split("/"))) for rel in files]
    if all(any(t in text for t in (TAG,) + OLD_TAGS) for text in texts):
        return "in place"
    return "unpatched"


def patch(gmc_dir=None, quiet=False):
    """Apply the edits; returns "patched", "in place", "missing" (no GMC there) or raises on an unknown GMC."""
    gmc_dir = gmc_dir or tc.gmc_dir()
    state = status(gmc_dir)
    if state != "unpatched":
        return state
    texts = {}
    for _id, rel, _old, _new in EDITS:
        if rel not in texts:
            texts[rel] = _read(os.path.join(gmc_dir, *rel.split("/")))
    for fix_id, rel, old, new in EDITS:
        text = texts[rel]
        crlf = "\r\n" in text
        o, n = (old.replace("\n", "\r\n"), new.replace("\n", "\r\n")) if crlf else (old, new)
        if n in text:
            continue
        if text.count(o) != 1:
            raise SystemExit("GMC {}: {} does not look like GMC {} ({} not applicable); remove it and run setup again"
                             .format(gmc_dir, rel, tc.GMC_VERSION, fix_id))
        texts[rel] = text.replace(o, n)
    for rel, text in texts.items():
        with open(os.path.join(gmc_dir, *rel.split("/")), "w", encoding="utf-8", newline="") as f:
            f.write(text)
    if not quiet:
        print("   GMC patched: " + ", ".join(FIX_IDS) + " (fixes/gmc/)", flush=True)
    return "patched"


if __name__ == "__main__":
    print(patch(sys.argv[1] if len(sys.argv) > 1 else None, quiet=True))
