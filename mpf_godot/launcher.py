#!/usr/bin/env python3
"""Start an MPF + GMC game: Godot (GMC, the BCP server) first, then MPF, optionally MPF Monitor.

    python -m mpf_godot run GAME                     # GAME: the folder with project.godot and MPF's config/
    python -m mpf_godot run GAME --monitor           # ... plus MPF Monitor
    python -m mpf_godot run GAME --seconds 20        # stop everything after 20 s
    python -m mpf_godot run GAME -c config,hw_proc   # MPF config files (mpf game -c)
    python -m mpf_godot run GAME -- --fullscreen     # arguments after -- go to Godot

Godot's log goes to GAME/logs/godot.log. MPF runs in this terminal; quitting it (Ctrl+C) stops Godot and MPF
Monitor too. What it does about each platform's traps (fixes/, platforms/):

- waits for GMC's port by trying to bind it, never by connecting: GMC quits when a client hangs up
  (fixes/gmc/port-probe-quits.md), and probes IPv4 and IPv6, since Godot on Windows listens on IPv6 only;
- Linux without a display: Godot under Xvfb (xvfb-run); Godot's --headless draws nothing;
- Linux on a real X display: X's screen saver and DPMS off for the session (a cabinet's players touch no mouse);
- Linux with 4+ cores: Godot's main thread gets a core of its own (MPF_GODOT_PIN=0 turns it off);
- --no-render-thread: Godot draws on its main thread, should a GPU driver misbehave with the separate one.
"""
import argparse
import errno
import os
import shutil
import signal
import socket
import subprocess
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mpf_godot import toolchain as tc  # noqa: E402

IS_WINDOWS = os.name == "nt"


def port_in_use(port):
    """True when something listens on port. Binds instead of connecting: GMC quits when its client hangs up."""
    # Godot listens on "*", an IPv6 socket that also takes IPv4 on Linux but not always on Windows: probe both
    probes = [(socket.AF_INET, ""), (socket.AF_INET, "127.0.0.1")]
    if socket.has_ipv6:
        probes += [(socket.AF_INET6, "::"), (socket.AF_INET6, "::1")]
    for family, host in probes:
        try:
            s = socket.socket(family, socket.SOCK_STREAM)
        except OSError:         # no IPv6 stack
            continue
        with s:
            if IS_WINDOWS:      # without it a Windows bind can share a port that is taken
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:               # ignore TIME_WAIT leftovers of the last run; a listener still blocks the bind
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if family == socket.AF_INET6:
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            try:
                s.bind((host, port))
            except OSError as e:
                if family == socket.AF_INET6 and e.errno in (errno.EADDRNOTAVAIL, errno.EAFNOSUPPORT):
                    continue    # IPv6 present but no ::1 / disabled
                return True
    return False


def log_says(path, marker):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return marker in f.read()
    except OSError:
        return False


def log_tail(path, lines=15):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except OSError:
        return ""


