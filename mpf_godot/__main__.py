"""python -m mpf_godot COMMAND ...

    setup       install MPF, MPF Monitor, Godot and GMC with our fixes (mpf_godot/setup_toolchain.py)
    addons      copy the patched GMC (and with --video the video add-ons) into a game folder
    bundle      build a game bundle (code and multimedia, no binary) from the game's spec (mpf_godot/bundle.py)
    patch-gmc   apply our GMC fixes to a GMC folder (default: toolchain/addons/mpf-gmc)
    run         start a game: Godot (GMC) first, then MPF, optionally MPF Monitor (mpf_godot/launcher.py)
    info        the paths and versions in use
"""
import argparse
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mpf_godot import fsutil, gmc_patch  # noqa: E402
from mpf_godot import toolchain as tc  # noqa: E402


def addons(argv):
    p = argparse.ArgumentParser(prog="python -m mpf_godot addons",
                                description="Copy the patched GMC (and the video add-ons) into GAME/addons/.")
    p.add_argument("game", help="the game's Godot project folder")
    p.add_argument("--video", action="store_true", help="also GDE GoZen (Linux, Windows) and native_video "
                                                         "(Windows, macOS), with our fixes (fixes/gde-gozen/, "
                                                         "fixes/native-video/)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    dest = os.path.join(os.path.abspath(args.game), "addons")
    jobs = [(tc.gmc_dir(), os.path.join(dest, "mpf-gmc"))]
    if args.video:
        if tc.gozen_supported():
            jobs.append((tc.addon_dir("gde_gozen"), os.path.join(dest, "gde_gozen")))
        if tc.native_video_supported():
            jobs.append((tc.addon_dir("native_video"), os.path.join(dest, "native_video")))
    if not os.path.exists(os.path.join(tc.gmc_dir(), "plugin.cfg")) and not args.dry_run:
        raise SystemExit("no GMC in {}: run `python -m mpf_godot setup` first".format(tc.gmc_dir()))
    for src, dst in jobs:
        print("   {} -> {}".format(src, dst), flush=True)
        if not args.dry_run:
            fsutil.copy_tree(src, dst)
    if not args.dry_run:
        print("   GMC: " + gmc_patch.patch(os.path.join(dest, "mpf-gmc"), quiet=True))
        if os.path.exists(os.path.join(args.game, "project.godot")) and os.path.exists(tc.godot_path()):
            from mpf_godot import launcher
            launcher.import_project(os.path.abspath(args.game))
    print("The game's project.godot needs GMC enabled: [autoload] MPF=\"*res://addons/mpf-gmc/mpf_gmc.gd\" and "
          "[editor_plugins] enabled=PackedStringArray(\"res://addons/mpf-gmc/plugin.cfg\") (examples/minimal/).")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "setup":
        from mpf_godot import setup_toolchain
        return setup_toolchain.main(rest)
    if cmd == "addons":
        return addons(rest)
    if cmd == "bundle":
        from mpf_godot import bundle
        return bundle.main(rest)
    if cmd == "patch-gmc":
        print(gmc_patch.patch(rest[0] if rest else None, quiet=True))
        return 0
    if cmd == "run":
        from mpf_godot import launcher
        return launcher.main(rest)
    if cmd == "info":
        print(tc.summary())
        return 0
    print("unknown command {!r}\n{}".format(cmd, __doc__), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
