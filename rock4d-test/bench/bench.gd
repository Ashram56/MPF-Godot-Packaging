extends Node
# Decode bench, as video_playback.gd's worker does: N videos decoded on worker threads.
# args after --:  --dir=DIR (a.mp4 b.mp4 c.mp4 d.mp4)  --n=3  --frames=240  --mode=copy|dup|into   (dup = next_frame + duplicate() of the planes, the current behaviour; into = next_frame_into() on a recycled set, needs the new GoZen)
func _cpu() -> float:
	var out := []
	OS.execute("cat", ["/proc/%d/stat" % OS.get_process_id()], out)
	var t: String = out[0]
	var p := t.substr(t.rfind(")") + 2).split(" ")
	return (float(p[11]) + float(p[12])) / 100.0

func _ready() -> void:
	var dir := "/tmp/claude-0/s/clips"
	var n := 3
	var frames := 240
	var mode := "dup"
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--dir="): dir = a.substr(6)
		elif a.begins_with("--n="): n = int(a.substr(4))
		elif a.begins_with("--frames="): frames = int(a.substr(9))
		elif a.begins_with("--mode="): mode = a.substr(7)
	var names := ["a", "b", "c", "d"]
	var vids := []
	for i in n:
		var v := GoZenVideo.new()
		v.open("%s/%s.mp4" % [dir, names[i % 4]])
		vids.append(v)
	var v0: GoZenVideo = vids[0]
	print("opened %d videos %s nv12=%s zero_copy=%s hwdec=%s threads=%s fast=%s skip=%s mode=%s" % [n, v0.get_actual_resolution(), v0.is_nv12(), v0.is_zero_copy() if v0.has_method("is_zero_copy") else "?", OS.get_environment("GOZEN_HWDEC"), OS.get_environment("GOZEN_THREADS"), OS.get_environment("GOZEN_FAST"), OS.get_environment("GOZEN_SKIP_LOOP_FILTER"), mode])
	var times := []   # per video [decode_us, copy_us]
	for i in n: times.append([0, 0])
	var t0 := Time.get_ticks_usec()
	var c0 := _cpu()
	var tasks := []
	for i in n:
		var v: GoZenVideo = vids[i]
		var tm: Array = times[i]
		tasks.append(WorkerThreadPool.add_task(func():
			var set: Array = []
			if mode == "into":
				set = [v.get_y_data().duplicate(), v.get_u_data().duplicate()]
				if not v.is_nv12(): set.append(v.get_v_data().duplicate())
			for k in frames:
				var a := Time.get_ticks_usec()
				if mode == "into":
					v.next_frame_into(set)
					tm[0] += Time.get_ticks_usec() - a
				else:
					v.next_frame(false)
					var b := Time.get_ticks_usec()
					tm[0] += b - a
					if mode == "dup":
						var y: Image = v.get_y_data().duplicate()
						var u: Image = v.get_u_data().duplicate()
						if not v.is_nv12():
							var w: Image = v.get_v_data().duplicate()
						tm[1] += Time.get_ticks_usec() - b
		))
	for t in tasks:
		WorkerThreadPool.wait_for_task_completion(t)
	var wall := (Time.get_ticks_usec() - t0) / 1e6
	var cpu := _cpu() - c0
	var dec := 0.0
	var dup := 0.0
	for tm in times:
		dec += tm[0]; dup += tm[1]
	print("RESULT n=%d frames=%d wall=%.2fs cpu=%.2fs fps_per_video=%.1f cpu_ms_per_frame=%.2f decode_ms_per_frame=%.2f dup_ms_per_frame=%.2f" % [n, frames, wall, cpu, frames / wall, cpu * 1000.0 / (n * frames), dec / 1000.0 / (n * frames), dup / 1000.0 / (n * frames)])
	get_tree().quit()
