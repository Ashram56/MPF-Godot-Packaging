extends Control

## One PinUP Player screen (a layer of a PuP window, or the audio-only music screen), playing as PinUP
## Player does (vendored from Ashram56/Stern-SAM-Decryption tools/pup/runtime):
## - a play replaces what runs when its priority is >= the running one's, else it is dropped;
## - Loop column: "Loop" loops the file, "SetBG" makes it the screen's background and plays it now when its
##   priority is >= the running video's (else when that one ends), "StopFile" stops that file, "StopPlayer" stops the screen, "SkipSamePrty" drops the play when
##   the running video has the same priority;
## - when a video ends the background comes back; a pop-up layer (ForcePopBack) with no background hides;
## - a screen with CustomPos fills that box of its window (opts.box, fractions of the window);
## - a picture from the PuPOverlays playlist is an overlay: it stays over whatever plays on the screen (its
##   transparent parts show the video) until another overlay replaces it (inferred from PinUP Player's folder
##   convention: Transformers row 246 "Overlay - Default", D0 on the backglass).

const GozenPlayer := preload("res://pup/gozen_player.gd")

var number: int
var player: Node                    # the PuP player autoload (media, playlists)
var popup := false                  # ForcePop / ForcePopBack: visible only while something plays
var audio_only := false
var fit := "fit"
var align := 0.5
var bus := "sfx"
var volume_scale := 1.0

var fg = null                       # {playlist, file, path, priority, loop, volume}
var bg = null                       # {playlist, file}
var bg_playing := false

var _video: Control                 # VideoStreamPlayer, or gozen_player.gd (player.gozen: Linux, GDE GoZen)
var _image: TextureRect
var _overlay: TextureRect
var _audio: AudioStreamPlayer
var _aspect := 16.0 / 9.0
var _length_timer: SceneTreeTimer
var _serial := 0


func setup(p_player: Node, p_number: int, opts: Dictionary) -> void:
	player = p_player
	number = p_number
	name = "pup_screen_%d" % number
	popup = opts.get("popup", false)
	audio_only = opts.get("audio_only", false)
	fit = opts.get("fit", "fit")
	align = float(opts.get("align", 0.5))
	bus = opts.get("bus", "sfx")
	volume_scale = float(opts.get("volume", 100)) / 100.0
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	clip_contents = true
	set_anchors_preset(Control.PRESET_FULL_RECT)
	var box: Rect2 = opts.get("box", Rect2())
	if box.has_area():
		anchor_left = box.position.x
		anchor_top = box.position.y
		anchor_right = box.end.x
		anchor_bottom = box.end.y
		offset_left = 0
		offset_top = 0
		offset_right = 0
		offset_bottom = 0
	if audio_only:
		_audio = AudioStreamPlayer.new()
		_audio.bus = bus
		_audio.finished.connect(_on_finished.bind(-1))
		add_child(_audio)
	else:
		if player.gozen:
			_video = GozenPlayer.new()
		else:
			_video = VideoStreamPlayer.new()
			_video.expand = true
		_video.bus = bus
		_video.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_video.finished.connect(_on_finished.bind(-1))
		add_child(_video)
		_image = TextureRect.new()
		_image.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		_image.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_image.hide()
		add_child(_image)
		_overlay = TextureRect.new()
		_overlay.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		_overlay.stretch_mode = TextureRect.STRETCH_SCALE
		_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
		_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_overlay.hide()
		add_child(_overlay)
		resized.connect(_layout)
	visible = not popup
	if opts.get("bg_playlist", ""):
		bg = {"playlist": opts.bg_playlist, "file": opts.get("bg_file", "")}


func start_background() -> void:
	if bg and fg == null:
		_play_bg()

# ------------------------------------------------------------------ commands

