#!/usr/bin/env python3
"""Is a real DMD panel plugged in? A platform question, the same for every game: a game's launcher asks it to choose
between a PIN2DMD, a ZeDMD and the screen (platforms/dmd_devices.md, "Choosing the device"). Standard library only.

    python -m mpf_godot dmd-detect     # pin2dmd, zedmd, or nothing

A PIN2DMD counts when its USB id (0314:e457) is on the bus. A ZeDMD counts only when it answers the handshake on its
USB serial port (the ESP32's own USB 303a:1001, a Raspberry Pi Pico 2 2e8a:000f (checked on a ZeDMD 6.1.3), or a CH340 / CP210x bridge, ids that other boards share), as
mpf_godot/zedmd_native.py speaks it. Linux only (sysfs); elsewhere nothing is found and "auto" stays stacked.
A ZeDMD on Wi-Fi is not looked for.
"""
import glob
import os
import select
import sys
import time

PIN2DMD = ("0314", "e457")
ZEDMD = {("303a", "1001"): 115200, ("2e8a", "000f"): 921600, ("1a86", "55d3"): 921600, ("1a86", "7523"): 921600, ("10c4", "ea60"): 921600}
HANDSHAKE = b"FRAME" + b"ZeDMD" + bytes((0x0C, 0, 0, 0))
SYS = "/sys"


def usb_id(path):
    """(vendor, product) of the USB device at or above the sysfs path, lower case hex, or None."""
    path = os.path.realpath(path)
    for _ in range(6):
        try:
            with open(os.path.join(path, "idVendor")) as v, open(os.path.join(path, "idProduct")) as p:
                return v.read().strip().lower(), p.read().strip().lower()
        except OSError:
            path = os.path.dirname(path)
    return None


def usb_ids(root=SYS):
    return {i for i in (usb_id(d) for d in glob.glob(os.path.join(root, "bus", "usb", "devices", "*"))) if i}


def serial_ports(root=SYS):
    """[(device, baud)] of the serial ports whose USB id a ZeDMD uses."""
    out = []
    for tty in sorted(glob.glob(os.path.join(root, "class", "tty", "ttyUSB*")) +
                      glob.glob(os.path.join(root, "class", "tty", "ttyACM*"))):
        baud = ZEDMD.get(usb_id(os.path.join(tty, "device")))
        if baud:
            out.append(("/dev/" + os.path.basename(tty), baud))
    return out


def zedmd_answers(device, baud, timeout=5.0):
    """True when a ZeDMD on `device` answers the handshake. Opening the port can reset the ESP32, so the handshake is
    sent again each second until `timeout`."""
    import termios
    import tty
    try:
        fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        tty.setraw(fd)
        attrs = termios.tcgetattr(fd)
        speed = getattr(termios, "B{}".format(baud))
        attrs[4] = attrs[5] = speed
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)
        end, reply, sent = time.monotonic() + timeout, b"", 0.0
        while time.monotonic() < end:
            if time.monotonic() - sent >= 1.0:
                reply, sent = b"", time.monotonic()
                os.write(fd, HANDSHAKE.ljust(64, b"\0"))
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                reply += os.read(fd, 64 - len(reply))
                if len(reply) >= 64:
                    if reply[:4] == b"ZeDM" and reply[57:58] == b"R":
                        return True
                    reply = b""
        return False
    except (OSError, termios.error, AttributeError):
        return False
    finally:
        os.close(fd)


def find(root=SYS):
    """"pin2dmd", "zedmd" or "" (also on a system without sysfs)."""
    if PIN2DMD in usb_ids(root):
        return "pin2dmd"
    if any(zedmd_answers(dev, baud) for dev, baud in serial_ports(root)):
        return "zedmd"
    return ""


def main(argv=None):
    print(find())
    return 0


if __name__ == "__main__":
    sys.exit(main())
