extends Node

## The PuP Pack player (autoload "Pup"): game/pup.cfg's windows, the PuP Pack's screens and playlists, and the
## "pup_play" commands MPF sends (game/pup_runtime/mode.py). Vendored from Ashram56/Stern-SAM-Decryption
## tools/pup/runtime: a game sets everything in game/pup.cfg, it does not edit this file.
##
## Windows ([pup] windows, each on the monitor its section gives it):
## - a layered window ([<name>] layers=[PuP screen numbers, bottom first]): those PuP screens stacked. A screen
##   whose screens.pup row has CustomPos ("parent,x,y,w,h" in percent) sits in that part of the window; a
##   ForcePop / ForcePopBack screen is visible only while something plays on it;
## - the DMD window ([<name>] dmd=true): the game's 128x32 DMD (the main window's picture), drawn larger in the
##   pack's DMD panel art (background="frame"), on black, or over a scene of the game's own (background =
##   "res://....gd", a Control with set_dmd_rect(Rect2)).
## [pup] optional=[window names] are the windows [pup] third_screen turns on and off (a topper).
## [pup] music_screen (no window) plays the pack's music when [pup] ost_music. Commands for a screen that is not
## shown are dropped. Screens the pack's option set leaves "off" are shown when a window lists them.
## Media come from the converted copy of the pack (scripts/gen_pup.py, manifest.json): Theora videos, the
## pack's own mp3 and pictures, all loaded at run time (nothing is imported into the Godot project); with a video
## add-on (native_video, GDE GoZen) the pack's mp4s play as they are.

const CONFIG_FILES := ["res://pup.cfg", "res://pup.local.cfg"]
const DOTS_SHADER := preload("res://pup/dmd_dots.gdshader")
const PupScreen := preload("res://pup/pup_screen.gd")
const OFF := ["0", "false", "no", "off"]

var cfg := ConfigFile.new()
var enabled := false
var pack_dir := ""
var media_dir := ""
var manifest := {}                  # pack path ("Drain/Drain1.mp4") -> {out, w, h, duration}
var folders := {}                   # playlist folder (lower case) -> [pack paths], sorted
var playlists := {}                 # playlist folder (lower case) -> {alpha_sort, volume}
var screens := {}                   # PuP screen number -> PupScreen
var windows := {}                   # window name -> Window
var music_screen := -1
var _next := {}                     # playlist -> next index (AlphaSort playlists)
var _last := {}                     # playlist -> last pick (random playlists)
var _audio_cache := {}
var _audio_lock := Mutex.new()      # _audio_cache: the music preload fills it on a worker (_preload_audio())
## Which add-on plays the pack's mp4s without conversion (_pick_video_player()), else Godot plays Theora copies:
## - GDE GoZen (Linux and Windows): FFmpeg decoding on the GPU (Direct3D 11 Video / DXVA2 on Windows, the Jetson's
##   decoder with libnvmpi); the screens then use gozen_player.gd;
## - native_video (macOS, and Windows' fallback): [pup] video_player="native" or <env>_VIDEO_PLAYER=native.
var native_video := false
var gozen := false


func _ready() -> void:
	if Engine.is_editor_hint():
		return
	# answered even with the PuP off, so MPF's hello is never "unhandled"; pup_ready only when it is on
	MPF.server.registered_handlers["pup_play"] = [Callable(self, "_on_pup_play")]
	MPF.server.registered_handlers["pup_hello"] = [Callable(self, "_on_pup_hello")]
	if not _load_config():
		return
	_pick_video_player()
	var root := ProjectSettings.globalize_path("res://").path_join("..").simplify_path()
	pack_dir = root.path_join(setting("pup", "pack_dir", "pup_pack"))
	media_dir = root.path_join(setting("pup", "media_dir", "pup_media"))
	if not _load_media():
		return
	enabled = true
	_load_playlists()
	call_deferred("_build")


func _load_config() -> bool:
	for path in CONFIG_FILES:
		if FileAccess.file_exists(path):
			var part := ConfigFile.new()
			if part.load(path) == OK:
				for section in part.get_sections():
					for key in part.get_section_keys(section):
						cfg.set_value(section, key, part.get_value(section, key))
	var prefix := str(setting("pup", "env", ""))
	for name in [prefix + "_PUP" if prefix != "" else "PUP", "PUP"]:
		if OS.get_environment(name).to_lower() in OFF:
			return false
	return bool(setting("pup", "enabled", false))


