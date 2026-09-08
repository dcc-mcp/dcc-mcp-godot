@tool
extends EditorPlugin

const Commands = preload("res://addons/dcc_mcp_godot/commands.gd")
const RUNTIME_AUTOLOAD_NAME := "DccMcpRuntimePeer"
const RUNTIME_AUTOLOAD_PATH := "res://addons/dcc_mcp_godot/runtime_peer.gd"
const BOOTSTRAP_STATUS_PATH := "res://.godot/dcc_mcp_godot_bootstrap.json"


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
var _pending_guarded_commits: Dictionary = {}


func _enter_tree() -> void:
	_write_bootstrap_status("starting")
	_commands = Commands.new(self)
	_debugger = RuntimeDebugger.new(self)
	add_debugger_plugin(_debugger)
	if not ProjectSettings.has_setting("autoload/%s" % RUNTIME_AUTOLOAD_NAME):
		add_autoload_singleton(RUNTIME_AUTOLOAD_NAME, RUNTIME_AUTOLOAD_PATH)
		ProjectSettings.save()
	set_process(true)
	_connect_bridge()
	_write_bootstrap_status("ready")


func _exit_tree() -> void:
	set_process(false)
	if _socket != null:
		_socket.close()
	if _debugger != null:
		remove_debugger_plugin(_debugger)
	_write_bootstrap_status("stopped")


func _write_bootstrap_status(status: String, message := "") -> void:
	var directory_error := DirAccess.make_dir_recursive_absolute(
		ProjectSettings.globalize_path("res://.godot")
	)
	if directory_error != OK:
		push_error("DCC-MCP bootstrap diagnostics directory failed: %s" % error_string(directory_error))
		return
	var file := FileAccess.open(BOOTSTRAP_STATUS_PATH, FileAccess.WRITE)
	if file == null:
		push_error("DCC-MCP bootstrap diagnostics file failed: %s" % error_string(FileAccess.get_open_error()))
		return
	file.store_string(JSON.stringify({
		"status": status,
		"message": message,
		"engine_version": Engine.get_version_info().get("string", "unknown"),
	}))


func _disable_plugin() -> void:
	if ProjectSettings.has_setting("autoload/%s" % RUNTIME_AUTOLOAD_NAME):
		remove_autoload_singleton(RUNTIME_AUTOLOAD_NAME)
		ProjectSettings.save()


func _process(_delta: float) -> void:
	# Tool-script reloads can briefly clear initialized members before the new
	# plugin instance enters the tree. Recreate the peer instead of polling a
	# stale/null object left by the previous instance.
	if _socket == null:
		_connect_bridge()
		return
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
	# Authorization belongs to one exact WebSocket connection. A replacement
	# connection can never inherit a queued mutation from its predecessor.
	_pending_guarded_commits.clear()
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
	if not message is Dictionary:
		return
	if message.get("type") == "commit_authorization":
		_handle_commit_authorization(message)
		return
	if message.get("type") != "request":
		return
	if str(message.get("method", "")) == "capability.commit_typed_action":
		_stage_guarded_commit(message)
		return
	_execute_bridge_request(message)


func _stage_guarded_commit(message: Dictionary) -> void:
	var request_id = message.get("id")
	var params = message.get("params", {})
	var fence = params.get("__dcc_mcp_commit_fence") if params is Dictionary else null
	if not fence is Dictionary \
		or fence.keys().size() != 3 \
		or not fence.has_all(["guard_id", "request_id", "request_digest"]) \
		or not fence.guard_id is String \
		or str(fence.guard_id).length() != 32 \
		or fence.request_id != request_id \
		or not fence.request_digest is String \
		or str(fence.request_digest).length() != 64 \
		or _pending_guarded_commits.has(str(fence.guard_id)):
		_send_json({
			"type": "response",
			"id": request_id,
			"error": {"code": -32003, "message": "typed_action_commit_fence_invalid"},
		})
		return
	var guarded_params: Dictionary = params.duplicate(true)
	guarded_params.erase("__dcc_mcp_commit_fence")
	var guard_id := str(fence.guard_id)
	_pending_guarded_commits[guard_id] = {
		"id": request_id,
		"method": message.get("method"),
		"params": guarded_params,
		"request_digest": str(fence.request_digest),
	}
	_send_json({
		"type": "commit_intent",
		"guard_id": guard_id,
		"request_id": request_id,
		"request_digest": str(fence.request_digest),
	})


func _handle_commit_authorization(message: Dictionary) -> void:
	if message.keys().size() != 6 \
		or not message.has_all([
			"type", "guard_id", "request_id", "request_digest", "authorized", "reason",
		]) \
		or not message.guard_id is String:
		return
	var guard_id := str(message.guard_id)
	var pending = _pending_guarded_commits.get(guard_id)
	if not pending is Dictionary \
		or pending.id != message.request_id \
		or str(pending.request_digest) != str(message.request_digest):
		return
	_pending_guarded_commits.erase(guard_id)
	if not bool(message.authorized) or str(message.reason) != "authorized":
		var terminal_reason := str(message.reason)
		if terminal_reason not in [
			"request_terminal", "request_identity_mismatch", "request_already_authorized",
			"commit_guard_rejected", "host_identity_mismatch",
		]:
			terminal_reason = "request_terminal"
		_send_json({
			"type": "response",
			"id": pending.id,
			"error": {"code": -32004, "message": "typed_action_commit_terminal:%s" % terminal_reason},
		})
		return
	_execute_bridge_request(pending)


func _execute_bridge_request(message: Dictionary) -> void:
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
	if _socket != null and _socket.get_ready_state() == WebSocketPeer.STATE_OPEN:
		_socket.send_text(JSON.stringify(value))
