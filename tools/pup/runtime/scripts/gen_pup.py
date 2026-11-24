#!/usr/bin/env python3
"""Convert the PuP Pack's media for Godot: [pup] pack_dir -> [pup] media_dir (game/pup.cfg; git-ignored).

    python scripts/gen_pup.py                  # everything, in parallel; re-runs only redo changed files
    python scripts/gen_pup.py --max-height 720 # smaller videos for a slower PC
    python scripts/gen_pup.py --only "Drain/*" # some files (testing)

Godot plays Theora video only, so every .mp4 becomes an .ogv (Theora + Vorbis); with --native (Windows and
macOS, the native_video add-on: pup_addons/native_video) the videos are only probed and Godot plays the pack's mp4s. The OST mp3s and the pictures
are copied as they are: Godot loads them at run time. manifest.json lists each file with its converted path,
size and length; the Godot PuP player (game/pup/pup_player.gd) reads it, and without it the PuP stays off.

Needs ffmpeg with libtheora: FFMPEG=<path>, or ffmpeg on the PATH, or `pip install imageio-ffmpeg` (into
.venv: .venv/bin/pip or .venv\\Scripts\\pip), whose ffmpeg has it. Standard library only otherwise.
"""
import argparse
import concurrent.futures
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: E402
import toolchain as tc  # noqa: E402

sys.path.insert(0, tc.GAME)
from pup_runtime import settings  # noqa: E402

VIDEO = (".mp4", ".m4v", ".mov", ".avi", ".wmv", ".webm", ".mkv", ".f4v")
COPY = (".mp3", ".ogg", ".png", ".jpg", ".jpeg", ".bmp", ".webp")
AUDIO_TO_OGG = (".wav",)
SKIP_DIRS = {"pupcapture", "pup-pack_options"}       # DMD captures (pup_decode.py match) and the VPX options
SIZE = re.compile(r"Stream #.*Video:.*?(\d{2,5})x(\d{2,5})")
DURATION = re.compile(r"Duration: (\d+):(\d+):(\d+\.\d+)")


def find_ffmpeg():
    candidates = [os.environ.get("FFMPEG"), shutil.which("ffmpeg")]
    try:
        import imageio_ffmpeg
        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except ImportError:
        venv = tc.venv_python()
        if os.path.exists(venv):
            out = subprocess.run([venv, "-c", "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"],
                                 capture_output=True, text=True)
            candidates.append(out.stdout.strip() if out.returncode == 0 else None)
    for exe in candidates:
        if not exe or not os.path.exists(exe) and not shutil.which(exe):
            continue
        encoders = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        if "libtheora" in encoders:
            return exe
        print("{} has no libtheora encoder, skipped".format(exe))
    raise SystemExit("no ffmpeg with libtheora: install ffmpeg, or `.venv/bin/pip install imageio-ffmpeg` "
                     "(Windows: .venv\\Scripts\\pip install imageio-ffmpeg), or set FFMPEG")


def probe(ffmpeg, path):
    err = subprocess.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True, text=True,
                         errors="replace").stderr
    info = {}
    m = SIZE.search(err)
    if m:
        info["w"], info["h"] = int(m.group(1)), int(m.group(2))
    m = DURATION.search(err)
    if m:
        info["duration"] = round(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), 3)
    info["audio"] = "Audio:" in err
    return info


def plan(pack, only):
    jobs = []
    for dirpath, dirnames, filenames in os.walk(pack):
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in SKIP_DIRS)
        rel_dir = os.path.relpath(dirpath, pack)
        if rel_dir == ".":
            continue                                  # the pack's root: option pictures, .pup files
        for name in sorted(filenames):
            rel = os.path.join(rel_dir, name).replace(os.sep, "/")
            if only and not any(fnmatch.fnmatch(rel, pattern) for pattern in only):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in VIDEO:
                jobs.append((rel, os.path.splitext(rel)[0] + ".ogv", "video"))
            elif ext in AUDIO_TO_OGG:
                jobs.append((rel, os.path.splitext(rel)[0] + ".ogg", "audio"))
            elif ext in COPY:
                jobs.append((rel, rel, "copy"))
    return jobs


