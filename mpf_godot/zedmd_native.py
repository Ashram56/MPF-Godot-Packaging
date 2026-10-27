"""A ZeDMD (https://github.com/PPUC/ZeDMD) driven directly over its USB serial port: MPF platform "zedmd_native".

MPF 0.80.1 ships a zedmd platform on top of libzedmd's compiled extension, which only loads on the Python build it was
made for and picks the x64 library on a Raspberry Pi. This one speaks the serial protocol itself (pyserial only), as
libzedmd's ZeDMDComm does (fixes/mpf/zedmd-native-serial.md):

    handshake    "FRAME" "ZeDMD" 0x0c 0 0 0, zero-padded to the write size; the reply is 64 bytes: "ZeDM" (4 bytes), width and
                 height (u16 little endian) at 4 and 6, write size at 11, byte 57 = 'R'
    frame        the 8 x 4 pixel zones (128 per frame) that changed, as "FRAME" "ZeDMD" 0x04 size-hi size-lo 0 then, per
                 zone, its index and its 8 x 4 RGB888 dots (a black zone: index + 128 alone), at most 1152 bytes a
                 packet, then "ZeDMD" 0x06 0 0 0 (render); every write of the write size is answered "ZeDMD" 'A'
    clear        "FRAME" "ZeDMD" 0x0a 0 0 0
    brightness   "FRAME" "ZeDMD" 0x16 0 1 0 level (0-15)

Frames are RGB888: the platform shows what the game sends as "rgb_dmd_frame". Use it in a machine config with
    mpf:
      platforms:
        zedmd_native: mpf_godot.zedmd_native.ZedmdNativePlatform
    hardware:
      rgb_dmd: zedmd_native
    zedmd:
      width: 128
      height: 32
(ZEDMD_PORT in the environment names the serial port).
"""
import asyncio
import logging
import os
import threading

from mpf.core.platform import RgbDmdPlatform
from mpf.platforms.interfaces.dmd_platform import DmdPlatformInterface

try:
    import serial
    from serial.tools import list_ports
except ImportError as e:        # pragma: no cover
    serial = None
    IMPORT_FAILED = e
else:
    IMPORT_FAILED = None

FRAME = b"FRAME"
CTRL = b"ZeDMD"
HANDSHAKE, ZONES_RGB888, RENDER, CLEAR, BRIGHTNESS = 0x0C, 0x04, 0x06, 0x0A, 0x16
BAUD = 921600
CDC_BAUD = 115200                    # USB JTAG/serial (ESP32-S3)
USB_IDS = {(0x303A, 0x1001), (0x1A86, 0x55D3), (0x1A86, 0x7523), (0x10C4, 0xEA60)}
ZONES_BYTE_LIMIT = 128 * 3 * 3
ZONE_W, ZONE_H = 8, 4
DEFAULT_WRITE = 64


def control(command, payload=b"", flag=0):
    """One control block: "ZeDMD", the command, the payload size (big endian) and a compression flag."""
    return CTRL + bytes((command, len(payload) >> 8 & 0xFF, len(payload) & 0xFF, flag)) + payload