def wait_for_port(port, procs, timeout, log=None, marker=None):
    """Wait until port is taken (or log shows marker); fail early when one of procs exits."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if port_in_use(port) or (marker and log_says(log, marker)):
            return True
        if any(p.poll() is not None for p in procs):
            return False
        time.sleep(0.2)
    return False


def spawn(cmd, *, log=None, cwd=None, env=None, group=False):
    """Start cmd; log is a path (stdout + stderr) or None to inherit the terminal."""
    out = open(log, "w", encoding="utf-8") if log else None
    kw = {}
    if group:       # its own process group, so stop() also ends its children (xvfb-run -> Godot)
        if IS_WINDOWS:
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kw["start_new_session"] = True
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT if out else None,
                            stdin=subprocess.DEVNULL if group else None, **kw)
    proc.log_file = out
    proc.group = group
    return proc


def stop(proc, grace=10):
    """Ask proc to end, then kill it after grace seconds."""
    if proc is None:
        return None
    if proc.poll() is None:
        try:
            if proc.group and not IS_WINDOWS:
                os.killpg(proc.pid, signal.SIGTERM)
            else:
                proc.terminate()
            proc.wait(grace)
        except subprocess.TimeoutExpired:
            if proc.group and not IS_WINDOWS:
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.wait()
        except (ProcessLookupError, PermissionError):
            pass
    if proc.log_file:
        proc.log_file.close()
    return proc.returncode


def godot_command(game, godot_args=(), virtual_display=None, render_thread=True):
    exe = tc.godot_path()
    if not os.path.exists(exe) and not shutil.which(exe):
        raise SystemExit("Godot not found at {} (run `python -m mpf_godot setup`, or set GODOT)".format(exe))
    args = list(godot_args)
    if (not render_thread or "opengl3" in args) and "--render-thread" not in args:
        # Godot's separate render thread off: asked for, or the opengl3 renderer (Xvfb captures), which wrote no
        # frames with it (platforms/linux.md)
        args = ["--render-thread", "safe"] + args
    cmd = [exe, "--path", game] + args
    if virtual_display is None:
        virtual_display = tc.needs_virtual_display()
    if virtual_display:
        if not shutil.which("xvfb-run"):
            raise SystemExit("no display and no xvfb-run: install xvfb (apt install xvfb) or set DISPLAY")
        cmd = ["xvfb-run", "-a", "-s", "-screen 0 1280x720x24"] + cmd
    return cmd


def core_pinning(godot, mpf, stop_event, interval=2.0):
    """Linux, 4+ usable cores: Godot's main thread gets the last core to itself; Godot's other threads (renderer,
    video decoding, audio) and MPF share the others. Godot's main thread runs the game's scripts and draws every
    frame, so it is the one that must not wait for a core (a Jetson Xavier NX: +1.5 FPS, a third fewer late
    frames; platforms/jetson.md). Applied again every `interval` s, as new threads start with their creator's cores."""
    cpus = sorted(os.sched_getaffinity(0))
    main_core, others = {cpus[-1]}, set(cpus[:-1])
    while not stop_event.wait(interval):
        for proc, is_godot in ((godot, True), (mpf, False)):
            if proc is None or proc.poll() is not None:
                continue
            try:
                tids = [int(t) for t in os.listdir("/proc/%d/task" % proc.pid)]
            except OSError:
                continue
            for tid in tids:
                want = main_core if is_godot and tid == proc.pid else others
                try:
                    if os.sched_getaffinity(tid) != want:
                        os.sched_setaffinity(tid, want)
                except OSError:
                    pass                # the thread ended meanwhile


def start_core_pinning(godot, mpf, virtual_display):
    """core_pinning() on a thread when it applies (Linux, a real display, 4+ cores); returns its stop event."""
    if not sys.platform.startswith("linux") or virtual_display or os.environ.get("MPF_GODOT_PIN") == "0" \
            or len(os.sched_getaffinity(0)) < 4:
        return None
    import threading
    stop_event = threading.Event()
    threading.Thread(target=core_pinning, args=(godot, mpf, stop_event), daemon=True).start()
    return stop_event


