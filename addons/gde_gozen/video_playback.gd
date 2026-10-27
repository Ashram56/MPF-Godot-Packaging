class_name VideoPlayback
extends Control
## Video playback and seeking inside of Godot.
##
## To use this node, just add it anywhere and resize it to the desired size. Use the function [code]set_video_path(new_path)[/code] and the video will load. Take in mind that long video's can take a second or longer to load. If this is an issue you can preload the Video on startup of your project and set the video variable yourself, just remember to use the function [code]update_video()[/code] before the moment that you'd like to use it.

enum COLOR_PROFILE { AUTO, BT470, BT601, BT709, BT2020, BT2100 }
enum STREAM_TYPE { VIDEO = 0, AUDIO = 1, SUBTITLE = 2 }


signal frame_changed(frame_nr: int) ## Emitted when the current frame has changed, for showing and skipped frames.
signal next_frame_called(frame_nr: int) ## Emitted when a new frame is showing.

signal video_loaded ## Emitted when the video is ready for playback.
signal video_ended ## Emitted when the last frame has been shown.

signal playback_started ## Emitted when playback started/resumed.
signal playback_paused ## Emitted when playback is paused.
signal playback_ready ## Emitted when the node if fully setup and ready for playback.


const SHADER_PATH_COMPATIBILITY: String = "res://addons/gde_gozen/yuv_to_rgb_compatibility.gdshader"
const SHADER_PATH_FORWARD: String = "res://addons/gde_gozen/yuv_to_rgb_forward.gdshader"
## The Compatibility shader's common case (no rotation, interlacing or alpha): ~3x cheaper on a Raspberry Pi 4.
const SHADER_FAST: Shader = preload("res://addons/gde_gozen/yuv_to_rgb_fast.gdshader")
const SHADER_FAST_NV12: Shader = preload("res://addons/gde_gozen/yuv_to_rgb_fast_nv12.gdshader")
const PLAYBACK_SPEED_MIN: float = 0.25
const PLAYBACK_SPEED_MAX: float = 4
const AUDIO_OFFSET_THRESHOLD: float = 0.1

## Vector2(min, max) speed to override PLAYBACK_SPEED_MIN and PLAYBACK_SPEED_MAX constants
## Ignored if ZERO
@export var playback_speed_override: Vector2 = Vector2.ZERO

@export_file var path: String = "": set = set_video_path ## Full path to video file.
@export var enable_audio: bool = true ## Enable/Disable audio playback. When setting this on false before loading the audio, the audio playback won't be loaded meaning that the video will load faster. If you want audio but only disable it at certain moments, switch this value to false *after* the video is loaded.
@export var audio_speed_to_sync: bool = false ## Enable/Disable a slight audio playback speed increase/reduction when syncing audio and video to avoid a hard cut.
@export var enable_auto_play: bool = false ## Enable/disable auto video playback.
@export_range(PLAYBACK_SPEED_MIN, PLAYBACK_SPEED_MAX, 0.05, "or_less", "or_greater")
var playback_speed: float = 1.0: set = set_playback_speed ## Adjust the video playback speed, 0.5 = half the speed and 2 = double the speed.
@export var pitch_adjust: bool = true: set = set_pitch_adjust ## When changing playback speed, do you want the pitch to change or stay the same?
@export var loop: bool = false ## Enable/disable looping on video_ended.
@export_group("Extra's")
@export var color_profile: COLOR_PROFILE = COLOR_PROFILE.AUTO: set = _set_color_profile ## Force a specific color profile if needed.
@export var decode_to_display_size: bool = false ## With a hardware decoder that can scale (GoZenVideo.set_target_size(), the Jetson's): decode at this node's size when the video opens, instead of the file's full size. Fewer pixels to copy and upload per frame; a later resize scales the picture as usual.
@export var debug: bool = false ## Enable/disable the printing of debug info.

var video: GoZenVideo = null ## Video class object of GDE GoZen which interacts with video files through FFmpeg.

var video_texture: TextureRect = TextureRect.new() ## The texture rect is the view of the video, you can adjust the scaling options as you like, it is set to always center and scale the image to fit within the main VideoPlayback node size.
var audio_player: AudioStreamPlayer = AudioStreamPlayer.new() ## Audio player is the AudioStreamPlayer which handles the audio playback for the video, only mess with the settings if you know what you are doing and know what you'd like to achieve.

var is_playing: bool = false ## Bool to check if the video is currently playing or not.
var current_frame: int = 0: set = _set_current_frame ## Current frame number which the video playback is at.

var video_streams: PackedInt32Array = [] ## List of video streams in the video file.
var audio_streams: PackedInt32Array = [] ## List of audio streams in the video file.
var subtitle_streams: PackedInt32Array = [] ## List of subtitle streams in the video file.
var chapters: Array[Chapter] = [] ## List of chapters in the video file.