def convert(ffmpeg, pack, out, job, args):
    rel, out_rel, kind = job
    src, dst = os.path.join(pack, rel), os.path.join(out, out_rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    info = probe(ffmpeg, src) if kind != "copy" or rel.lower().endswith(".mp3") else {}
    entry = {"out": out_rel}
    entry.update({k: v for k, v in info.items() if k in ("duration",)})
    fresh = os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src) and not args.force
    if kind == "copy":
        if not fresh:
            shutil.copyfile(src, dst)
        return rel, entry, "copied" if not fresh else "up to date"
    if kind == "video" and args.native:
        return rel, dict({k: info[k] for k in ("w", "h", "duration") if k in info}, native=True), "native"
    if kind == "video":
        w, h = info.get("w", 0), info.get("h", 0)
        if args.max_height and h > args.max_height:
            w, h = round(w * args.max_height / h / 2) * 2, args.max_height
        entry.update(w=w, h=h)
    if fresh:
        return rel, entry, "up to date"
    cmd = [ffmpeg, "-v", "error", "-y", "-i", src]
    if kind == "video":
        cmd += ["-map", "0:v:0", "-c:v", "libtheora", "-q:v", str(args.quality), "-pix_fmt", "yuv420p"]
        if args.max_height and info.get("h", 0) > args.max_height:
            cmd += ["-vf", "scale={}:{}".format(entry["w"], entry["h"])]
        if info.get("audio"):
            cmd += ["-map", "0:a:0", "-c:a", "libvorbis", "-q:a", "5", "-ar", "44100"]
    else:
        cmd += ["-c:a", "libvorbis", "-q:a", "5"]
    tmp = dst + ".part" + os.path.splitext(dst)[1]
    result = subprocess.run(cmd + [tmp], capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError("{}: {}".format(rel, result.stderr.strip()[-500:]))
    fsutil.replace(tmp, dst)
    return rel, entry, "converted"


def main(argv=None):
    cfg = settings.load()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pack", default=settings.pack_dir(cfg), help="the PuP Pack folder (default from game/pup.cfg)")
    p.add_argument("--out", default=settings.media_dir(cfg), help="converted media (default from game/pup.cfg)")
    p.add_argument("--jobs", type=int, default=os.cpu_count() or 2, help="parallel conversions")
    p.add_argument("--max-height", type=int, default=0, help="scale videos down to this height (0: keep)")
    p.add_argument("--quality", type=int, default=7, choices=range(0, 11), help="Theora quality 0-10 (default 7)")
    p.add_argument("--only", action="append", help="pack paths to convert (glob, repeatable)")
    p.add_argument("--native", action="store_true", help="keep the videos as they are (native_video add-on)")
    p.add_argument("--force", action="store_true", help="convert again even when up to date")
    args = p.parse_args(argv)
    if not os.path.exists(os.path.join(args.pack, "triggers.pup")):
        raise SystemExit("no PuP Pack at {}: run scripts/pup_setup.py".format(args.pack))
    ffmpeg = find_ffmpeg()
    jobs = plan(args.pack, args.only)
    print("PuP media: {} files from {} to {} ({} jobs, ffmpeg {})".format(len(jobs), args.pack, args.out,
                                                                           args.jobs, ffmpeg), flush=True)
    os.makedirs(args.out, exist_ok=True)
    manifest_path = os.path.join(args.out, "manifest.json")
    files = {}
    if args.only and os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            files = json.load(f).get("files", {})
    failed = []
    with concurrent.futures.ThreadPoolExecutor(max(1, args.jobs)) as pool:
        futures = [pool.submit(convert, ffmpeg, args.pack, args.out, job, args) for job in jobs]
        for n, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                rel, entry, what = fut.result()
            except RuntimeError as e:
                failed.append(str(e))
                print("  FAILED " + str(e), flush=True)
                continue
            files[rel] = entry
            print("  [{}/{}] {} {}".format(n, len(jobs), what, rel), flush=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"pack": os.path.relpath(args.pack, tc.ROOT).replace(os.sep, "/"),
                   "files": dict(sorted(files.items()))}, f, indent=1)
    print("manifest: {} ({} files)".format(manifest_path, len(files)))
    if failed:
        print("{} files failed".format(len(failed)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