def keep_screen_on():
    """Linux on a real X display: X's screen saver and DPMS power-off off for this session. GNOME's own idle
    blanking and lock are turned off by platforms/jetson/install_jetson_hwdec.sh (platforms/jetson.md)."""
    if IS_WINDOWS or sys.platform == "darwin" or not os.environ.get("DISPLAY") or tc.needs_virtual_display():
        return
    if shutil.which("xset"):
        subprocess.run(["xset", "s", "off", "-dpms"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run(game, *, configs="config", monitor=False, seconds=None, text_ui=False, godot_args=(), mpf_args=(),
        virtual_display=None, render_thread=True, timeout=120):
    """Godot, then MPF (and MPF Monitor); returns MPF's exit code. Everything is stopped on the way out."""
    game = os.path.abspath(game)
    if not os.path.exists(os.path.join(game, "project.godot")):
        raise SystemExit("{} has no project.godot".format(game))
    logs = os.path.join(game, "logs")
    os.makedirs(logs, exist_ok=True)
    godot_log = os.path.join(logs, "godot.log")
    if port_in_use(tc.BCP_PORT):
        raise SystemExit("port {} is already taken: is another Godot/GMC running?".format(tc.BCP_PORT))
    if virtual_display is None:
        virtual_display = tc.needs_virtual_display()
    if not virtual_display:
        keep_screen_on()
    godot = mpf = mon = pinning = None
    try:
        godot = spawn(godot_command(game, godot_args, virtual_display, render_thread), log=godot_log, group=True)
        print("Godot started (log: {}), waiting for GMC on port {}".format(godot_log, tc.BCP_PORT), flush=True)
        if not wait_for_port(tc.BCP_PORT, [godot], timeout, godot_log, "GMC listening on port"):
            godot.log_file.flush()
            raise SystemExit("GMC did not open port {}{}; last lines of {}:\n{}".format(
                tc.BCP_PORT, " (Godot exited)" if godot.poll() is not None else "", godot_log, log_tail(godot_log)))
        print("GMC is listening", flush=True)
        margs = ["game", ".", "-c", configs] + ([] if text_ui else ["-t"]) + list(mpf_args)
        print("Starting MPF: mpf " + " ".join(margs), flush=True)
        mpf = spawn(tc.mpf_command() + margs, cwd=game, log=None if text_ui else os.path.join(logs, "mpf.log"))
        pinning = start_core_pinning(godot, mpf, virtual_display)
        if monitor:
            print("waiting for MPF's BCP server on port {} for MPF Monitor".format(tc.MONITOR_PORT), flush=True)
            if wait_for_port(tc.MONITOR_PORT, [mpf], timeout):
                mon = spawn(tc.mpf_command() + ["monitor"], cwd=game, group=True, log=os.path.join(logs, "monitor.log"))
                print("MPF Monitor started (log: {})".format(os.path.join(logs, "monitor.log")), flush=True)
            else:
                print("MPF did not open port {}: no MPF Monitor".format(tc.MONITOR_PORT), flush=True)
        try:
            mpf.wait(seconds)
        except subprocess.TimeoutExpired:
            print("{} s elapsed, stopping MPF".format(seconds), flush=True)
            stop(mpf)
            mpf.returncode = 0          # a planned stop, not a failure
        return mpf.returncode
    except KeyboardInterrupt:
        print("interrupted, stopping", flush=True)
        return 130
    finally:
        if pinning:
            pinning.set()
        for p in (mon, mpf, godot):
            stop(p)


def parser():
    p = argparse.ArgumentParser(prog="python -m mpf_godot run", description=__doc__.split("\n")[0])
    p.add_argument("game", help="the game folder (project.godot and MPF's config/)")
    p.add_argument("-c", "--configs", default="config", help="MPF config files, comma separated (default: config)")
    p.add_argument("--monitor", action="store_true", help="also start MPF Monitor")
    p.add_argument("--seconds", type=float, help="stop everything after this many seconds")
    p.add_argument("--text-ui", action="store_true", help="MPF's text UI in this terminal (default: plain log)")
    p.add_argument("--no-render-thread", dest="render_thread", action="store_false",
                   help="Godot draws on its main thread instead of a separate render thread")
    p.add_argument("--xvfb", dest="virtual_display", action="store_true", default=None,
                   help="Linux: run Godot under Xvfb even with a display")
    p.add_argument("godot_args", nargs="*", help="after --: arguments for Godot")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    return run(args.game, configs=args.configs, monitor=args.monitor, seconds=args.seconds, text_ui=args.text_ui,
               godot_args=args.godot_args, virtual_display=args.virtual_display, render_thread=args.render_thread)


if __name__ == "__main__":
    sys.exit(main())
