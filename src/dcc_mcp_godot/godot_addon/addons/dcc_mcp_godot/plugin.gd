@tool
extends EditorPlugin

const Commands = preload("res://addons/dcc_mcp_godot/commands.gd")

var _socket := WebSocketPeer.new()
var _commands
var _hello_sent := false
var _next_reconnect_ms := 0


func _enter_tree() -> void:
	_commands = Commands.new(self)
	set_process(true)
	_connect_bridge()


func _exit_tree() -> void:
	set_process(false)
	_socket.close()


func _process(_delta: float) -> void:
	_socket.poll()
	var state := _socket.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN:
		if not _hello_sent:
			_send_json({
				"type": "hello",
				"client": "godot",
				"version": Engine.get_version_info().get("string", "unknown"),
			})
			_hello_sent = true
		while _socket.get_available_packet_count() > 0:
			_handle_packet(_socket.get_packet().get_string_from_utf8())
	elif state == WebSocketPeer.STATE_CLOSED and Time.get_ticks_msec() >= _next_reconnect_ms:
		_connect_bridge()


func _connect_bridge() -> void:
	_socket = WebSocketPeer.new()
	_hello_sent = false
	var url := OS.get_environment("DCC_MCP_GODOT_BRIDGE_URL")
	if url.is_empty():
		url = "ws://127.0.0.1:3847"
	var error := _socket.connect_to_url(url)
	if error != OK:
		_next_reconnect_ms = Time.get_ticks_msec() + 1000


func _handle_packet(text: String) -> void:
	var message = JSON.parse_string(text)
	if not message is Dictionary or message.get("type") != "request":
		return
	var request_id = message.get("id")
	var result: Dictionary = _commands.execute(
		str(message.get("method", "")),
		message.get("params", {}) as Dictionary,
	)
	if result.has("__error__"):
		_send_json({
			"type": "response",
			"id": request_id,
			"error": {"code": -32000, "message": result["__error__"]},
		})
	else:
		_send_json({"type": "response", "id": request_id, "result": result})


func _send_json(value: Dictionary) -> void:
	_socket.send_text(JSON.stringify(value))