func _pick_video_player() -> void:
	var has_native := ClassDB.class_exists("NativeVideoStream")
	var has_gozen := ClassDB.class_exists("GoZenVideo") \
		and ResourceLoader.exists("res://addons/gde_gozen/video_playback.gd")
	var prefix := str(setting("pup", "env", ""))
	var want := OS.get_environment((prefix + "_" if prefix != "" else "") + "VIDEO_PLAYER").strip_edges().to_lower()
	if want.is_empty():
		want = str(setting("pup", "video_player", "")).strip_edges().to_lower()
	gozen = has_gozen and not (want == "native" and has_native)
	native_video = has_native and not gozen
	print("PuP video player: %s" % ("GDE GoZen" if gozen else ("native_video" if native_video else "Godot (Theora)")))


func setting(section: String, key: String, default = null):
	return cfg.get_value(section, key, default)


func _load_media() -> bool:
	var path := media_dir.path_join("manifest.json")
	if not FileAccess.file_exists(path):
		push_warning("PuP: no converted media at %s (run scripts/gen_pup.py): PuP off" % media_dir)
		return false
	var data = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(data) != TYPE_DICTIONARY:
		push_warning("PuP: %s is not valid: PuP off" % path)
		return false
	manifest = data.get("files", {})
	for key in manifest.keys():
		var folder: String = key.get_base_dir().to_lower()
		if not folders.has(folder):
			folders[folder] = []
		folders[folder].append(key)
	for folder in folders:
		folders[folder].sort_custom(func(a, b): return a.naturalnocasecmp_to(b) < 0)
	return true


func _load_playlists() -> void:
	for row in _read_csv(pack_dir.path_join("playlists.pup")):
		playlists[row.get("Folder", "").to_lower()] = {
			"alpha_sort": row.get("AlphaSort", "0") == "1",
			"volume": float(row.get("Volume", "100") if row.get("Volume", "") != "" else "100")}


func _read_csv(path: String) -> Array:
	var rows := []
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_warning("PuP: cannot read %s" % path)
		return rows
	var head := f.get_csv_line()
	if head.size() > 0:
		head[0] = head[0].trim_prefix("﻿")
	while not f.eof_reached():
		var line := f.get_csv_line()
		if line.size() < 2:
			continue
		var row := {}
		for i in range(mini(head.size(), line.size())):
			row[head[i].strip_edges()] = line[i].strip_edges()
		rows.append(row)
	return rows

# ------------------------------------------------------------------ windows and screens

func _build() -> void:
	get_tree().root.gui_embed_subwindows = false
	var defaults := {}
	for row in _read_csv(pack_dir.path_join("screens.pup")):
		defaults[int(row.get("ScreenNum", "-1"))] = row
	var video_volume := float(setting("pup", "video_volume", 100))
	var optional: Array = setting("pup", "optional", [])
	var third := bool(setting("pup", "third_screen", true))
	for name in setting("pup", "windows", ["backglass", "dmd", "topper"]):
		if not bool(setting(name, "enabled", true)) or (name in optional and not third):
			continue
		if bool(setting(name, "dmd", false)):
			_make_dmd_window(name)
		else:
			_make_layered_window(name, defaults, video_volume)
	if str(setting("pup", "layout", "stack")) == "stack":
		_stack_windows()
	if windows.has(_dmd_name):
		_layout_dmd()
		windows[_dmd_name].size_changed.connect(_layout_dmd)
	music_screen = int(setting("pup", "music_screen", 15))
	if bool(setting("pup", "ost_music", true)) and music_screen >= 0:
		var music := PupScreen.new()
		var row: Dictionary = defaults.get(music_screen, {})
		music.setup(self, music_screen, {"audio_only": true, "bus": str(setting("pup", "music_bus", "music")),
			"volume": float(setting("pup", "music_volume", 100)),
			"bg_playlist": row.get("PlayList", ""), "bg_file": row.get("PlayFile", "")})
		add_child(music)
		screens[music_screen] = music
		_preload_audio()
	for n in screens:
		screens[n].start_background()
	if windows.has(_dmd_name) and bool(setting(_dmd_name, "hide_main_window", true)):
		get_tree().root.mode = Window.MODE_MINIMIZED
	_vsync_one_window()
	var placed := []
	for name in windows:
		placed.append("%s %s at %s" % [name, windows[name].size, windows[name].position])
	print("PuP: windows %s, screens %s" % [", ".join(placed), screens.keys()])
	_start_capture()


