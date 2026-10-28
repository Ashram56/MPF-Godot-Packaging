extends Node
## What dmd_out finds at /root/MPF (GMC's autoload): a connected BCP server that records what is sent.

class FakeServer:
	extends RefCounted
	var _client := true
	var frames: Array = []

	func send_bytes(command: String, data: PackedByteArray, params: Dictionary) -> void:
		frames.append([command, data, params])

var server := FakeServer.new()