var y_texture: ImageTexture
var u_texture: ImageTexture
var v_texture: ImageTexture
var a_texture: ImageTexture

var _time_elapsed: float = 0.
var _frame_time: float = 0
var _skips: int = 0

var _rotation: int = 0
var _padding: int = 0
var _frame_rate: float = 0.
var _frame_count: int = 0
var _has_alpha: bool = false

var _resolution: Vector2i = Vector2i.ZERO
var _shader_material: ShaderMaterial = null

var _video_thread: int = -1
var _opened_audio: Array = [] ## The audio stream _open_video() opens on the worker thread, taken on the main one.
var _release_tasks: Array[int] = [] ## Worker tasks freeing closed videos (see close()).
var _abandoned: Array = [] ## [task, [video]]: videos closed while a worker still opened or restarted them (see close()).
var _restart_thread: int = -1 ## Worker task seeking back to the first frame (see restart()).
const QUEUE_FRAMES: int = 3 ## Frames decoded ahead per video (see _process()).
var _decode_task: int = -1 ## Worker task decoding the next frames into _queue (see _fill_queue()).
var _decoded: int = 0 ## The last frame number decoded (or being decoded) into _queue.
var _queue: Array[Dictionary] = [] ## Decoded frames not shown yet, oldest first: {"frame": int, "planes": Array}.
var _queue_mutex: Mutex = Mutex.new()
var _nv12: bool = false ## The decoder gives NV12: u_data holds U and V (RG8), there is no v plane to upload.
## With a separate render thread, RenderingServer.texture_2d_update() runs later, on that thread, while the next decode
## may already write into GoZen's images: a frame shown straight from GoZen (after a seek or restart) is then copied.
## (Queued frames always are.)
static var _copy_planes: bool = int(ProjectSettings.get_setting("rendering/driver/threads/thread_model", 1)) == 2
## Zero-copy (GoZenVideo.is_zero_copy(): the Raspberry Pi 4's hardware decoder with the Compatibility renderer): queued
## frames stay in the decoder's buffers ({"frame": int, "held": id}) and are shown as GPU textures of those buffers,
## nothing copied or uploaded. Late frames are skipped instead of slipping the clock. show_held() makes GL calls: with a
## separate render thread it runs there (RenderingServer.call_on_render_thread()).
var _zero_copy: bool = false
var _held_bound: bool = false ## The shader samples a held frame's textures, not y_texture/u_texture/v_texture.
var _clock: float = 0.0 ## Seconds of video played; frame n is due at n / _frame_rate (playback_speed moves it).
## The sound's output latency when the audio driver reports none (ALSA on a Raspberry Pi 4 says 0 while its buffer
## holds about 0.1 s): GOZEN_AUDIO_LATENCY (seconds) if set, else audio/driver/output_latency (ms).
static var _fallback_latency: float = float(OS.get_environment("GOZEN_AUDIO_LATENCY")) \
		if OS.get_environment("GOZEN_AUDIO_LATENCY") != "" \
		else float(ProjectSettings.get_setting("audio/driver/output_latency", 15)) / 1000.0
var _audio_pitch_effect: AudioEffectPitchShift = AudioEffectPitchShift.new()

var _ignore_path_setter: bool = false



#------------------------------------------------ TREE FUNCTIONS
func _enter_tree() -> void:
	var empty_image: Image = Image.create_empty(2,2,false, Image.FORMAT_R8)

	y_texture = ImageTexture.create_from_image(empty_image)
	u_texture = ImageTexture.create_from_image(empty_image)
	v_texture = ImageTexture.create_from_image(empty_image)
	a_texture = ImageTexture.create_from_image(empty_image)

	_shader_material = ShaderMaterial.new()
	if RenderingServer.get_current_rendering_method() == "forward_plus" and ProjectSettings.get_setting("rendering/viewport/hdr_2d", false):
		_shader_material.shader = preload(SHADER_PATH_FORWARD)
	else:
		_shader_material.shader = preload(SHADER_PATH_COMPATIBILITY)

	video_texture.material = _shader_material
	video_texture.texture = ImageTexture.new()
	video_texture.anchor_right = TextureRect.ANCHOR_END
	video_texture.anchor_bottom = TextureRect.ANCHOR_END
	video_texture.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	video_texture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE

	add_child(video_texture)
	add_child(audio_player)

	AudioServer.add_bus()
	audio_player.bus = AudioServer.get_bus_name(AudioServer.bus_count - 1)
	AudioServer.add_bus_effect(AudioServer.bus_count - 1, _audio_pitch_effect)

	if debug and OS.get_name().to_lower() != "web":
		_print_system_debug()


func _exit_tree() -> void:
	close()
	for item: Array in _abandoned:
		WorkerThreadPool.wait_for_task_completion(item[0])
		item[1].clear()
	_abandoned.clear()
	for task: int in _release_tasks:
		WorkerThreadPool.wait_for_task_completion(task)
	_release_tasks.clear()
	AudioServer.remove_bus(AudioServer.get_bus_index(audio_player.bus))