## Vsync on the first PuP window only: with vsync on every window, each one's present waits for its own vertical
## blank, so a frame took one screen refresh per window (15 FPS with four windows on a Jetson Xavier NX). One
## vsync'd window still paces the frames of all of them.
func _vsync_one_window() -> void:
	if windows.is_empty() or DisplayServer.window_get_vsync_mode() == DisplayServer.VSYNC_DISABLED:
		return
	var keep: Window = windows.values()[0]
	var others: Array = [get_tree().root] + windows.values()
	for w: Window in others:
		if w != keep:
			DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED, w.get_window_id())


## run.py --dmd-size WxH (Godot's --resolution, which sizes the main window): the size of the DMD window the
## player sees, which is this one when the PuP is on. Vector2i.ZERO when not given.
func _dmd_size_arg() -> Vector2i:
	var root_size := get_tree().root.size
	var default := Vector2i(int(ProjectSettings.get_setting("display/window/size/window_width_override", 0)),
		int(ProjectSettings.get_setting("display/window/size/window_height_override", 0)))
	return root_size if root_size != default and root_size.x > 0 and root_size.y > 0 else Vector2i.ZERO


func _make_window(section: String) -> Window:
	var w := Window.new()
	w.name = "pup_" + section
	w.title = "%s - %s" % [str(setting("pup", "title", "PuP")), section]
	w.transient = false
	w.unresizable = false
	w.borderless = bool(setting(section, "borderless", false))
	w.close_requested.connect(func(): pass)
	w.window_input.connect(_forward_input)
	var screen := clampi(int(setting(section, "screen", 0)), 0, DisplayServer.get_screen_count() - 1)
	var size_cfg = setting(section, "size", [800, 600])
	var pos_cfg = setting(section, "position", [0, 0])
	w.size = Vector2i(int(size_cfg[0]), int(size_cfg[1]))
	if section == _dmd_name and _dmd_size_arg() != Vector2i.ZERO:
		w.size = _dmd_size_arg()
	w.position = DisplayServer.screen_get_position(screen) + Vector2i(int(pos_cfg[0]), int(pos_cfg[1]))
	var back := ColorRect.new()
	back.color = Color.BLACK
	back.set_anchors_preset(Control.PRESET_FULL_RECT)
	back.mouse_filter = Control.MOUSE_FILTER_IGNORE
	w.add_child(back)
	add_child(w)
	if bool(setting(section, "fullscreen", false)):
		w.current_screen = screen
		w.mode = Window.MODE_FULLSCREEN
	windows[section] = w
	return w


## [pup] layout="stack": the windows one under the other ([pup] windows order) at the left of the first one's
## monitor, as wide as fits its height (each keeps the aspect of its size in pup.cfg; run.py --dmd-size keeps
## the DMD's own size). Fullscreen windows stay out of the stack.
func _stack_windows() -> void:
	var order: Array[Window] = []
	for name in windows:
		if windows[name].mode != Window.MODE_FULLSCREEN:
			order.append(windows[name])
	if order.is_empty():
		return
	var screen := clampi(int(setting(windows.keys()[0], "screen", 0)), 0, DisplayServer.get_screen_count() - 1)
	var area := DisplayServer.screen_get_usable_rect(screen)
	if area.size.x <= 0 or area.size.y <= 0:
		return
	var fixed := _dmd_size_arg()
	var free_h := float(area.size.y)
	var ratio := 0.0                        # sum of height/width of the windows that take the common width
	for w in order:
		free_h -= _title_height(w)
		if w == windows.get(_dmd_name) and fixed != Vector2i.ZERO:
			free_h -= fixed.y
		else:
			ratio += float(w.size.y) / maxf(1.0, float(w.size.x))
	var width := int(minf(float(area.size.x), free_h / ratio)) if ratio > 0.0 else 0
	var y := area.position.y
	for w in order:
		if not (w == windows.get(_dmd_name) and fixed != Vector2i.ZERO):
			w.size = Vector2i(width, int(round(width * float(w.size.y) / maxf(1.0, float(w.size.x)))))
		y += _title_height(w)
		w.position = Vector2i(area.position.x, y)
		y += w.size.y


