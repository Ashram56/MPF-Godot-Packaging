extends Node
## Publishes a 256x64 and an HD (1024x256: left half white, right half black) picture, lets dmd_out run, then prints
## what reached the fake MPF: "PROBE <command> <name> <bytes> first=r,g,b last=r,g,b" and quits.

var _frames := 0


func _ready() -> void:
	var white := _viewport(Vector2i(128, 32), Color(1, 1, 1))     # not published: the root viewport is "classic"
	get_tree().root.add_child.call_deferred(white)
	var mid := _viewport(Vector2i(256, 64), Color(0.5, 0.5, 0.5))
	add_child(mid)
	var hd := _viewport(Vector2i(1024, 256), Color(1, 1, 1))
	var black := ColorRect.new()
	black.color = Color(0, 0, 0)
	black.position = Vector2(512, 0)
	black.size = Vector2(512, 256)
	hd.add_child(black)
	add_child(hd)
	var out := get_node("/root/DmdOut")
	out.publish("256x64", mid)
	out.publish("hd", hd)
	var bg := ColorRect.new()                                       # the root viewport (classic): all white
	bg.color = Color(1, 1, 1)
	bg.size = Vector2(128, 32)
	get_tree().root.add_child.call_deferred(bg)


func _viewport(size: Vector2i, color: Color) -> SubViewport:
	var vp := SubViewport.new()
	vp.size = size
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	var rect := ColorRect.new()
	rect.color = color
	rect.size = Vector2(size)
	vp.add_child(rect)
	return vp


func _process(_delta: float) -> void:
	_frames += 1
	var frames: Array = get_node("/root/MPF").server.frames
	if frames.size() > 0 or _frames > 120:
		if frames.is_empty():
			print("PROBE none")
		else:
			var f: Array = frames[0]
			var d: PackedByteArray = f[1]
			var n := d.size()
			print("PROBE %s %s %d first=%d,%d,%d last=%d,%d,%d" % [f[0], f[2].get("name", ""), n,
					d[0], d[1], d[2], d[n - 3], d[n - 2], d[n - 1]])
		get_tree().quit()
