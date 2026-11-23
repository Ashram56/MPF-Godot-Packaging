extends Control

## A PuP screen's video player on Linux and Windows: GDE GoZen's VideoPlayback (FFmpeg; pup_addons/gde_gozen), which
## plays the pack's mp4s as they are and decodes on the GPU: the Jetson's decoder when libnvmpi is installed,
## Direct3D 11 Video (else DXVA2) on Windows (docs/pup/README.md). Offers
## the parts of VideoStreamPlayer that pup_screen.gd uses: open(), play() (from the start), stop(), finished.

signal finished

const PLAYBACK := "res://addons/gde_gozen/video_playback.gd"

var bus := "sfx"
var _playback: Control
var _loop := false


## The Jetson device nodes the hardware decoder needs (in /dev). Without them, libnvmpi's NVIDIA libraries do not
## fail cleanly (seen with libnvmpi installed and no decoder: NvRmMemInit failed, then Godot crashed), so GoZen
## gets GOZEN_HWDEC=0 and decodes in software. Set GOZEN_HWDEC yourself to override.
const HWDEC_MEM := "nvmap"
const HWDEC_DEVICES: Array[String] = ["nvhost-nvdec", "v4l2-nvdec"]

static var _hwdec_checked := false


static func _check_hwdec() -> void:
	if _hwdec_checked or OS.has_environment("GOZEN_HWDEC") or OS.get_name() != "Linux":
		return
	_hwdec_checked = true
	# FileAccess.file_exists() is false for device nodes; a listing of /dev has them
	var dev := DirAccess.get_files_at("/dev")
	var dec := Array(dev).any(func(f: String) -> bool:
		return HWDEC_DEVICES.any(func(d: String) -> bool: return f.begins_with(d)))
	if not (dec and HWDEC_MEM in dev):
		OS.set_environment("GOZEN_HWDEC", "0")
		print("GoZen: no Jetson decoder device (/dev/%s, /dev/%s*): software decoding"
				% [HWDEC_MEM, "*, /dev/".join(HWDEC_DEVICES)])


func _ready() -> void:
	_check_hwdec()
	_playback = load(PLAYBACK).new()
	_playback.set_anchors_preset(Control.PRESET_FULL_RECT)
	_playback.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_playback.enable_auto_play = true
	_playback.decode_to_display_size = true   # the Jetson's decoder scales to the PuP window (fewer pixels per frame)
	add_child(_playback)
	_playback.video_ended.connect(_on_ended)
	_playback.video_loaded.connect(func(): _playback.video_texture.show())
	# VideoPlayback adds an audio bus of its own (for its pitch effect): send it to this screen's bus
	var own := AudioServer.get_bus_index(_playback.audio_player.bus)
	if own >= 0 and AudioServer.get_bus_index(bus) >= 0:
		AudioServer.set_bus_send(own, bus)


func open(path: String, loop: bool, volume_db: float) -> void:
	_loop = loop
	_playback.loop = loop
	_playback.audio_player.volume_db = volume_db
	_playback.set_video_path(path)


## From the first frame again (pup_screen.gd's restart of a looping file or background).
func play() -> void:
	_playback.restart()


func stop() -> void:
	_playback.close()
	_playback.video_texture.hide()


func _on_ended() -> void:
	# VideoPlayback restarts a looping file itself
	if not _loop:
		finished.emit()