func command(cmd: Dictionary) -> void:
	var mode := str(cmd.get("mode", "")).to_lower()
	if not audio_only and str(cmd.get("playlist", "")).to_lower() == "pupoverlays":
		var path: String = player.pick(cmd.get("playlist", ""), cmd.get("file", ""))
		_overlay.texture = player.load_image(path) if path != "" and mode not in ["stopfile", "stopplayer"] else null
		_overlay.visible = _overlay.texture != null
		return
	var priority := int(cmd.get("priority", 0))
	match mode:
		"stopfile":
			if fg != null and _matches(fg, cmd):
				_stop_fg()
			return
		"stopplayer":
			if fg != null:
				_stop_fg()
			elif popup:
				_stop_media()
				hide()
			return
		"setbg":
			bg = {"playlist": cmd.get("playlist", ""), "file": cmd.get("file", "")}
			if fg == null or priority >= int(fg.priority):
				fg = null                   # plays now over a lower or equal priority video (a looping one too)
				_play_bg()
			return
		"skipsameprty":
			if fg != null and int(fg.priority) == priority:
				return
	if fg != null and priority < int(fg.priority):
		return
	var path: String = player.pick(cmd.get("playlist", ""), cmd.get("file", ""))
	if path == "":
		return
	fg = {"playlist": cmd.get("playlist", ""), "file": path.get_file(), "path": path, "priority": priority,
		"loop": mode == "loop", "volume": player.volume_of(cmd)}
	_start(path, fg.loop, fg.volume)
	var length := float(cmd.get("length", 0))
	if length > 0:
		var serial := _serial
		get_tree().create_timer(length).timeout.connect(func():
			if serial == _serial and fg != null:
				_stop_fg())


func _matches(entry: Dictionary, cmd: Dictionary) -> bool:
	var file := str(cmd.get("file", ""))
	if file != "":
		return entry.file.get_basename().to_lower() == file.get_basename().to_lower()
	return entry.playlist.to_lower() == str(cmd.get("playlist", "")).to_lower()

# ------------------------------------------------------------------ playback

func _stop_fg() -> void:
	fg = null
	if bg:
		_play_bg()
	else:
		_stop_media()
		if popup:
			hide()


func _play_bg() -> void:
	var path: String = player.pick(bg.playlist, bg.file)
	if path == "":
		_stop_media()
		return
	bg_playing = true
	# a background named by its file loops that file; a playlist background moves to its next file
	_start(path, bg.file != "", player.volume_of({"playlist": bg.playlist}))


func _start(path: String, loop: bool, volume: float) -> void:
	_serial += 1
	bg_playing = fg == null
	var db := linear_to_db(maxf(volume * volume_scale, 0.0001))
	if audio_only:
		var stream = player.load_audio(path)
		if stream == null:
			return
		if "loop" in stream:
			stream.loop = loop
		_audio.stream = stream
		_audio.volume_db = db
		_audio.play()
		return
	if popup:
		show()
	var ext := path.get_extension().to_lower()
	if ext in ["png", "jpg", "jpeg", "bmp", "webp"]:
		_video.stop()
		_video.hide()
		_image.texture = player.load_image(path)
		_image.show()
		if _image.texture:
			_aspect = float(_image.texture.get_width()) / maxf(1.0, _image.texture.get_height())
		_layout()
		return
	_image.hide()
	_aspect = player.aspect_of(path)
	_video.show()
	_layout()
	if player.gozen:
		# no stop() first: the previous video's last frame stays up while the next one opens (in the background,
		# a moment with the Jetson's hardware decoder), instead of a black screen; a stopped player shows nothing
		_video.open(path, loop, db)
		return
	_video.stop()
	_video.stream = player.video_stream(path)
	_video.volume_db = db
	if "loop" in _video:
		_video.loop = loop
	_video.play()


func _stop_media() -> void:
	_serial += 1
	bg_playing = false
	if audio_only:
		_audio.stop()
		return
	_video.stop()
	_image.hide()


func _on_finished(_unused) -> void:
	if fg != null:
		if fg.loop:
			_restart()
			return
		_stop_fg()
		return
	if bg and bg_playing:
		if bg.file != "":
			_restart()
		else:
			_play_bg()


func _restart() -> void:
	if audio_only:
		_audio.play()
	else:
		_video.play()

# ------------------------------------------------------------------ layout

func _layout() -> void:
	if audio_only:
		return
	var area := size
	var w := area.x
	var h := area.y
	if fit != "stretch" and area.x > 0 and area.y > 0:
		var fitted := area.x / area.y > _aspect
		if fit == "fill":
			fitted = not fitted
		if fitted:
			w = area.y * _aspect
		else:
			h = area.x / _aspect
	var rect := Rect2((area.x - w) * 0.5, (area.y - h) * align, w, h)
	for node in [_video, _image]:
		node.position = rect.position
		node.size = rect.size
