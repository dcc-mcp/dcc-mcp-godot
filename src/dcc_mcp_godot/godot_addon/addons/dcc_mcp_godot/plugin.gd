@tool
extends EditorPlugin

const Commands = preload("res://addons/dcc_mcp_godot/commands.gd")
const RUNTIME_AUTOLOAD_NAME := "DccMcpRuntimePeer"
const RUNTIME_AUTOLOAD_PATH := "res://addons/dcc_mcp_godot/runtime_peer.gd"


class RuntimeDebugger extends EditorDebuggerPlugin:
	var owner

	func _init(plugin_owner) -> void:
		owner = plugin_owner

	func _has_capture(capture: String) -> bool:
		return capture == "dcc_mcp_godot"

	func _capture(message: String, data: Array, _session_id: int) -> bool:
		if message == "dcc_mcp_godot:ready":
			owner._runtime_ready = true
			return true
		if message == "dcc_mcp_godot:response" and not data.is_empty():
			owner._handle_runtime_response(data[0])
			return true
		return false

	func send_request(request_id, action: String, params: Dictionary) -> bool:
		if not owner._runtime_ready:
			return false
		for session in get_sessions():
			if session.is_active():
				session.send_message("dcc_mcp_godot:request", [{"id": request_id, "action": action, "params": params}])
				return true
		return false

var _socket := WebSocketPeer.new()
var _commands
var _hello_sent := false
var _next_reconnect_ms := 0
var _debugger
var _runtime_ready := false


func _enter_tree() -> void:
	_commands = Commands.new(self)
	_debugger = RuntimeDebugger.new(self)
	add_debugger_plugin(_debugger)
	if not ProjectSettings.has_setting("autoload/%s" % RUNTIME_AUTOLOAD_NAME):
		add_autoload_singleton(RUNTIME_AUTOLOAD_NAME, RUNTIME_AUTOLOAD_PATH)
		ProjectSettings.save()
	set_process(true)
	_connect_bridge()


func _exit_tree() -> void:
	set_process(false)
	_socket.close()
	if _debugger != null:
		remove_debugger_plugin(_debugger)


func _disable_plugin() -> void:
	if ProjectSettings.has_setting("autoload/%s" % RUNTIME_AUTOLOAD_NAME):
		remove_autoload_singleton(RUNTIME_AUTOLOAD_NAME)
		ProjectSettings.save()


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
	elif result.has("__runtime_action__"):
		if not _debugger.send_request(request_id, result["__runtime_action__"], result.get("params", {})):
			if result["__runtime_action__"] == "get_runtime_status":
				_send_json({"type": "response", "id": request_id, "result": {"connected": false, "playing": EditorInterface.is_playing_scene(), "runtime_ready": _runtime_ready}})
			else:
				_send_json({"type": "response", "id": request_id, "error": {"code": -32001, "message": "No running Godot game debugger session"}})
	else:
		_send_json({"type": "response", "id": request_id, "result": result})


func _handle_runtime_response(payload) -> void:
	if not payload is Dictionary or not payload.has("id"):
		return
	if payload.has("error"):
		_send_json({"type": "response", "id": payload.id, "error": {"code": -32002, "message": str(payload.error)}})
	else:
		_send_json({"type": "response", "id": payload.id, "result": payload.get("result", {})})


func _send_json(value: Dictionary) -> void:
	_socket.send_text(JSON.stringify(value))