func _ready() -> void:
	playback_ready.emit()


#------------------------------------------------ VIDEO DATA HANDLING
## This is the starting point for video playback, provide a path of where
## the video file can be found and it will load a Video object. After which
## [code]_update_video()[/code] get's run and set's the first frame image.
func set_video_path(new_path: String) -> void:
	if _ignore_path_setter:
		path = new_path
		return

	close()
	if !is_node_ready():
		await ready
	if !get_tree().root.is_node_ready():
		await get_tree().root.ready

	if new_path == "" or new_path.ends_with(".tscn"):
		return
	elif new_path.split(":")[0] == "uid":
		new_path = ResourceUID.get_id_path(ResourceUID.text_to_id(new_path))

	path = new_path
	video = GoZenVideo.new()
	if decode_to_display_size and video.has_method("set_target_size") and size.x >= 1.0 and size.y >= 1.0:
		video.set_target_size(Vector2i(ceili(size.x), ceili(size.y)))
	if debug:
		video.enable_debug()
	else:
		video.disable_debug()

	# The audio stream opens on the worker thread too: opening either on the main thread stalls every frame drawn
	_opened_audio = []
	_video_thread = WorkerThreadPool.add_task(_open_video.bind(video, path, enable_audio, _opened_audio))


## Update the video manually by providing a GoZenVideo instance and an optional AudioStreamWAV.
func update_video(video_instance: GoZenVideo, audio_stream: AudioStream = null) -> void:
	close()
	if !is_node_ready():
		await ready
	if !get_tree().root.is_node_ready():
		await get_tree().root.ready

	_ignore_path_setter = true
	path = video_instance.get_path()
	_ignore_path_setter = false
	if enable_audio:
		if audio_stream != null:
			audio_player.stream = audio_stream
		else:
			_open_audio()

	_update_video(video_instance)
	if is_open() and enable_auto_play:
		play()


## Only run this function after manually having added a Video object to the `video` variable. A good reason for doing this is to load your video's at startup time to prevent your program for freezing for a second when loading in big video files. Some video formats load faster then others so if you are experiencing issues with long loading times, try to use this function and create the video object on startup, or try switching the video format which you are using.
func _update_video(new_video: GoZenVideo) -> void:
	video = new_video
	if !is_open():
		printerr("Video isn't open!")
		video = null
		return

	var image: Image
	var rotation_radians: float = deg_to_rad(video.get_rotation())

	is_playing = false
	current_frame = 0
	_decoded = 0
	_clock = 0.0

	# Getting video data
	_padding = video.get_padding()
	_rotation = video.get_rotation()
	_frame_rate = video.get_framerate()
	_resolution = video.get_resolution()
	_frame_count = video.get_frame_count()
	_has_alpha = video.get_has_alpha()
	_nv12 = video.has_method("is_nv12") and video.is_nv12()
	_zero_copy = video.has_method("is_zero_copy") and video.is_zero_copy()

	video_streams = video.get_streams(STREAM_TYPE.VIDEO)
	audio_streams = video.get_streams(STREAM_TYPE.AUDIO)
	subtitle_streams = video.get_streams(STREAM_TYPE.SUBTITLE)

	chapters.clear()
	for i: int in range(video.get_chapter_count()):
		@warning_ignore("UNSAFE_CALL_ARGUMENT")
		var chapter: Chapter = Chapter.new(
			video.get_chapter_start(i),
			video.get_chapter_end(i),
			video.get_chapter_metadata(i).get("title", "")
		)
		chapters.append(chapter)

	if abs(_rotation) == 90:
		image = Image.create_empty(_resolution.y, _resolution.x, false, Image.FORMAT_R8)
	else:
		image = Image.create_empty(_resolution.x, _resolution.y, false, Image.FORMAT_R8)

	image.fill(Color.WHITE)
	if debug:
		_print_video_debug()

	@warning_ignore("UNSAFE_METHOD_ACCESS")
	video_texture.texture.set_image(image)

	# Applying shader params.
	_shader_material.set_shader_parameter("resolution", video.get_actual_resolution())
	_shader_material.set_shader_parameter("full_color", video.is_full_color_range())
	_shader_material.set_shader_parameter("interlaced", video.get_interlaced())
	_shader_material.set_shader_parameter("rotation", rotation_radians)
	_shader_material.set_shader_parameter("nv12", _nv12)
	if _shader_material.shader in [SHADER_FAST, SHADER_FAST_NV12, preload(SHADER_PATH_COMPATIBILITY)]:
		var fast: bool = _rotation == 0 and video.get_interlaced() == 0 and not _has_alpha
		_shader_material.shader = (SHADER_FAST_NV12 if _nv12 else SHADER_FAST) if fast else preload(SHADER_PATH_COMPATIBILITY)
	_set_color_profile()

	y_texture.set_image(video.get_y_data())
	u_texture.set_image(video.get_u_data())
	v_texture.set_image(video.get_v_data())
	a_texture.set_image(video.get_a_data() if _has_alpha else image)

	_shader_material.set_shader_parameter("y_data", y_texture)
	_shader_material.set_shader_parameter("u_data", u_texture)
	_shader_material.set_shader_parameter("v_data", v_texture)
	_shader_material.set_shader_parameter("a_data", a_texture)

	set_playback_speed(playback_speed)
	video_loaded.emit()