func _title_height(w: Window) -> int:
	if w.borderless:
		return 0
	var title := w.get_size_with_decorations().y - w.size.y
	return title if title > 0 else 32


## CustomPos "parent,x,y,w,h" (percent of the parent screen) -> Rect2 in 0..1 of the window, or an empty Rect2.
static func custom_pos(text: String) -> Rect2:
	var parts := text.split(",")
	if parts.size() < 5:
		return Rect2()
	return Rect2(float(parts[1]) / 100.0, float(parts[2]) / 100.0, float(parts[3]) / 100.0, float(parts[4]) / 100.0)


func _make_layered_window(section: String, defaults: Dictionary, volume: float) -> void:
	var w := _make_window(section)
	for n in setting(section, "layers", []):
		var row: Dictionary = defaults.get(int(n), {})
		var mode := str(row.get("Active", "")).to_lower()
		var box := custom_pos(str(row.get("CustomPos", "")))
		var layer := PupScreen.new()
		layer.setup(self, int(n), {"popup": mode.begins_with("forcepop"),
			"fit": "stretch" if box.has_area() else setting(section, "fit", "fit"),
			"align": setting(section, "align", 0.5), "bus": str(setting("pup", "video_bus", "sfx")),
			"volume": volume, "box": box,
			"bg_playlist": row.get("PlayList", ""), "bg_file": row.get("PlayFile", "")})
		w.add_child(layer)
		screens[int(n)] = layer


var _dmd_name := ""
var _dmd_frame: TextureRect             # the pack's DMD panel art (background="frame")
var _dmd_crop := Rect2i()
var _dmd_scene: Control                 # a scene of the game's own behind the DMD (background="res://...gd")
var _dmd_view: TextureRect              # the game's DMD (the main window's picture)


func _make_dmd_window(section: String) -> void:
	_dmd_name = section
	var w := _make_window(section)
	var background := str(setting(section, "background", "frame"))
	var frame_path := str(setting(section, "frame_image", ""))
	if background.begins_with("res://"):
		var script = load(background)
		if script:
			_dmd_scene = script.new()
			w.add_child(_dmd_scene)
		else:
			push_warning("PuP: cannot load the DMD background %s" % background)
	elif background == "frame" and frame_path != "":
		var image := Image.load_from_file(pack_dir.path_join(frame_path))
		if image:
			var c = setting(section, "frame_crop", [0, 0, image.get_width(), image.get_height()])
			_dmd_crop = Rect2i(int(c[0]), int(c[1]), int(c[2]), int(c[3]))
			_dmd_frame = TextureRect.new()
			_dmd_frame.texture = ImageTexture.create_from_image(image.get_region(_dmd_crop))
			_dmd_frame.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			_dmd_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
			w.add_child(_dmd_frame)
		else:
			push_warning("PuP: cannot load the DMD frame %s" % frame_path)
	_dmd_view = TextureRect.new()
	_dmd_view.name = "dmd"
	_dmd_view.texture = get_tree().root.get_texture()
	_dmd_view.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_dmd_view.stretch_mode = TextureRect.STRETCH_SCALE
	# a game's HD DMD mode (autoload DmdMode with hd=true) draws smooth text at its window's size and has its own dots
	var dmd_mode = get_node_or_null("/root/DmdMode")
	var hd: bool = dmd_mode != null and bool(dmd_mode.get("hd"))
	_dmd_view.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR if hd else CanvasItem.TEXTURE_FILTER_NEAREST
	_dmd_view.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if bool(setting(section, "dots", true)) and not hd:
		var mat := ShaderMaterial.new()
		mat.shader = DOTS_SHADER
		mat.set_shader_parameter("dmd_size", Vector2(128, 32))
		_dmd_view.material = mat
	w.add_child(_dmd_view)