def zone_packets(frame, previous, width, height):
    """The zone payloads (each at most ZONES_BYTE_LIMIT bytes) that turn `previous` (or None) into `frame`, RGB888."""
    zones_x = width // ZONE_W
    packets, current = [], bytearray()
    for index in range((width // ZONE_W) * (height // ZONE_H)):
        x, y = index % zones_x * ZONE_W, index // zones_x * ZONE_H
        rows = [frame[((y + r) * width + x) * 3:((y + r) * width + x + ZONE_W) * 3] for r in range(ZONE_H)]
        if previous is not None and all(
                previous[((y + r) * width + x) * 3:((y + r) * width + x + ZONE_W) * 3] == rows[r]
                for r in range(ZONE_H)):
            continue
        pixels = b"".join(rows)
        entry = bytes((index + 128,)) if not any(pixels) else bytes((index,)) + pixels
        if len(current) + len(entry) > ZONES_BYTE_LIMIT:
            packets.append(bytes(current))
            current = bytearray()
        current += entry
    if current:
        packets.append(bytes(current))
    return packets


class ZedmdNativePlatform(RgbDmdPlatform):

    """The ZeDMD over USB serial. Config: `zedmd: width, height` (MPF's own section); ZEDMD_PORT names the port."""

    def __init__(self, machine):
        if IMPORT_FAILED:
            raise AssertionError('Failed to load pyserial. Try: "pip3 install pyserial".') from IMPORT_FAILED
        super().__init__(machine)
        self.config = self.machine.config_validator.validate_config("zedmd", self.machine.config.get("zedmd", {}))
        self._configure_device_logging_and_debug("ZeDMD", self.config)
        self.device = None

    async def initialize(self):
        """Nothing before the DMD is configured."""

    def stop(self):
        if self.device:
            self.device.stop()

    def configure_rgb_dmd(self, name):
        if not self.device:
            self.device = ZedmdNativeDevice(self.config["width"], self.config["height"])
        return self.device


class ZedmdNativeDevice(DmdPlatformInterface):

    """Sends the newest frame from its own thread, so MPF's loop never waits for the serial port."""

    def __init__(self, width, height, port=None, opener=None):
        self.log = logging.getLogger("ZeDMD")
        self.width, self.height = width, height
        self.write_size = DEFAULT_WRITE
        self.brightness = None
        self._port_name = port or os.environ.get("ZEDMD_PORT", "")
        self._open = opener or self._open_port
        self._serial = None
        self._previous = None
        self._pending = None
        self._brightness_pending = None
        self._wake = threading.Event()
        self._stopped = False
        self._thread = threading.Thread(target=self._run, name="zedmd", daemon=True)
        self._thread.start()

    def update(self, data):
        self._pending = bytes(data)
        self._wake.set()

    def set_brightness(self, brightness):
        if brightness < 0.0 or brightness > 1.0:
            raise AssertionError("Brightness has to be between 0 and 1.")
        self._brightness_pending = round(brightness * 15)
        self._wake.set()

    def stop(self):
        self._stopped = True
        self._wake.set()
        self._thread.join(2)
        if self._serial:
            try:
                self._serial.close()
            except OSError:
                pass

    # ---- the serial side (device thread) ----

    def _open_port(self):
        names = [self._port_name] if self._port_name else [
            p.device for p in list_ports.comports() if (p.vid, p.pid) in USB_IDS]
        for name in names:
            ports = {p.device: p for p in list_ports.comports()}
            cdc = name in ports and (ports[name].vid, ports[name].pid) == (0x303A, 0x1001)
            try:
                return serial.Serial(name, CDC_BAUD if cdc else BAUD, timeout=0.5, write_timeout=0.5)
            except (OSError, serial.SerialException) as e:
                self.log.warning("ZeDMD port %s: %s", name, e)
        return None

    def _write(self, data):
        """`data` in write-size slices (the last padded with zeros), each answered 'ZeDMD' 'A'."""
        size = self.write_size
        for at in range(0, len(data), size):
            piece = data[at:at + size].ljust(size, b"\0")
            self._serial.write(piece)
            reply = self._serial.read(len(CTRL) + 1)
            if reply != CTRL + b"A":
                self.log.debug("ZeDMD answered %r, full frame next", reply)
                self._previous = None
                return False
        return True

    def _handshake(self):
        self._serial.reset_input_buffer()
        self._serial.write((FRAME + control(HANDSHAKE)).ljust(self.write_size, b"\0"))
        reply = self._serial.read(64)
        if len(reply) < 64 or reply[:4] != CTRL[:4] or reply[57:58] != b"R":
            return False
        width, height = reply[4] + reply[5] * 256, reply[6] + reply[7] * 256
        write = reply[11] + reply[12] * 256
        self.write_size = write if 32 <= write <= 1920 else DEFAULT_WRITE
        self.log.info("ZeDMD %dx%d firmware %d.%d.%d", width, height, reply[8], reply[9], reply[10])
        if (width, height) != (self.width, self.height):
            self.log.warning("ZeDMD is %dx%d, the game sends %dx%d", width, height, self.width, self.height)
        return True

    def _connect(self):
        self._serial = self._open()
        if self._serial and not self._handshake():
            self._serial.close()
            self._serial = None
        if self._serial:
            self._previous = None
            if self.brightness is not None:
                self._brightness_pending = self.brightness
        return self._serial is not None

    def _send(self, frame):
        if not any(frame):
            if self._previous is None or any(self._previous):
                self._write(FRAME + control(CLEAR))
            self._previous = frame
            return
        for packet in zone_packets(frame, self._previous, self.width, self.height):
            if not self._write(FRAME + control(ZONES_RGB888, packet) + control(RENDER)):
                return
        self._previous = frame

    def _run(self):
        while not self._stopped:
            if not self._serial and not self._connect():
                self._wake.wait(2.0)                # no ZeDMD yet: look again in two seconds
                self._wake.clear()
                continue
            self._wake.wait(3.0)
            self._wake.clear()
            try:
                if self._brightness_pending is not None:
                    self.brightness, self._brightness_pending = self._brightness_pending, None
                    self._write(FRAME + control(BRIGHTNESS, bytes((self.brightness,))))
                frame, self._pending = self._pending, None
                if frame is not None and len(frame) == self.width * self.height * 3:
                    self._send(frame)
            except (OSError, serial.SerialException) as e:
                self.log.warning("ZeDMD lost: %s", e)
                self._serial = None