## Sometimes color profiles are unknown from video files and in case that happens, the colors might be slightly off. Changing the export variable `color_profile` might help fixing the colors.
func _set_color_profile(new_profile: COLOR_PROFILE = color_profile) -> void:
	var color_data: Vector4
	var profile_str: String = video.get_color_profile()

	color_profile = new_profile
	if new_profile != COLOR_PROFILE.AUTO:
		profile_str = str(COLOR_PROFILE.find_key(COLOR_PROFILE.BT2100)).to_lower()

	match profile_str:
		"bt2020", "bt2100": color_data = Vector4(1.4746, 0.16455, 0.57135, 1.8814)
		"bt601", "bt470": color_data = Vector4(1.402, 0.344136, 0.714136, 1.772)
		_: color_data = Vector4(1.5748, 0.1873, 0.4681, 1.8556) # bt709 and unknown
	_shader_material.set_shader_parameter("color_profile", color_data)
	# the fast shaders: rgb = k_y * y + k_u * u + k_v * v after offset, the range's scale folded in
	var full: bool = video.is_full_color_range()
	var sy: float = 1.0 if full else 255.0 / 219.0
	var sc: float = 1.0 if full else 255.0 / 224.0
	_shader_material.set_shader_parameter("k_y", Vector3(sy, sy, sy))
	_shader_material.set_shader_parameter("k_u", Vector3(0.0, -color_data.y * sc, color_data.w * sc))
	_shader_material.set_shader_parameter("k_v", Vector3(color_data.x * sc, -color_data.z * sc, 0.0))
	_shader_material.set_shader_parameter("offset", Vector3(0.0 if full else 16.0 / 255.0, 0.5, 0.5))


## Seek frame can be used to switch to a frame number you want. Remember that some video codecs report incorrect video end frames or can't seek to the last couple of frames in a video file which may result in an error. Only use this when going to far distances in the video file, else you can use [code]next_frame()[/code].
func seek_frame(new_frame_nr: int) -> void:
	if !is_open() and new_frame_nr == current_frame:
		return

	_wait_decode()
	current_frame = clamp(new_frame_nr, 0, _frame_count)
	_decoded = current_frame
	_clock = current_frame / _frame_rate
	if video.seek_frame(current_frame):
		printerr("Couldn't seek frame!")
	else:
		_set_frame_image()

	if enable_audio and audio_player.stream and audio_player.stream.get_length() != 0:
		audio_player.set_stream_paused(false)
		audio_player.play(current_frame / _frame_rate)
		audio_player.set_stream_paused(!is_playing)


## Seeking frames can be slow, so when you just need to go a couple of frames ahead, you can use next_frame and set skip to false for the last frame.
func next_frame(skip: bool = false) -> bool:
	_wait_decode()
	var success: bool = video.next_frame(skip)
	_decoded = current_frame
	if success and !skip:
		_set_frame_image()
		next_frame_called.emit(current_frame)
	return success


func close() -> void:
	# A worker still opening or restarting the video keeps it until it is done (_process() then frees it on a worker):
	# waiting for it here held the main thread, and every screen, up to 0.6 s when a playlist switched while a loop
	# restart or an open was under way (several decoders being created at once on the Jetson)
	var busy: int = -1
	for task: int in [_video_thread, _restart_thread]:
		if task != -1:
			if WorkerThreadPool.is_task_completed(task):
				WorkerThreadPool.wait_for_task_completion(task)
			else:
				busy = task
	_video_thread = -1
	_restart_thread = -1
	_wait_decode()

	if video != null:
		_unbind_held()   # the held frames' textures go with the video
		if is_playing:
			pause()
		# Freeing a video closes its decoder, which takes tens of ms with the Jetson's hardware decoder: let a
		# worker thread drop the last reference instead of the main one
		var holder: Array = [video]
		video = null
		if busy != -1:
			_abandoned.append([busy, holder])
		else:
			_release_tasks.append(WorkerThreadPool.add_task(_release_video.bind(holder)))
	_opened_audio = []

	if audio_player:
		audio_player.stop()
		audio_player.stream = null


