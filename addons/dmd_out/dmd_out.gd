extends Node
## Sends the game's 128x32 DMD to an RGB LED DMD: a PIN2DMD (MPF's pin2dmd platform, USB) or a ZeDMD
## (mpf_godot/zedmd_native.py over MPF, or native/zedmd_feed through a pipe). Add it as an autoload of a GMC game whose
## root viewport is the 128x32 DMD (or that offers other pictures with publish(), see --dmd-size= and --dmd-feed=); it does nothing unless Godot is started with one of the user args:
##   godot --path GAME -- --pin2dmd[=#RRGGBB]                          frames to MPF as "rgb_dmd_frame"
##   godot --path GAME -- --zedmd[=#RRGGBB]                            the same, for the zedmd_native platform
##   godot --path GAME -- --zedmd --zedmd-feed=/path/to/zedmd_feed    frames piped to the native feeder, not to MPF
##   ... --zedmd-shades                                                the pipe carries one shade 0-15 per dot (4096 bytes) instead of RGB:
##        the feeder (zedmd_feed --shades [--serum DIR --rom NAME]) then draws the colour, or Serum's colourisation (classic 128x32 only)
## MPF needs the matching overlay (examples/dmd_devices/). Each changed frame (up to FPS a second) is 12288 bytes, three
## per dot, row by row, rgb_dmds "default". Monochrome: the picture's brightness (0-15, as a DMD's 16 shades) scales
## one colour (16 shades for the 128x32 classic dots, 8 bits for 192x64, 256x64 and the HD picture), #RRGGBB (default #ff730d, a DMD's orange). platforms/dmd_devices.md.

const SIZE_ARG := "--dmd-size="        # WxH of the device: 128x32 (default), 192x64 (PIN2DMD XL), 256x64 (PIN2DMD HD, ZeDMD HD)
const FEED_NAME_ARG := "--dmd-feed="   # which picture the game published (publish()): "classic" (default, the root viewport)

var WIDTH := 128
var HEIGHT := 32
var _feeds := {}                       # name -> Viewport, set by the game with publish()
var _feed_name := "classic"
const FPS := 30.0
const DEFAULT_COLOR := "#ff730d"
const FEED_ARG := "--zedmd-feed="
const SHADES_ARG := "--zedmd-shades"
const FEED_ARGS_ARG := "--zedmd-feed-args="    # arguments for the feeder, separated by |  (e.g. --shades|--serum|DIR|--rom|NAME)

var _color := Color(DEFAULT_COLOR)
var _palette := PackedByteArray()      # 16 shades x 3 bytes
var _last := PackedByteArray()
var _elapsed := 0.0
var _feed: FileAccess = null           # the feeder's stdin
var _feed_pid := 0
var _feed_path := ""
var _feed_args := PackedStringArray()
var _shades := false                   # the feeder gets shades 0-15, one byte per dot, not RGB


func _ready() -> void:
	var on := false
	for a in OS.get_cmdline_user_args():
		if a == "--pin2dmd" or a == "--zedmd":
			on = true
		elif a.begins_with(SIZE_ARG):
			var wh := a.trim_prefix(SIZE_ARG).split("x")
			if wh.size() == 2 and int(wh[0]) > 0 and int(wh[1]) > 0:
				WIDTH = int(wh[0])
				HEIGHT = int(wh[1])
		elif a.begins_with(FEED_NAME_ARG):
			_feed_name = a.trim_prefix(FEED_NAME_ARG)
		elif a == SHADES_ARG:
			_shades = true
		elif a.begins_with(FEED_ARGS_ARG):
			_feed_args = a.trim_prefix(FEED_ARGS_ARG).split("|", false)
		elif a.begins_with(FEED_ARG):
			_feed_path = a.trim_prefix(FEED_ARG)
		elif a.begins_with("--pin2dmd=") or a.begins_with("--zedmd="):
			on = true
			var v := a.substr(a.find("=") + 1).strip_edges().to_lower()
			if Color.html_is_valid(v):
				_color = Color(v)
	if _feed_path != "":
		_start_feed(_feed_path)                # after the whole command line: its args and --zedmd-shades are known
	set_process(on)
	_palette = shade_palette(_color)


## A game offers a picture of its DMD under a name ("classic": the exact 128x32 dots, "256x64", "hd"); the platform
## sends the one the device and `--dmd-feed=` ask for. A viewport is resized to the device (nearest for the exact
## classic dots, Lanczos for anything else).
func publish(feed: String, viewport: Viewport) -> void:
	_feeds[feed] = viewport


func _source() -> Viewport:
	return _feeds.get(_feed_name, get_viewport())


func _start_feed(path: String) -> void:
	var run := OS.execute_with_pipe(path, _feed_args)
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


## The 4096 shades (0-15) of a 128x32 image, one byte per dot: the brightest channel, as a DMD's 16 levels.
static func shades_frame(image: Image) -> PackedByteArray:
	var frame := PackedByteArray()
	frame.resize(128 * 32)
	for y in 32:
		for x in 128:
			var dot := image.get_pixel(x, y)
			frame[y * 128 + x] = clampi(roundi(maxf(dot.r, maxf(dot.g, dot.b)) * 15.0), 0, 15)
	return frame


## The 12288-byte RGB frame of a 128x32 image: each dot's brightness as a shade, through the palette.
## Any other size (and the HD picture) keeps the full 8 bits: the brightness scales the colour smoothly.
func rgb_frame(image: Image, palette: PackedByteArray) -> PackedByteArray:
	var frame := PackedByteArray()
	frame.resize(WIDTH * HEIGHT * 3)
	var classic := WIDTH == 128 and HEIGHT == 32
	for y in HEIGHT:
		for x in WIDTH:
			var dot := image.get_pixel(x, y)
			var at := (y * WIDTH + x) * 3
			var level := maxf(dot.r, maxf(dot.g, dot.b))
			if classic:
				var shade := clampi(roundi(level * 15.0), 0, 15)
				frame[at] = palette[shade * 3]
				frame[at + 1] = palette[shade * 3 + 1]
				frame[at + 2] = palette[shade * 3 + 2]
			else:
				frame[at] = roundi(_color.r * level * 255.0)
				frame[at + 1] = roundi(_color.g * level * 255.0)
				frame[at + 2] = roundi(_color.b * level * 255.0)
	return frame


func _process(delta: float) -> void:
	_elapsed += delta
	if _elapsed < 1.0 / FPS:
		return
	_elapsed = 0.0
	var mpf := get_node_or_null("/root/MPF")       # GMC's autoload (looked up: the add-on loads without GMC)
	if not _feed and (mpf == null or not mpf.server._client):      # no MPF connected yet
		return
	var image := _source().get_texture().get_image()
	if image.get_width() != WIDTH or image.get_height() != HEIGHT:
		var classic := WIDTH == 128 and HEIGHT == 32
		image.resize(WIDTH, HEIGHT, Image.INTERPOLATE_NEAREST if classic else Image.INTERPOLATE_LANCZOS)
	var frame := shades_frame(image) if _shades and _feed and WIDTH == 128 and HEIGHT == 32 else rgb_frame(image, _palette)
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