## Background and DMD laid out for the DMD window's current size (again on every resize).
func _layout_dmd() -> void:
	var area := Vector2(windows[_dmd_name].size)
	var dmd_rect := Rect2(Vector2.ZERO, area)
	if _dmd_scene:
		# a 4:1 DMD in the middle, dmd_width of the window's width, at most half its height
		var w := minf(area.x * float(setting(_dmd_name, "dmd_width", 0.6)), area.y * 0.5 * 4.0)
		dmd_rect = Rect2((area - Vector2(w, w / 4.0)) * 0.5, Vector2(w, w / 4.0))
		_dmd_scene.position = Vector2.ZERO
		_dmd_scene.size = area
		if _dmd_scene.has_method("set_dmd_rect"):
			_dmd_scene.set_dmd_rect(dmd_rect)
	elif _dmd_frame:
		var scale := minf(area.x / _dmd_crop.size.x, area.y / _dmd_crop.size.y)
		var origin := (area - Vector2(_dmd_crop.size) * scale) * 0.5
		_dmd_frame.position = origin
		_dmd_frame.size = Vector2(_dmd_crop.size) * scale
		var c := _dmd_crop
		var r = setting(_dmd_name, "dmd_rect", [c.position.x, c.position.y, c.size.x, c.size.y])
		dmd_rect = Rect2(origin + (Vector2(float(r[0]), float(r[1])) - Vector2(c.position)) * scale,
			Vector2(float(r[2]), float(r[3])) * scale)
	# the game's 128x32 DMD, 4:1, centred in its rect
	var dmd_size := Vector2(128, 32)
	var k := minf(dmd_rect.size.x / dmd_size.x, dmd_rect.size.y / dmd_size.y)
	_dmd_view.size = dmd_size * k
	_dmd_view.position = dmd_rect.position + (dmd_rect.size - _dmd_view.size) * 0.5


func _forward_input(event: InputEvent) -> void:
	# keys pressed in a PuP window drive the game like keys in the DMD window (gmc.cfg [keyboard], Esc)
	get_tree().root.push_input(event)

# ------------------------------------------------------------------ MPF

func _on_pup_hello(_message: Dictionary) -> void:
	if not enabled or windows.is_empty():
		return
	MPF.server.send_event_with_args("pup_ready", {"ost": 1 if screens.has(music_screen) else 0}, false)


func _on_pup_play(message: Dictionary) -> void:
	var n := int(message.get("screen", -1))
	if screens.has(n):
		screens[n].command(message)

# ------------------------------------------------------------------ media

## Pack path of the file a play names, or the next file of its playlist; returns the path it plays from.
func pick(playlist: String, file: String) -> String:
	var key := ""
	if file != "":
		key = _find(playlist, file)
	else:
		var files: Array = folders.get(playlist.to_lower(), [])
		if files.is_empty():
			return ""
		var info: Dictionary = playlists.get(playlist.to_lower(), {})
		if info.get("alpha_sort", false):
			# in order from a random first file: AlphaSort playlists are numbered variants, and starting at 1
			# every boot showed the same one first
			var i: int = _next.get(playlist, randi()) % files.size()
			_next[playlist] = i + 1
			key = files[i]
		else:
			var i := randi() % files.size()
			if files.size() > 1 and files[i] == _last.get(playlist, ""):
				i = (i + 1 + randi() % (files.size() - 1)) % files.size()
			key = files[i]
			_last[playlist] = key
	if key == "":
		push_warning("PuP: no file %s in playlist %s" % [file, playlist])
		return ""
	return media_path(key)


## Where a pack file plays from: the pack's own video with the native_video add-on or GoZen, else the converted copy.
func media_path(key: String) -> String:
	var entry: Dictionary = manifest[key]
	if (native_video or gozen) and entry.has("w") and key.get_extension().to_lower() in ["mp4", "m4v", "mov"]:
		return pack_dir.path_join(key)
	if not entry.has("out"):
		push_warning("PuP: %s was not converted (gen_pup.py --native) and no video add-on is loaded" % key)
		return ""
	return media_dir.path_join(entry.out)