#------------------------------------------------ PLAYBACK HANDLING
func _process(delta: float) -> void:
	if _restart_thread != -1:
		# Showing the last frame until the worker has gone back to the first one
		if not WorkerThreadPool.is_task_completed(_restart_thread):
			return
		WorkerThreadPool.wait_for_task_completion(_restart_thread)
		_restart_thread = -1
		current_frame = 0
		_decoded = 0
		_clock = 0.0
		_time_elapsed = 0.0
		_set_frame_image()
		play()
		return

	if is_playing:
		# Frames are decoded ahead on worker threads into _queue (_fill_queue()), so the main thread only uploads
		# them: decoding three 1080p videos on it took most of every frame on a Jetson Xavier NX (5 FPS). A frame is
		# shown when the clock reaches it. When frames come late (the game's frame took long, or a decode did):
		# a video with its own sound playing keeps to its sound (its clock is the sound's position) and drops the
		# frames it is late by; any other video (the PuP's are mostly silent) shows every frame, and its clock slips
		# by the delay instead, except with zero-copy, where showing a frame costs nothing: late frames are skipped.
		var audio_master: bool = enable_audio and audio_player.playing and audio_player.stream != null
		if audio_master:            # the sound heard now: its position, minus what is still on its way out
			var latency: float = AudioServer.get_output_latency()
			_clock = maxf(audio_player.get_playback_position() + AudioServer.get_time_since_last_mix()
					- (latency if latency > 0.0 else _fallback_latency), _clock)
		else:
			_clock += delta * playback_speed
		_fill_queue()
		var due: int = floori(_clock * _frame_rate + 0.000001)
		var shown: Dictionary = {}
		_skips = 0
		_queue_mutex.lock()
		while not _queue.is_empty() and int(_queue[0].frame) <= due:
			if (audio_master or _zero_copy) and _queue.size() > 1 and int(_queue[1].frame) <= due:
				_queue.pop_front()          # late, keeping to the sound
				_skips += 1
				continue
			shown = _queue.pop_front()
			break
		var waiting: bool = not _queue.is_empty() or _decode_task != -1
		_queue_mutex.unlock()
		var eof_reached: bool = false
		if not shown.is_empty():
			current_frame = int(shown.frame)
			if not audio_master and not _zero_copy and current_frame < due:
				_clock = current_frame / _frame_rate   # late: the clock slips, no frame is lost
			if shown.has("held"):
				_show_held(int(shown.held))
			else:
				_set_frame_image(shown.planes)
			next_frame_called.emit(current_frame)
			_fill_queue()
		elif not waiting and _frame_count > 0 and _decoded + 1 >= _frame_count:
			eof_reached = due > current_frame
		elif not audio_master and due > current_frame:
			_clock = (current_frame + 1) / _frame_rate   # the next frame is still decoding
		_time_elapsed = (_clock - current_frame / _frame_rate) / playback_speed
		if eof_reached:
			is_playing = !is_playing
			if enable_audio and audio_player.stream != null:
				audio_player.set_stream_paused(true)
			video_ended.emit()

			if loop:
				restart()
	elif _video_thread != -1 and WorkerThreadPool.is_task_completed(_video_thread):
		# Only once the worker is done: waiting for it here would stall the frame while the file opens
		var error: int = WorkerThreadPool.wait_for_task_completion(_video_thread)
		if error != OK:
			printerr("Something went wrong waiting for task completion! %s" % error)

		_video_thread = -1
		if not _opened_audio.is_empty():
			audio_player.stream = _opened_audio[0]
			_opened_audio = []
		_update_video(video)
		if enable_auto_play:
			play()

	while not _release_tasks.is_empty() and WorkerThreadPool.is_task_completed(_release_tasks[0]):
		WorkerThreadPool.wait_for_task_completion(_release_tasks.pop_front())
	for i: int in range(_abandoned.size() - 1, -1, -1):
		if WorkerThreadPool.is_task_completed(_abandoned[i][0]):
			WorkerThreadPool.wait_for_task_completion(_abandoned[i][0])
			_release_tasks.append(WorkerThreadPool.add_task(_release_video.bind(_abandoned[i][1])))
			_abandoned.remove_at(i)


## Plays from the first frame again, like [code]seek_frame(0)[/code] then [code]play()[/code], but seeking on a worker
## thread: going back to the start recreates the decoder with the Jetson's hardware decoder, about 0.1 s that would
## otherwise stall every frame drawn. The video shows its current frame until then.
func restart() -> void:
	if !is_open() or _restart_thread != -1:
		return
	if is_playing:
		pause()
	_wait_decode()
	_restart_thread = WorkerThreadPool.add_task(_seek_start.bind(video))


func _seek_start(of: GoZenVideo) -> void:
	if of.seek_frame(0):
		printerr("Couldn't seek frame!")


