#!/usr/bin/env python3
"""(Vendored from Ashram56/Stern-SAM-Decryption tools/pup/runtime.) Checks GDE GoZen's PuP video decoding on this PC, without the game (docs/pup/README.md): a few pack videos decoded on
the GPU (Direct3D 11 Video / DXVA2 on Windows, the Jetson's decoder), then in software (GOZEN_HWDEC=0), with the
speed of each against the video's own frame rate.

    python scripts/video_check.py            # both runs
    python scripts/video_check.py --gpu      # the GPU run only
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # scripts/
import toolchain as tc  # noqa: E402


def run(label, hwdec):
    env = dict(os.environ)
    env.pop("GOZEN_HWDEC", None)
    if hwdec is not None:
        env["GOZEN_HWDEC"] = hwdec
    out = os.path.join(tempfile.mkdtemp(prefix="pup-video-check-"), "result.txt")
    cmd = tc.godot_command("--headless", "-s", "res://tools/gozen_check.gd", "--", "--out", out)
    print("== " + label, flush=True)
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    # GoZen's own lines (which decoder each video got) come on Godot's output; the results in the file
    for line in (proc.stdout + proc.stderr).splitlines():
        if line.startswith("GoZen: ") or "GoZenVideo" in line:
            print("   " + line)
    if os.path.exists(out):
        with open(out) as f:
            for line in f.read().splitlines():
                print("   " + line)
    else:
        print("   no result (Godot exit code {}): {}".format(proc.returncode, " ".join(cmd)))
        return 1
    return 0


def main():
    code = run("GPU decoding (GOZEN_HWDEC unset)", None)
    if "--gpu" not in sys.argv[1:]:
        code |= run("software decoding (GOZEN_HWDEC=0)", "0")
    return code


if __name__ == "__main__":
    sys.exit(main())
