#!/usr/bin/env python3
"""A window that shows the DMD pictures dmd_bridge writes with --rgb-out (the local platform's `--dmd preview`): the same pictures a
ZeDMD would get, Serum colour included, on the screen of a computer that has none. Standard library only (tkinter: part of the
python.org installers for Windows and macOS).

    python -m mpf_godot.dmd_preview FILE [--size 128x32] [--zoom 6] [--title TEXT]
"""
import argparse
import os
import sys


def ppm(rgb, width, height):
    """The binary PPM of an RGB888 picture, or None when `rgb` is not a whole picture (the bridge was writing it)."""
    if len(rgb) != width * height * 3:
        return None
    return b"P6 %d %d 255\n" % (width, height) + rgb


def read(path, width, height):
    try:
        with open(path, "rb") as f:
            return ppm(f.read(), width, height)
    except OSError:
        return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("file")
    p.add_argument("--size", default="128x32")
    p.add_argument("--zoom", type=int, default=6)
    p.add_argument("--title", default="DMD preview (what a ZeDMD would show)")
    a = p.parse_args(argv)
    width, height = (int(x) for x in a.size.split("x"))
    try:
        import tkinter
    except ImportError:
        print("the DMD preview needs tkinter (Python from python.org has it; Linux: apt install python3-tk)", file=sys.stderr)
        return 2
    root = tkinter.Tk()
    root.title(a.title)
    root.configure(bg="black")
    label = tkinter.Label(root, bg="black", bd=0)
    label.pack()
    shown = [None]
    last = [None]

    def tick():
        data = read(a.file, width, height)
        if data is not None and data != last[0]:
            last[0] = data
            img = tkinter.PhotoImage(data=data, format="PPM")
            shown[0] = img.zoom(a.zoom, a.zoom)       # keep a reference: Tk drops a picture nobody holds
            label.configure(image=shown[0])
        root.after(33, tick)

    tick()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