## Keeps up to QUEUE_FRAMES frames decoded ahead: one worker task at a time decodes frames in order until the queue is
## full, not one frame per call. One frame per call made the decoder as fast as the game's frame rate: with a slow
## decoder (the Raspberry Pi 4's) at a 30 FPS cap (29.5 FPS drawn, 27.4 in the game's attract) a 30 fps video fell
## behind by 2 to 9 % and never caught up, the picture 5 s late after a minute. Never a seek: GoZenVideo.seek_frame()
## near the end of a file can retry for minutes, and close() waits for this task. A high-priority task: Godot runs
## low-priority ones (the opens, closes and restarts) on a share of its threads only, so a frame would wait behind them.
func _fill_queue() -> void:
	if _decode_task != -1:
		if not WorkerThreadPool.is_task_completed(_decode_task):
			return
		WorkerThreadPool.wait_for_task_completion(_decode_task)
		_decode_task = -1
	_queue_mutex.lock()
	var room: bool = _queue.size() < QUEUE_FRAMES and (_frame_count <= 0 or _decoded + 1 < _frame_count)
	_queue_mutex.unlock()
	if room:
		_decode_task = WorkerThreadPool.add_task(_decode_frames, true)


## On a worker thread: decodes the next frames (_decoded + 1 on) while the queue has room, each queued as soon as it is
## decoded. _decoded is the last frame decoded or being decoded; the main thread reads it only when no task runs.
func _decode_frames() -> void:
	while true:
		_queue_mutex.lock()
		var go: bool = _queue.size() < QUEUE_FRAMES and (_frame_count <= 0 or _decoded + 1 < _frame_count)
		var frame_nr: int = _decoded + 1
		if go:
			_decoded = frame_nr
		_queue_mutex.unlock()
		if not go:
			return
		_decode_one(frame_nr)


## On a worker thread: decodes the next frame and queues copies of its planes (GoZen reuses its images for the next),
## or with zero-copy the id of the frame held in the decoder's buffer.
func _decode_one(frame_nr: int) -> void:
	var item: Dictionary = {"frame": frame_nr}
	var held: int = video.next_frame_held() if _zero_copy else -1
	if held >= 0:
		item.held = held
	else:
		if not _zero_copy:
			video.next_frame(false)
		var planes: Array = [video.get_y_data().duplicate(), video.get_u_data().duplicate()]
		if not _nv12:
			planes.append(video.get_v_data().duplicate())
		if _has_alpha:
			planes.append(video.get_a_data().duplicate())
		item.planes = planes
	_queue_mutex.lock()
	_queue.append(item)
	_queue_mutex.unlock()


## Stops decoding ahead and forgets the decoded frames (before a seek, a restart or a close).
func _wait_decode() -> void:
	if _decode_task != -1:
		WorkerThreadPool.wait_for_task_completion(_decode_task)
		_decode_task = -1
	_queue_mutex.lock()
	_queue.clear()
	_queue_mutex.unlock()
	if _zero_copy and video != null:
		video.drop_held()
	_decoded = current_frame


## Start the video playback. This will play until reaching the end of the video and then pause and go back to the start.
func play() -> void:
	if not is_open():
		print("The video on '%s' isn't open yet!" % path)
		return
	if is_playing: return
	is_playing = true
	_clock = current_frame / _frame_rate

	if enable_audio and audio_player.stream and audio_player.stream.get_length() != 0:
		audio_player.set_stream_paused(false)
		audio_player.play((current_frame + 1) / _frame_rate)
		audio_player.set_stream_paused(!is_playing)

	playback_started.emit()


## Pausing the video.
func pause() -> void:
	is_playing = false
	if enable_audio and audio_player.stream != null:
		audio_player.set_stream_paused(true)
	playback_paused.emit()


## Ensures the audio playback is in sync with the video
func _sync_audio_video() -> void:
	if  _time_elapsed < 1.20:
		return
	elif enable_audio and audio_player.stream.get_length() != 0:
		var audio_offset: float = audio_player.get_playback_position() + AudioServer.get_time_since_last_mix() - (current_frame + 1) / _frame_rate
		if abs(audio_player.get_playback_position() + AudioServer.get_time_since_last_mix() - (current_frame + 1) / _frame_rate) > AUDIO_OFFSET_THRESHOLD:
			if debug: print("Audio Sync: time correction: ", audio_offset)
			audio_player.seek((current_frame + 1) / _frame_rate)
			audio_player.pitch_scale = playback_speed
		elif audio_speed_to_sync:
			if is_zero_approx(audio_player.pitch_scale - playback_speed):
				if audio_offset > AUDIO_OFFSET_THRESHOLD / 2:
					audio_player.pitch_scale = playback_speed * 0.99
					if debug: print("Audio Sync: slow down")
				elif audio_offset < -AUDIO_OFFSET_THRESHOLD / 2:
					audio_player.pitch_scale = playback_speed * 1.01
					if debug: print("Audio Sync: speed up")
			else:
				if not (audio_player.pitch_scale > playback_speed) != not (audio_offset < 0):
					audio_player.pitch_scale = playback_speed
					if debug: print("Audio Sync: back to normal")


#------------------------------------------------ GETTERS
## Getting the total amount of frames found in the video file.
func get_video_frame_count() -> int:
	return _frame_count