func video_stream(path: String) -> VideoStream:
	var stream: VideoStream = ClassDB.instantiate("NativeVideoStream") if path.get_extension().to_lower() != "ogv" \
		else VideoStreamTheora.new()
	stream.file = path
	return stream


func _find(playlist: String, file: String) -> String:
	var want := file.get_basename().to_lower()
	for key in folders.get(playlist.to_lower(), []):
		if key.get_file().get_basename().to_lower() == want:
			return key
	return ""


func volume_of(cmd: Dictionary) -> float:
	if cmd.has("volume") and str(cmd.volume) != "":
		return float(cmd.volume) / 100.0
	return float(playlists.get(str(cmd.get("playlist", "")).to_lower(), {}).get("volume", 100.0)) / 100.0


func aspect_of(path: String) -> float:
	for key in manifest:
		var entry: Dictionary = manifest[key]
		var here := pack_dir.path_join(key) == path or media_dir.path_join(entry.get("out", key)) == path
		if here and entry.get("h", 0) > 0:
			return float(entry.w) / float(entry.h)
	return 16.0 / 9.0


func load_audio(path: String) -> AudioStream:
	_audio_lock.lock()
	var kept = _audio_cache.get(path)
	_audio_lock.unlock()
	if kept != null:
		return kept
	return _read_audio(path)


## The pack's music (mp3, ogg) read and decoded on a worker at start, one file after the other, so no first play
## reads it on the main thread (20-60 ms per mp3 on a Jetson Xavier NX). Memory: the same as after a game that played them
## all, since every played stream stays cached anyway.
func _preload_audio() -> void:
	var paths: Array[String] = []
	for key in manifest:
		if key.get_extension().to_lower() in ["mp3", "ogg"]:
			var path := media_path(key)
			if path != "":
				paths.append(path)
	if paths.is_empty():
		return
	WorkerThreadPool.add_task(func():
		var t0 := Time.get_ticks_msec()
		var bytes := 0
		for path in paths:
			var stream := _read_audio(path)
			if stream is AudioStreamMP3:
				bytes += stream.data.size()
		print("PuP: %d music files preloaded (%.1f MB) in %d ms" % [
			paths.size(), bytes / 1048576.0, Time.get_ticks_msec() - t0]),
		false, "PuP music preload")


func _read_audio(path: String) -> AudioStream:
	_audio_lock.lock()
	var kept = _audio_cache.get(path)
	_audio_lock.unlock()
	if kept != null:
		return kept
	var data := FileAccess.get_file_as_bytes(path)
	if data.is_empty():
		push_warning("PuP: cannot read %s" % path)
		return null
	var stream: AudioStream
	match path.get_extension().to_lower():
		"mp3":
			stream = AudioStreamMP3.new()
			stream.data = data
		"ogg":
			stream = AudioStreamOggVorbis.load_from_buffer(data)
	_audio_lock.lock()
	if _audio_cache.has(path):          # read on both threads at once: keep the first
		stream = _audio_cache[path]
	else:
		_audio_cache[path] = stream
	_audio_lock.unlock()
	return stream


func load_image(path: String) -> Texture2D:
	var image := Image.load_from_file(path)
	return ImageTexture.create_from_image(image) if image else null

# ------------------------------------------------------------------ checks without a screen

## godot --path game -- --pup-capture-dir=/abs/path [--pup-capture-every-ms=2000]: saves every PuP window
## as <window>_NNNN.png (scripts/pup_check.py).
func _start_capture() -> void:
	var dir := ""
	var every := 2000
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--pup-capture-dir="):
			dir = arg.split("=", true, 1)[1]
		elif arg.begins_with("--pup-capture-every-ms="):
			every = int(arg.split("=", true, 1)[1])
	if dir == "":
		return
	DirAccess.make_dir_recursive_absolute(dir)
	var timer := Timer.new()
	timer.wait_time = every / 1000.0
	var count := [0]
	timer.timeout.connect(func():
		for name in windows:
			windows[name].get_texture().get_image().save_png("%s/%s_%04d.png" % [dir, name, count[0]])
		count[0] += 1)
	add_child(timer)
	timer.start()
