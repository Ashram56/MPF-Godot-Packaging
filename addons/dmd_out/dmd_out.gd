extends Node
## Sends the game's 128x32 DMD to an RGB LED DMD: a PIN2DMD (MPF's pin2dmd platform, USB) or a ZeDMD
## (mpf_godot/zedmd_native.py over MPF, or native/zedmd_feed through a pipe). Add it as an autoload of a GMC game whose
## root viewport is the 128x32 DMD; it does nothing unless Godot is started with one of the user args:
##   godot --path GAME -- --pin2dmd[=#RRGGBB]                          frames to MPF as "rgb_dmd_frame"
##   godot --path GAME -- --zedmd[=#RRGGBB]                            the same, for the zedmd_native platform
##   godot --path GAME -- --zedmd --zedmd-feed=/path/to/zedmd_feed    frames piped to the native feeder, not to MPF
## MPF needs the matching overlay (examples/dmd_devices/). Each changed frame (up to FPS a second) is 12288 bytes, three
## per dot, row by row, rgb_dmds "default". Monochrome: the picture's brightness (0-15, as a DMD's 16 shades) scales
## one colour, #RRGGBB (default #ff730d, a DMD's orange). platforms/dmd_devices.md.

const WIDTH := 128
const HEIGHT := 32
const FPS := 30.0
const DEFAULT_COLOR := "#ff730d"
const FEED_ARG := "--zedmd-feed="

var _color := Color(DEFAULT_COLOR)
var _palette := PackedByteArray()      # 16 shades x 3 bytes
var _last := PackedByteArray()
var _elapsed := 0.0
var _feed: FileAccess = null           # the feeder's stdin
var _feed_pid := 0


func _ready() -> void:
	var on := false
	for a in OS.get_cmdline_user_args():
		if a == "--pin2dmd" or a == "--zedmd":
			on = true
		elif a.begins_with(FEED_ARG):
			_start_feed(a.trim_prefix(FEED_ARG))
		elif a.begins_with("--pin2dmd=") or a.begins_with("--zedmd="):
			on = true
			var v := a.substr(a.find("=") + 1).strip_edges().to_lower()
			if Color.html_is_valid(v):
				_color = Color(v)
	set_process(on)
	_palette = shade_palette(_color)


func _start_feed(path: String) -> void:
	var run := OS.execute_with_pipe(path, [])
	if run.is_empty():
		push_warning("zedmd_feed did not start: " + path)
		return
	_feed = run["stdio"]
	_feed_pid = run["pid"]


func _exit_tree() -> void:
	if _feed_pid:
		if _feed:
			_feed.close()              # the feeder ends when its stdin closes
		OS.kill(_feed_pid)


## 16 shades of one colour as 48 bytes (shade n = the colour at n / 15).
static func shade_palette(color: Color) -> PackedByteArray:
	var out := PackedByteArray()
	out.resize(48)
	for n in 16:
		var k := n / 15.0
		out[n * 3] = roundi(color.r * k * 255.0)
		out[n * 3 + 1] = roundi(color.g * k * 255.0)
		out[n * 3 + 2] = roundi(color.b * k * 255.0)
	return out


## The 12288-byte RGB frame of a 128x32 image: each dot's brightness as a shade, through the palette.
static func rgb_frame(image: Image, palette: PackedByteArray) -> PackedByteArray:
	var frame := PackedByteArray()
	frame.resize(WIDTH * HEIGHT * 3)
	for y in HEIGHT:
		for x in WIDTH:
			var dot := image.get_pixel(x, y)
			var at := (y * WIDTH + x) * 3
			var shade := clampi(roundi(maxf(dot.r, maxf(dot.g, dot.b)) * 15.0), 0, 15)
			frame[at] = palette[shade * 3]
			frame[at + 1] = palette[shade * 3 + 1]
			frame[at + 2] = palette[shade * 3 + 2]
	return frame


func _process(delta: float) -> void:
	_elapsed += delta
	if _elapsed < 1.0 / FPS:
		return
	_elapsed = 0.0
	var mpf := get_node_or_null("/root/MPF")       # GMC's autoload (looked up: the add-on loads without GMC)
	if not _feed and (mpf == null or not mpf.server._client):      # no MPF connected yet
		return
	var image := get_viewport().get_texture().get_image()
	if image.get_width() != WIDTH or image.get_height() != HEIGHT:
		image.resize(WIDTH, HEIGHT, Image.INTERPOLATE_NEAREST)
	var frame := rgb_frame(image, _palette)
	if frame == _last:
		return
	_last = frame
	if _feed:
		if not OS.is_process_running(_feed_pid):
			push_warning("zedmd_feed stopped")
			_feed = null
			return
		_feed.store_buffer(frame)
		_feed.flush()
		return
	mpf.server.send_bytes("rgb_dmd_frame", frame, {"name": "default"})