## Getting the framerate of the video
func get_video_framerate() -> float:
	return _frame_rate


## Getting the length of the video in seconds (integer)
func get_video_length() -> int:
	return int(_frame_count / _frame_rate)


## Getting the length of the video in seconds (float)
func get_video_length_float() -> float:
	return _frame_count / _frame_rate


## Getting the current playback position of the video in seconds (integer)
func get_current_playback_position() -> int:
	return int(current_frame / _frame_rate)


## Getting the current playback position of the video in seconds (float)
func get_current_playback_position_float() -> float:
	return current_frame / _frame_rate


## Getting the rotation in degrees of the video
func get_video_rotation() -> int:
	return _rotation


## Check the alpha value of a video to know if this video has alpha or not
func is_video_alpha() -> bool:
	return _has_alpha


## Getting the title of a stream.
func get_stream_title(stream: int) -> String:
	if not is_open():
		printerr("Video is not open!")
		return ""

	return video.get_stream_metadata(stream).get("title")


## Getting the language of a stream.
func get_stream_language(stream: int) -> String:
	if not is_open():
		printerr("Video is not open!")
		return ""

	return video.get_stream_metadata(stream).get("language")


## Checking to see if the video is open or not, trying to run functions without checking if open can crash your project.
func is_open() -> bool:
	return video != null and video.is_open()


func _get_img_tex(image_data: PackedByteArray, width: int, height: int, r8: bool = true) -> ImageTexture:
	var format: Image.Format = Image.FORMAT_R8 if r8 else Image.FORMAT_RG8
	var image: Image = Image.create_from_data(width, height, false, format, image_data)

	return ImageTexture.create_from_image(image)


#------------------------------------------------ SETTERS
func _set_current_frame(new_current_frame: int) -> void:
	current_frame = new_current_frame
	frame_changed.emit(current_frame)


func _set_frame_image(planes: Array = []) -> void:
	_unbind_held()
	if planes.is_empty():
		planes = [video.get_y_data(), video.get_u_data()]
		if not _nv12:
			planes.append(video.get_v_data())
		if _has_alpha:
			planes.append(video.get_a_data())
		if _copy_planes:
			planes = planes.map(func(image: Image) -> Image: return image.duplicate())
	RenderingServer.texture_2d_update(y_texture.get_rid(), planes[0], 0)
	RenderingServer.texture_2d_update(u_texture.get_rid(), planes[1], 0)
	if not _nv12:
		RenderingServer.texture_2d_update(v_texture.get_rid(), planes[2], 0)
	if _has_alpha:
		RenderingServer.texture_2d_update(a_texture.get_rid(), planes[-1], 0)


## Shows a frame held in the decoder's buffer: the shader samples its textures (RIDs straight into the material, as
## they are not Texture resources). A frame that cannot be shown is lost; zero-copy stops when it is impossible.
func _show_held(id: int) -> void:
	_held_bound = true
	if RenderingServer.is_on_render_thread():
		_show_held_now(id, video)
	else:
		RenderingServer.call_on_render_thread(_show_held_now.bind(id, video))


## On the render thread. of: the video the frame belongs to (the node may have opened another one since).
func _show_held_now(id: int, of: GoZenVideo) -> void:
	if of != video or not is_instance_valid(of):
		return
	var rids: Array = of.show_held(id)
	if rids.is_empty():
		if not of.is_zero_copy():
			_zero_copy = false
		return
	if not _held_bound:
		return   # unbound meanwhile (a copied frame or a close came first)
	var material: RID = _shader_material.get_rid()
	RenderingServer.material_set_param(material, "y_data", rids[0])
	RenderingServer.material_set_param(material, "u_data", rids[1])
	if not _nv12:
		RenderingServer.material_set_param(material, "v_data", rids[2])


func _unbind_held() -> void:
	if _held_bound:
		_held_bound = false
		_shader_material.set_shader_parameter("y_data", y_texture)
		_shader_material.set_shader_parameter("u_data", u_texture)
		_shader_material.set_shader_parameter("v_data", v_texture)


func set_playback_speed(new_playback_value: float) -> void:
	if playback_speed_override == Vector2.ZERO:
		playback_speed = clampf(new_playback_value, 0.5, 2)
	else:
		playback_speed = clampf(new_playback_value, playback_speed_override.x, playback_speed_override.y)
	_frame_time = (1.0 / _frame_rate) / playback_speed

	if enable_audio and audio_player.stream != null:
		audio_player.pitch_scale = playback_speed
		_set_pitch_adjust()
		if is_playing:
			audio_player.play(current_frame * (1.0 / _frame_rate))


func set_pitch_adjust(new_pitch_value: bool) -> void:
	pitch_adjust = new_pitch_value
	_set_pitch_adjust()


func _set_pitch_adjust() -> void:
	if pitch_adjust:
		_audio_pitch_effect.pitch_scale = clamp(1.0 / playback_speed, 0.5, 2.0)
	elif _audio_pitch_effect.pitch_scale != 1.0:
		_audio_pitch_effect.pitch_scale = 1.0


func set_audio_stream(stream: int) -> void:
	if not is_open():
		printerr("Video is not open!")
		return

	if not stream in audio_streams:
		printerr("Invalid audio stream!")
		return

	if enable_audio:
		_open_audio(stream)
		if is_playing and audio_player.stream.get_length() != 0:
			audio_player.set_stream_paused(false)
			audio_player.play(current_frame / _frame_rate)
			audio_player.set_stream_paused(!is_playing)


#------------------------------------------------ MISC
## Converts the given duration as seconds in a formatted string. (hh):mm:ss
func duration_to_formatted_string(duration_in_seconds: float) -> String:
	var hours: int = floori(duration_in_seconds / 3600.0)
	var minutes: int = floori(duration_in_seconds / 60.0) % 60
	var seconds: int = floori(duration_in_seconds) % 60

	if hours == 0:
		return "%02d:%02d" % [minutes, seconds]
	return "%02d:%02d:%02d" % [hours, minutes, seconds]


## On a worker thread: everything it touches is passed in, so close() can leave it running (the video and its
## path, and audio_out, which receives the audio stream).
func _open_video(of: GoZenVideo, file: String, with_audio: bool, audio_out: Array) -> void:
	if of.open(file):
		printerr("Error opening video!")
	if with_audio:
		var stream: AudioStreamFFmpeg = AudioStreamFFmpeg.new()
		if stream.open(file, -1) != OK:
			printerr("Failed to open AudioStreamFFmpeg for: %s" % file)
		else:
			audio_out.append(stream)


## On a worker thread (close()): drops the last reference to a closed video, which frees it and its decoder.
static func _release_video(holder: Array) -> void:
	holder.clear()


func _open_audio(stream_id: int = -1) -> void:
	var stream: AudioStreamFFmpeg = AudioStreamFFmpeg.new()

	if stream.open(path, stream_id) != OK:
		printerr("Failed to open AudioStreamFFmpeg for: %s" % path)
		return

	audio_player.stream = stream


func _print_stream_info(streams: PackedInt32Array) -> void:
	for i: int in range(len(streams)):
		var metadata: Dictionary = video.get_stream_metadata(streams[i])
		var title: String = metadata.get("title")
		var language: String = metadata.get("language")

		if title == "":
			title = "Track " + str(i + 1)
		if language != "":
			title += " - %s" % language

		print("- %s" % title)


func _print_system_debug() -> void:
	print_rich("[b]System info")
	print("OS name: ", OS.get_name())
	print("Distro name: ", OS.get_distribution_name())
	print("OS version: ", OS.get_version())
	print_rich("Memory info:\n\t", OS.get_memory_info())
	print("CPU name: ", OS.get_processor_name())
	print("Threads count: ", OS.get_processor_count())


func _print_video_debug() -> void:
	print_rich("[b]Video debug info")
	print("Extension: ", path.get_extension())
	print("Resolution: ", _resolution)
	print("Actual resolution: ", video.get_actual_resolution())
	print("Pixel format: ", video.get_pixel_format())
	print("Color profile: ", video.get_color_profile())
	print("Framerate: ", _frame_rate)
	print("Duration (in frames): ", _frame_count)
	print("Padding: ", _padding)
	print("Rotation: ", _rotation)
	print("Alpha: ", _has_alpha)
	print("Full color range: ", video.is_full_color_range())
	print("Interlaced flag: ", video.get_interlaced())
	print("Using sws: ", video.is_using_sws())
	print("Sar: ", video.get_sar())

	print_rich("Video streams: [i](%s)" % video_streams.size())
	_print_stream_info(video_streams)

	if audio_streams.size() != 0:
		print_rich("Audio streams: [i](%s)" % audio_streams.size())
		_print_stream_info(audio_streams)
	elif debug:
		print("No audio streams found.")

	if subtitle_streams.size() != 0:
		print_rich("Subtitle streams: [i](%s)" % subtitle_streams.size())
		_print_stream_info(subtitle_streams)
	elif debug:
		print("No subtitle streams found.")

	if chapters.size() != 0:
		print_rich("Chapters: [i](%s)" % chapters.size())
		for i: int in range(chapters.size()):
			var title: String = chapters[i].title
			if title == "":
				title = "Chapter " + str(i + 1)
			print("- %s-%s - %s" % [
				duration_to_formatted_string(chapters[i].start),
				duration_to_formatted_string(chapters[i].end),
				title
			])
	else:
		print("No chapters found.")



class Chapter:
	var start: float ## Start of the chapter in seconds.
	var end: float ## End of the chapter in seconds.
	var title: String

	func _init(_start: float, _end: float, _title: String) -> void:
		start = _start
		end = _end
		title = _title
