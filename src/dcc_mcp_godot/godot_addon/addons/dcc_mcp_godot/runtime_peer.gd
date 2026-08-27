extends Node

const MAX_DEPTH := 16
const MAX_RESULTS := 500
const MAX_FRAMES := 120
const DEFAULT_PAGE_SIZE := 64
const MAX_PAGE_SIZE := 128
const TYPED_ACTION_MANIFEST_PATH := "res://.dcc-mcp/playtest-actions.v1.json"
const MAX_TYPED_ACTION_MANIFEST_BYTES := 65536
const TYPED_ACTION_RESERVATION_TTL_MSEC := 5000
const TYPED_ACTION_REQUEST_KEYS := [
	"project_id", "session_id", "runtime_id", "authority_id",
	"manifest_id", "manifest_digest", "action",
]
const FORBIDDEN_ACTION_SELECTOR_TERMS := [
	"script", "console", "eval", "shell", "exec", "file", "network", "http",
	"url", "socket", "account", "login", "auth", "payment", "purchase",
	"multiplayer", "peer", "rpc",
]

var _recording := false
var _recorded_events: Array[Dictionary] = []
var _last_test_report := {"status": "not_run", "assertions": []}
var _debugger_registered := false
var _typed_manifest: Dictionary = {}
var _typed_manifest_digest := ""
var _typed_action_count := 0
var _typed_rate_count := 0
var _typed_rate_window_start_msec := 0
var _typed_runtime_id := ""
var _typed_reservation: Dictionary = {}


func _ready() -> void:
	_ensure_typed_runtime_id()
	set_process(true)
	_register_debugger()


func _process(_delta: float) -> void:
	_expire_typed_action_reservation()
	if not _debugger_registered:
		_register_debugger()


func _register_debugger() -> void:
	if not EngineDebugger.is_active():
		return
	EngineDebugger.register_message_capture("dcc_mcp_godot", _capture)
	EngineDebugger.send_message("dcc_mcp_godot:ready", [{"version": Engine.get_version_info().get("string", "unknown")}])
	_debugger_registered = true


func _capture(message: String, data: Array) -> bool:
	if message != "request" or data.is_empty() or not data[0] is Dictionary:
		return false
	var request: Dictionary = data[0]
	var result := _execute(str(request.get("action", "")), request.get("params", {}))
	var response := {"id": request.get("id")}
	if result.has("__error__"): response["error"] = result.__error__
	else: response["result"] = result
	EngineDebugger.send_message("dcc_mcp_godot:response", [response])
	return true


func _execute(action: String, params: Dictionary) -> Dictionary:
	match action:
		"get_runtime_status": return _get_runtime_status()
		"execute_typed_action": return _execute_typed_action(params)
		"reserve_typed_action": return _reserve_typed_action(params)
		"commit_typed_action": return _commit_typed_action(params)
		"finalize_typed_action": return _finalize_typed_action(params)
		"rollback_typed_action": return _rollback_typed_action(params)
		"get_game_scene_tree": return _get_scene_tree(params)
		"get_game_node_properties": return _get_node_properties(params)
		"set_game_node_property": return _set_node_property(params)
		"execute_game_script": return _call_node_method(params)
		"get_game_screenshot": return _screenshot(params)
		"capture_frames": return _capture_frames(params)
		"monitor_properties": return _monitor_properties(params)
		"simulate_key": return _simulate_key(params)
		"simulate_mouse_click": return _simulate_mouse_click(params)
		"simulate_mouse_move": return _simulate_mouse_move(params)
		"simulate_action": return _simulate_action(params)
		"simulate_sequence": return _simulate_sequence(params)
		"start_recording": _recording = true; _recorded_events.clear(); return {"recording": true}
		"stop_recording": _recording = false; return {"recording": false, "events": _recorded_events.duplicate(true), "count": _recorded_events.size()}
		"replay_recording": return _replay_recording(params)
		"find_nodes_by_script": return _find_nodes_by_script(params)
		"get_autoload": return _get_autoload(params)
		"batch_get_properties": return _batch_get_properties(params)
		"find_ui_elements": return _find_ui_elements(params)
		"click_button_by_text": return _click_button_by_text(params)
		"wait_for_node": return _wait_for_node(params)
		"find_nearby_nodes": return _find_nearby_nodes(params)
		"navigate_to": return _navigate_to(params)
		"move_to": return _move_to(params)
		"assert_node_state": return _assert_node_state(params)
		"assert_screen_text": return _assert_screen_text(params)
		"run_test_scenario": return _run_test_scenario(params)
		"run_stress_test": return _run_stress_test(params)
		"get_test_report": return _last_test_report
		"get_performance_monitors": return _get_performance_monitors()
		_: return _error("Unknown runtime action: %s" % action)


func _get_scene_tree(params: Dictionary) -> Dictionary:
	var root := get_tree().current_scene
	if root == null: return _error("Running game has no current scene")
	var cursor_result := _decode_node_cursor(str(params.get("cursor", "")))
	if cursor_result.has("__error__"): return cursor_result
	var cursor: Array[int] = cursor_result.indices
	var max_nodes := clampi(int(params.get("max_nodes", DEFAULT_PAGE_SIZE)), 1, MAX_PAGE_SIZE)
	var nodes: Array[Dictionary] = []
	while nodes.size() < max_nodes:
		var node := _node_at_cursor(root, cursor)
		if node == null: return _error("Runtime scene-tree cursor no longer identifies a node")
		nodes.append(_flat_snapshot(node))
		var next_cursor = _next_node_cursor(root, cursor)
		if next_cursor == null:
			cursor = []
			break
		cursor = next_cursor
	var has_more := not cursor.is_empty()
	var result := {
		"scene_path": root.scene_file_path,
		"nodes": nodes,
		"count": nodes.size(),
		"truncated": has_more,
		"next_cursor": _encode_node_cursor(cursor) if has_more else null,
	}
	# Preserve the legacy root field for clients that have not adopted paging.
	if str(params.get("cursor", "")).is_empty() and not nodes.is_empty():
		result["root"] = _snapshot(root, 0) if not has_more else nodes[0]
	return result


func _flat_snapshot(node: Node) -> Dictionary:
	return {
		"name": node.name,
		"type": node.get_class(),
		"path": str(node.get_path()),
		"visible": node.is_visible_in_tree() if node is CanvasItem or node is Node3D else true,
		"children": [],
		"child_count": node.get_child_count(),
	}


func _decode_node_cursor(value: String) -> Dictionary:
	if value.is_empty(): return {"indices": [] as Array[int]}
	if not value.begins_with("v1:"): return _error("Runtime cursor is invalid")
	var indices: Array[int] = []
	var payload := value.trim_prefix("v1:")
	if payload.is_empty(): return {"indices": indices}
	for item in payload.split(","):
		if not str(item).is_valid_int(): return _error("Runtime cursor is invalid")
		var index := int(item)
		if index < 0 or indices.size() >= MAX_DEPTH: return _error("Runtime cursor is invalid")
		indices.append(index)
	return {"indices": indices}


func _encode_node_cursor(indices: Array[int]) -> String:
	var values: Array[String] = []
	for index in indices: values.append(str(index))
	return "v1:%s" % ",".join(values)


func _decode_offset_cursor(value: String, prefix: String) -> Dictionary:
	if value.is_empty(): return {"offset": 0}
	var expected_prefix := "%s:" % prefix
	if not value.begins_with(expected_prefix): return _error("Runtime cursor is invalid")
	var payload := value.trim_prefix(expected_prefix)
	if not payload.is_valid_int() or int(payload) < 0: return _error("Runtime cursor is invalid")
	return {"offset": int(payload)}


func _encode_offset_cursor(prefix: String, offset: int) -> String:
	return "%s:%d" % [prefix, offset]


func _node_at_cursor(root: Node, indices: Array[int]) -> Node:
	var node := root
	for index in indices:
		if index < 0 or index >= node.get_child_count(): return null
		node = node.get_child(index)
	return node


func _next_node_cursor(root: Node, indices: Array[int]):
	var node := _node_at_cursor(root, indices)
	if node == null: return null
	if indices.size() < MAX_DEPTH and node.get_child_count() > 0:
		var child_cursor: Array[int] = indices.duplicate()
		child_cursor.append(0)
		return child_cursor
	var candidate: Array[int] = indices.duplicate()
	while not candidate.is_empty():
		var sibling_index: int = int(candidate.pop_back()) + 1
		var parent := _node_at_cursor(root, candidate)
		if parent != null and sibling_index < parent.get_child_count():
			candidate.append(sibling_index)
			return candidate
	return null


func _snapshot(node: Node, depth: int) -> Dictionary:
	var data := {"name": node.name, "type": node.get_class(), "path": str(node.get_path()), "visible": node.is_visible_in_tree() if node is CanvasItem or node is Node3D else true, "children": []}
	if depth >= MAX_DEPTH: return data
	for child in node.get_children(): data.children.append(_snapshot(child, depth + 1))
	return data


func _node(params: Dictionary) -> Node:
	var path := str(params.get("node_path", params.get("path", "")))
	if path.is_empty() or path == ".": return get_tree().current_scene
	return get_node_or_null(NodePath(path))


func _get_node_properties(params: Dictionary) -> Dictionary:
	var node := _node(params)
	if node == null: return _error("Runtime node not found")
	var cursor_result := _decode_offset_cursor(str(params.get("cursor", "")), "p1")
	if cursor_result.has("__error__"): return cursor_result
	var offset: int = cursor_result.offset
	var max_properties := clampi(int(params.get("max_properties", DEFAULT_PAGE_SIZE)), 1, MAX_PAGE_SIZE)
	var properties := {}
	var requested: Array = params.get("properties", [])
	var available: Array[Dictionary] = []
	for item in node.get_property_list():
		var name := str(item.get("name", ""))
		if (requested.is_empty() and int(item.get("usage", 0)) & PROPERTY_USAGE_STORAGE) or name in requested:
			available.append(item)
	if offset > available.size(): return _error("Runtime property cursor is no longer valid")
	var page_end := mini(offset + max_properties, available.size())
	for index in range(offset, page_end):
		var name := str(available[index].get("name", ""))
		properties[name] = _json_value(node.get(name))
	return {
		"node_path": str(node.get_path()),
		"type": node.get_class(),
		"properties": properties,
		"count": properties.size(),
		"truncated": page_end < available.size(),
		"next_cursor": _encode_offset_cursor("p1", page_end) if page_end < available.size() else null,
	}


func _set_node_property(params: Dictionary) -> Dictionary:
	var node := _node(params)
	if node == null: return _error("Runtime node not found")
	var property_name := str(params.get("property", ""))
	if not _has_property(node, property_name): return _error("Property not found: %s" % property_name)
	node.set(property_name, _coerce_value(node.get(property_name), params.get("value")))
	return {"updated": true, "node_path": str(node.get_path()), "property": property_name, "value": _json_value(node.get(property_name))}


func _call_node_method(params: Dictionary) -> Dictionary:
	var node := _node(params)
	if node == null: return _error("Runtime node not found")
	var method_name := str(params.get("__method__", params.get("method", "")))
	if method_name.is_empty() or method_name.begins_with("_") or not node.has_method(method_name): return _error("A public node method is required")
	var arguments: Array = params.get("arguments", [])
	if arguments.size() > 8: return _error("At most 8 method arguments are allowed")
	return {"called": true, "method": method_name, "result": _json_value(node.callv(method_name, arguments))}


func _get_runtime_status() -> Dictionary:
	_ensure_typed_runtime_id()
	return {
		"connected": true,
		"playing": true,
		"scene": get_tree().current_scene.scene_file_path if get_tree().current_scene else "",
		"typed_actions": _typed_action_status(),
	}


func _ensure_typed_runtime_id() -> void:
	if not _typed_runtime_id.is_empty():
		return
	var source := "%s:%d:%d" % [
		ProjectSettings.globalize_path("res://"),
		OS.get_process_id(),
		Time.get_ticks_usec(),
	]
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(source.to_utf8_buffer())
	_typed_runtime_id = hashing.finish().hex_encode().substr(0, 32)


func _typed_action_status() -> Dictionary:
	var loaded := _load_typed_manifest()
	if loaded.has("__error__"):
		return {
			"available": false,
			"reason": loaded.__error__,
			"runtime_id": _typed_runtime_id,
		}
	var manifest: Dictionary = loaded.manifest
	var actions: Array[Dictionary] = []
	for action in manifest.actions:
		actions.append({
			"id": action.id,
			"kind": action.kind,
			"thread": action.thread,
			"target": action.target.duplicate(true),
		})
	var maximum := int(manifest.authority.max_actions)
	return {
		"available": true,
		"schema_version": 1,
		"manifest_id": manifest.manifest_id,
		"manifest_digest": loaded.digest,
		"project_id": _typed_project_id(),
		"session_id": _typed_session_id(),
		"runtime_id": _typed_runtime_id,
		"authority_id": _typed_authority_id(),
		"remaining_budget": maxi(0, maximum - _typed_action_count),
		"actions": actions,
	}


func _execute_typed_action(params: Dictionary) -> Dictionary:
	var reserved := _reserve_typed_action(params)
	if reserved.has("__error__"):
		return reserved
	var boundary := {"reservation_id": reserved.reservation_id}
	var committed := _commit_typed_action(boundary)
	if committed.has("__error__"):
		return committed
	return _finalize_typed_action(boundary)


func _reserve_typed_action(params: Dictionary) -> Dictionary:
	_expire_typed_action_reservation()
	if not _typed_reservation.is_empty():
		return _typed_error("action_in_progress")
	var resolved := _resolve_typed_action(params)
	if resolved.has("__error__"):
		return resolved
	var snapshot := _capture_typed_action_snapshot(resolved.declared)
	if snapshot.has("__error__"):
		return snapshot
	var authority_error := _typed_action_authority_error(resolved.manifest.authority)
	if not authority_error.is_empty():
		return _typed_error(authority_error)
	var reservation_id := _new_typed_reservation_id(str(resolved.declared.id))
	_typed_reservation = {
		"id": reservation_id,
		"created_msec": Time.get_ticks_msec(),
		"params": params.duplicate(true),
		"declared": resolved.declared.duplicate(true),
		"manifest_digest": resolved.digest,
		"snapshot": snapshot,
		"committed": false,
		"rollback_only": false,
	}
	return {"status": "reserved", "reservation_id": reservation_id}


func _commit_typed_action(params: Dictionary) -> Dictionary:
	var reservation_error := _typed_reservation_error(params)
	if not reservation_error.is_empty():
		return _typed_error(reservation_error)
	if bool(_typed_reservation.rollback_only):
		return _typed_error("reservation_rollback_required")
	var resolved := _resolve_typed_action(_typed_reservation.params)
	if resolved.has("__error__"):
		_clear_typed_reservation(false)
		return resolved
	if resolved.digest != _typed_reservation.manifest_digest \
		or resolved.declared != _typed_reservation.declared:
		_clear_typed_reservation(false)
		return _typed_error("reservation_contract_drift")
	var authority_error := _typed_action_authority_error(resolved.manifest.authority)
	if not authority_error.is_empty():
		_clear_typed_reservation(false)
		return _typed_error(authority_error)
	var current := _capture_typed_action_snapshot(resolved.declared)
	if current.has("__error__"):
		_clear_typed_reservation(false)
		return current
	if not _typed_snapshots_match(
		resolved.declared,
		current,
		_typed_reservation.snapshot,
	):
		_clear_typed_reservation(false)
		return _typed_error("target_drift_before_commit")
	var arguments: Dictionary = _typed_reservation.params.action.arguments
	var applied := (
		_apply_typed_input_action(resolved.declared, arguments, _typed_reservation.snapshot)
		if str(resolved.declared.kind) == "input_action"
		else _apply_typed_property_action(
			resolved.declared,
			arguments,
			_typed_reservation.snapshot,
		)
	)
	if applied.has("__error__"):
		if "rollback_failed" in str(applied.__error__):
			# Keep ownership so frame processing can continue fail-closed rollback attempts.
			_typed_reservation.committed = true
			_typed_reservation.rollback_only = true
		else:
			_clear_typed_reservation(false)
		return applied
	_typed_reservation.committed = true
	_typed_reservation.readback = applied.readback
	return {
		"status": "pending_commit",
		"reservation_id": _typed_reservation.id,
	}


func _finalize_typed_action(params: Dictionary) -> Dictionary:
	var reservation_error := _typed_reservation_error(params)
	if not reservation_error.is_empty():
		return _typed_error(reservation_error)
	if bool(_typed_reservation.rollback_only):
		return _typed_error("reservation_rollback_required")
	if not bool(_typed_reservation.committed):
		return _typed_error("reservation_not_committed")
	var resolved := _resolve_typed_action(_typed_reservation.params)
	if resolved.has("__error__"):
		_clear_typed_reservation(true)
		return resolved
	var arguments: Dictionary = _typed_reservation.params.action.arguments
	var measured := _measure_typed_action_effect(resolved.declared, arguments)
	if measured.has("__error__"):
		_clear_typed_reservation(true)
		return measured
	var authority_error := _typed_action_authority_error(resolved.manifest.authority)
	if not authority_error.is_empty():
		_clear_typed_reservation(true)
		return _typed_error(authority_error)
	_commit_typed_action_authority()
	var maximum := int(resolved.manifest.authority.max_actions)
	var result := {
		"status": "applied",
		"schema_version": 1,
		"manifest_id": resolved.manifest.manifest_id,
		"manifest_digest": resolved.digest,
		"action_id": resolved.declared.id,
		"kind": resolved.declared.kind,
		"target": resolved.declared.target.duplicate(true),
		"readback": measured.readback,
		"budget": {
			"used": _typed_action_count,
			"remaining": maxi(0, maximum - _typed_action_count),
			"limit": maximum,
		},
	}
	_clear_typed_reservation(false)
	return result


func _rollback_typed_action(params: Dictionary) -> Dictionary:
	var reservation_error := _typed_reservation_error(params)
	if not reservation_error.is_empty():
		return _typed_error(reservation_error)
	var rollback_error := _clear_typed_reservation(true)
	if not rollback_error.is_empty():
		return _typed_error(rollback_error)
	return {"status": "rolled_back"}


func _resolve_typed_action(params: Dictionary) -> Dictionary:
	_ensure_typed_runtime_id()
	var request_error := _validate_typed_action_request(params)
	if not request_error.is_empty():
		return _typed_error(request_error)
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return _typed_error("main_thread_mismatch")
	var loaded := _load_typed_manifest()
	if loaded.has("__error__"):
		return loaded
	var manifest: Dictionary = loaded.manifest
	if str(params.project_id) != _typed_project_id():
		return _typed_error("project_identity_mismatch")
	if str(params.session_id) != _typed_session_id():
		return _typed_error("session_identity_mismatch")
	if str(params.runtime_id) != _typed_runtime_id:
		return _typed_error("runtime_identity_mismatch")
	if str(params.authority_id) != _typed_authority_id():
		return _typed_error("authority_mismatch")
	if str(params.manifest_id) != str(manifest.manifest_id):
		return _typed_error("manifest_identity_mismatch")
	if str(params.manifest_digest) != str(loaded.digest):
		return _typed_error("manifest_digest_mismatch")
	var requested: Dictionary = params.action
	var declared := _find_declared_action(manifest, str(requested.id))
	if declared.is_empty():
		return _typed_error("unknown_action")
	if str(declared.kind) != str(requested.kind) or declared.target != requested.target:
		return _typed_error("action_contract_mismatch")
	if str(declared.thread) == "physics":
		return _typed_error("physics_thread_unavailable")
	if str(declared.thread) != "main":
		return _typed_error("thread_owner_mismatch")
	var argument_error := _validate_typed_action_arguments(declared, requested.arguments)
	if not argument_error.is_empty():
		return _typed_error(argument_error)
	return {
		"manifest": manifest,
		"digest": loaded.digest,
		"declared": declared,
	}


func _load_typed_manifest() -> Dictionary:
	var path_error := _typed_path_error(TYPED_ACTION_MANIFEST_PATH)
	if not path_error.is_empty():
		return _typed_error(path_error)
	if not FileAccess.file_exists(TYPED_ACTION_MANIFEST_PATH):
		return _typed_error("manifest_absent")
	var size := FileAccess.get_size(TYPED_ACTION_MANIFEST_PATH)
	if size < 1 or size > MAX_TYPED_ACTION_MANIFEST_BYTES:
		return _typed_error("manifest_size_invalid")
	var digest := FileAccess.get_sha256(TYPED_ACTION_MANIFEST_PATH)
	if digest.is_empty():
		return _typed_error("manifest_digest_unavailable")
	if not _typed_manifest_digest.is_empty() and digest != _typed_manifest_digest:
		return _typed_error("manifest_drift")
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(TYPED_ACTION_MANIFEST_PATH))
	if not parsed is Dictionary:
		return _typed_error("manifest_json_invalid")
	var manifest: Dictionary = parsed
	var shape_error := _validate_typed_manifest(manifest)
	if not shape_error.is_empty():
		return _typed_error(shape_error)
	var identity_error := _validate_typed_manifest_identity(manifest)
	if not identity_error.is_empty():
		return _typed_error(identity_error)
	if _typed_manifest_digest.is_empty():
		_typed_manifest_digest = digest
		_typed_manifest = manifest.duplicate(true)
		_typed_action_count = 0
		_typed_rate_count = 0
		_typed_rate_window_start_msec = Time.get_ticks_msec()
	elif manifest != _typed_manifest:
		return _typed_error("manifest_replacement")
	return {"manifest": _typed_manifest, "digest": _typed_manifest_digest}


func _validate_typed_manifest(manifest: Dictionary) -> String:
	if not _keys_exact(manifest, [
		"schema_version", "manifest_id", "project_id", "session_id", "authority", "actions",
	]):
		return "manifest_shape_invalid"
	if not _is_integer_number(manifest.schema_version) or int(manifest.schema_version) != 1:
		return "manifest_version_unsupported"
	for field in ["manifest_id", "project_id", "session_id"]:
		if not manifest[field] is String or not _valid_identity(str(manifest[field])):
			return "manifest_identity_invalid"
	if not manifest.authority is Dictionary or not _keys_exact(
		manifest.authority, ["id", "max_actions", "rate_limit"]
	):
		return "manifest_shape_invalid"
	var authority: Dictionary = manifest.authority
	if not authority.id is String or not _valid_identity(str(authority.id)):
		return "manifest_identity_invalid"
	if not _is_integer_number(authority.max_actions) or int(authority.max_actions) < 1 or int(authority.max_actions) > 10000:
		return "manifest_budget_invalid"
	if not authority.rate_limit is Dictionary or not _keys_exact(
		authority.rate_limit, ["max_actions", "window_msec"]
	):
		return "manifest_shape_invalid"
	var rate: Dictionary = authority.rate_limit
	if not _is_integer_number(rate.max_actions) or int(rate.max_actions) < 1 or int(rate.max_actions) > 100:
		return "manifest_rate_invalid"
	if not _is_integer_number(rate.window_msec) or int(rate.window_msec) < 10 or int(rate.window_msec) > 60000:
		return "manifest_rate_invalid"
	if not manifest.actions is Array or manifest.actions.is_empty() or manifest.actions.size() > 64:
		return "manifest_actions_invalid"
	var ids := {}
	for value in manifest.actions:
		if not value is Dictionary:
			return "manifest_action_invalid"
		var action: Dictionary = value
		var action_error := _validate_typed_manifest_action(action)
		if not action_error.is_empty():
			return action_error
		if ids.has(str(action.id)):
			return "manifest_action_duplicate"
		ids[str(action.id)] = true
	return ""


func _validate_typed_manifest_action(action: Dictionary) -> String:
	if not _keys_exact(action, ["id", "kind", "thread", "target", "arguments", "readback"]):
		return "manifest_action_invalid"
	if not action.id is String or not _valid_identity(str(action.id)) \
		or not action.kind is String or not action.thread is String \
		or not action.target is Dictionary:
		return "manifest_action_invalid"
	if str(action.thread) not in ["main", "physics"]:
		return "manifest_action_invalid"
	if not _selector_values_allowed(str(action.id), action.target):
		return "forbidden_surface"
	if str(action.kind) == "input_action":
		if not _keys_exact(action.target, ["action"]):
			return "manifest_action_invalid"
		if not action.target.action is String or not _valid_identity(str(action.target.action)):
			return "manifest_action_invalid"
		if not action.arguments is Dictionary or not _keys_exact(
			action.arguments, ["pressed", "strength"]
		):
			return "manifest_action_invalid"
		if not action.arguments.pressed is Array or action.arguments.pressed.is_empty() or action.arguments.pressed.size() > 2:
			return "manifest_action_invalid"
		for pressed in action.arguments.pressed:
			if not pressed is bool:
				return "manifest_action_invalid"
		if not _array_values_unique(action.arguments.pressed):
			return "manifest_action_invalid"
		if not action.arguments.strength is Dictionary or not _keys_exact(
			action.arguments.strength, ["minimum", "maximum"]
		):
			return "manifest_action_invalid"
		var minimum = action.arguments.strength.minimum
		var maximum = action.arguments.strength.maximum
		if not _is_number(minimum) or not _is_number(maximum):
			return "manifest_action_invalid"
		if float(minimum) < 0.0 or float(maximum) > 1.0 or float(minimum) > float(maximum):
			return "manifest_action_invalid"
		if not action.readback is Dictionary or not _keys_exact(action.readback, ["kind"]):
			return "manifest_action_invalid"
		if str(action.readback.kind) != "input_action":
			return "manifest_action_invalid"
		return ""
	if str(action.kind) == "set_property":
		if not _keys_exact(action.target, [
			"node_path", "node_type", "script_path", "script_sha256", "property",
		]):
			return "manifest_action_invalid"
		if not action.target.node_path is String or not _valid_node_path(str(action.target.node_path)):
			return "manifest_action_invalid"
		if not action.target.script_path is String \
			or not _valid_script_path(str(action.target.script_path)):
			return "manifest_action_invalid"
		if not action.target.script_sha256 is String \
			or not _valid_digest(str(action.target.script_sha256)):
			return "manifest_action_invalid"
		if not action.target.node_type is String \
			or not _valid_identity(str(action.target.node_type)) \
			or not action.target.property is String \
			or not _valid_identity(str(action.target.property)):
			return "manifest_action_invalid"
		if not action.arguments is Dictionary or not _keys_exact(action.arguments, ["value"]):
			return "manifest_action_invalid"
		if not action.arguments.value is Dictionary:
			return "manifest_action_invalid"
		var value_error := _validate_value_contract(action.arguments.value)
		if not value_error.is_empty():
			return value_error
		if not action.readback is Dictionary or not _keys_exact(
			action.readback, ["kind", "node_path", "property"]
		):
			return "manifest_action_invalid"
		if not action.readback.kind is String \
			or str(action.readback.kind) != "property" \
			or not action.readback.node_path is String \
			or not _valid_node_path(str(action.readback.node_path)) \
			or str(action.readback.node_path) != str(action.target.node_path) \
			or not action.readback.property is String \
			or str(action.readback.property) != str(action.target.property):
			return "manifest_action_invalid"
		return ""
	return "manifest_action_kind_invalid"


func _validate_value_contract(contract: Dictionary) -> String:
	if not contract.get("type") is String:
		return "manifest_action_invalid"
	var kind := str(contract.get("type", ""))
	if kind == "boolean":
		return "" if _keys_exact(contract, ["type"]) else "manifest_action_invalid"
	if kind in ["integer", "number"]:
		if not _keys_exact(contract, ["type", "minimum", "maximum"]):
			return "manifest_action_invalid"
		if not _is_number(contract.minimum) or not _is_number(contract.maximum):
			return "manifest_action_invalid"
		if float(contract.minimum) < -1000000.0 or float(contract.maximum) > 1000000.0 or float(contract.minimum) > float(contract.maximum):
			return "manifest_action_invalid"
		return ""
	if kind == "string":
		if not _keys_exact(contract, ["type", "enum"]) or not contract.enum is Array:
			return "manifest_action_invalid"
		if contract.enum.is_empty() or contract.enum.size() > 32:
			return "manifest_action_invalid"
		for value in contract.enum:
			if not value is String or str(value).length() > 128:
				return "manifest_action_invalid"
		if not _array_values_unique(contract.enum):
			return "manifest_action_invalid"
		return ""
	return "manifest_action_invalid"


func _validate_typed_manifest_identity(manifest: Dictionary) -> String:
	if _typed_project_id().is_empty() or str(manifest.project_id) != _typed_project_id():
		return "project_identity_mismatch"
	if _typed_session_id().is_empty() or str(manifest.session_id) != _typed_session_id():
		return "session_identity_mismatch"
	if _typed_authority_id().is_empty() or str(manifest.authority.id) != _typed_authority_id():
		return "authority_mismatch"
	return ""


func _validate_typed_action_request(params: Dictionary) -> String:
	if not _keys_exact(params, TYPED_ACTION_REQUEST_KEYS):
		return "request_shape_invalid"
	for field in ["project_id", "session_id", "runtime_id", "authority_id", "manifest_id"]:
		if not params[field] is String or not _valid_identity(str(params[field])):
			return "request_identity_invalid"
	if not params.manifest_digest is String or not _valid_digest(str(params.manifest_digest)):
		return "request_digest_invalid"
	if not params.action is Dictionary:
		return "action_shape_invalid"
	var action: Dictionary = params.action
	if not _keys_exact(action, ["id", "kind", "target", "arguments"]):
		return "action_shape_invalid"
	if not action.id is String or not _valid_identity(str(action.id)) \
		or not action.kind is String or not action.target is Dictionary \
		or not action.arguments is Dictionary:
		return "action_shape_invalid"
	if str(action.kind) == "input_action":
		if not _keys_exact(action.target, ["action"]) or not _keys_exact(action.arguments, ["pressed", "strength"]):
			return "action_shape_invalid"
		if not action.target.action is String or not _valid_identity(str(action.target.action)):
			return "action_shape_invalid"
		if not action.arguments.pressed is bool or not _is_number(action.arguments.strength):
			return "argument_type_mismatch"
		return ""
	if str(action.kind) == "set_property":
		if not _keys_exact(action.target, [
			"node_path", "node_type", "script_path", "script_sha256", "property",
		]) or not _keys_exact(action.arguments, ["value"]):
			return "action_shape_invalid"
		if not action.target.node_path is String \
			or not _valid_node_path(str(action.target.node_path)) \
			or not action.target.node_type is String \
			or not _valid_identity(str(action.target.node_type)) \
			or not action.target.script_path is String \
			or not _valid_script_path(str(action.target.script_path)) \
			or not action.target.script_sha256 is String \
			or not _valid_digest(str(action.target.script_sha256)) \
			or not action.target.property is String \
			or not _valid_identity(str(action.target.property)):
			return "action_shape_invalid"
		if not _json_scalar(action.arguments.value):
			return "argument_type_mismatch"
		return ""
	return "unknown_action_kind"


func _validate_typed_action_arguments(declared: Dictionary, arguments: Dictionary) -> String:
	if str(declared.kind) == "input_action":
		if arguments.pressed not in declared.arguments.pressed:
			return "argument_not_allowed"
		var strength := float(arguments.strength)
		if strength < float(declared.arguments.strength.minimum) or strength > float(declared.arguments.strength.maximum):
			return "argument_out_of_bounds"
		return ""
	var value = arguments.value
	var contract: Dictionary = declared.arguments.value
	if not _matches_value_type(value, str(contract.type)):
		return "argument_type_mismatch"
	if str(contract.type) in ["integer", "number"]:
		if float(value) < float(contract.minimum) or float(value) > float(contract.maximum):
			return "argument_out_of_bounds"
	elif str(contract.type) == "string" and value not in contract.enum:
		return "argument_not_allowed"
	return ""


func _typed_action_authority_error(authority: Dictionary) -> String:
	if _typed_action_count >= int(authority.max_actions):
		return "action_budget_exhausted"
	var now := Time.get_ticks_msec()
	var window_msec := int(authority.rate_limit.window_msec)
	if _typed_rate_window_start_msec == 0 or now - _typed_rate_window_start_msec >= window_msec:
		_typed_rate_window_start_msec = now
		_typed_rate_count = 0
	if _typed_rate_count >= int(authority.rate_limit.max_actions):
		return "rate_limit_exceeded"
	return ""


func _commit_typed_action_authority() -> void:
	_typed_action_count += 1
	_typed_rate_count += 1


func _apply_typed_input_action(
	declared: Dictionary,
	arguments: Dictionary,
	snapshot: Dictionary,
) -> Dictionary:
	var action := StringName(str(declared.target.action))
	if bool(arguments.pressed):
		Input.action_press(action, float(arguments.strength))
	else:
		Input.action_release(action)
	var measured := _measure_typed_action_effect(declared, arguments)
	if measured.has("__error__"):
		var rollback_error := _restore_typed_action_snapshot(declared, snapshot)
		if not rollback_error.is_empty():
			return _typed_error("rollback_failed")
		return measured
	return measured


func _apply_typed_property_action(
	declared: Dictionary,
	arguments: Dictionary,
	snapshot: Dictionary,
) -> Dictionary:
	# Re-resolve and hash immediately before the only property mutation.
	var before := _capture_typed_action_snapshot(declared)
	if before.has("__error__"):
		return before
	if not _typed_snapshots_match(declared, before, snapshot):
		return _typed_error("target_drift_before_commit")
	var node: Node = before.node
	node.set(str(declared.target.property), arguments.value)
	# Re-resolve and hash immediately after mutation, then verify the exact effect.
	var measured := _measure_typed_action_effect(declared, arguments)
	if measured.has("__error__"):
		var rollback_error := _restore_typed_action_snapshot(declared, snapshot)
		if not rollback_error.is_empty():
			return _typed_error("rollback_failed")
		return measured
	return measured


func _measure_typed_action_effect(declared: Dictionary, arguments: Dictionary) -> Dictionary:
	if str(declared.kind) == "input_action":
		var action := StringName(str(declared.target.action))
		if not InputMap.has_action(action):
			return _typed_error("target_action_missing")
		var pressed := Input.is_action_pressed(action)
		var strength := Input.get_action_strength(action)
		var expected_strength := float(arguments.strength) if bool(arguments.pressed) else 0.0
		if pressed != bool(arguments.pressed) or strength != expected_strength:
			return _typed_error("setter_effect_mismatch")
		return {"readback": {
			"kind": "input_action",
			"action": str(action),
			"pressed": pressed,
			"strength": strength,
		}}
	var target := _resolve_typed_property_target(declared)
	if target.has("__error__"):
		return target
	var measured = target.node.get(str(declared.target.property))
	if not _typed_values_equal(measured, arguments.value, str(declared.arguments.value.type)):
		return _typed_error("setter_effect_mismatch")
	return {"readback": {
		"kind": "property",
		"node_path": str(target.node.get_path()),
		"node_type": target.node.get_class(),
		"property": str(declared.target.property),
		"value": measured,
		"script_sha256": target.script_sha256,
	}}


func _capture_typed_action_snapshot(declared: Dictionary) -> Dictionary:
	if str(declared.kind) == "input_action":
		var action := StringName(str(declared.target.action))
		if not InputMap.has_action(action):
			return _typed_error("target_action_missing")
		return {
			"kind": "input_action",
			"action": str(action),
			"pressed": Input.is_action_pressed(action),
			"strength": Input.get_action_strength(action),
		}
	var target := _resolve_typed_property_target(declared)
	if target.has("__error__"):
		return target
	var property_name := str(declared.target.property)
	var value = target.node.get(property_name)
	if not _matches_value_type(value, str(declared.arguments.value.type)):
		return _typed_error("target_type_drift")
	return {
		"kind": "set_property",
		"node": target.node,
		"instance_id": target.node.get_instance_id(),
		"node_path": str(target.node.get_path()),
		"node_type": target.node.get_class(),
		"script_path": str(declared.target.script_path),
		"script_sha256": target.script_sha256,
		"property": property_name,
		"value": value,
	}


func _resolve_typed_property_target(declared: Dictionary) -> Dictionary:
	var target: Dictionary = declared.target
	var script_path := str(target.script_path)
	var path_error := _typed_path_error(script_path)
	if not path_error.is_empty():
		return _typed_error("script_target_reparse")
	var script_sha256 := FileAccess.get_sha256(script_path)
	if script_sha256 != str(target.script_sha256):
		return _typed_error("target_script_drift")
	var node := get_node_or_null(NodePath(str(target.node_path)))
	if node == null:
		return _typed_error("target_missing")
	if node.get_class() != str(target.node_type):
		return _typed_error("target_type_drift")
	var script = node.get_script()
	if script == null or str(script.resource_path) != script_path:
		return _typed_error("target_script_drift")
	if not _has_property(node, str(target.property)):
		return _typed_error("target_property_missing")
	return {"node": node, "script_sha256": script_sha256}


func _typed_snapshots_match(
	declared: Dictionary,
	current: Dictionary,
	reserved: Dictionary,
) -> bool:
	if current.get("kind") != reserved.get("kind"):
		return false
	if current.kind == "input_action":
		return current.action == reserved.action \
			and current.pressed == reserved.pressed \
			and current.strength == reserved.strength
	return current.node == reserved.node \
		and current.instance_id == reserved.instance_id \
		and current.node_path == reserved.node_path \
		and current.node_type == reserved.node_type \
		and current.script_path == reserved.script_path \
		and current.script_sha256 == reserved.script_sha256 \
		and current.property == reserved.property \
		and _typed_values_equal(
			current.value,
			reserved.value,
			str(declared.arguments.value.type),
		)


func _restore_typed_action_snapshot(declared: Dictionary, snapshot: Dictionary) -> String:
	if snapshot.kind == "input_action":
		var action := StringName(str(snapshot.action))
		if not InputMap.has_action(action):
			return "rollback_target_missing"
		if bool(snapshot.pressed):
			Input.action_press(action, float(snapshot.strength))
		else:
			Input.action_release(action)
		if Input.is_action_pressed(action) != bool(snapshot.pressed) \
			or Input.get_action_strength(action) != float(snapshot.strength):
			return "rollback_effect_mismatch"
		return ""
	var node = snapshot.node
	if not is_instance_valid(node) \
		or node.get_instance_id() != int(snapshot.instance_id) \
		or str(node.get_path()) != str(snapshot.node_path) \
		or node.get_class() != str(snapshot.node_type):
		return "rollback_target_drift"
	var script = node.get_script()
	if script == null or str(script.resource_path) != str(snapshot.script_path):
		return "rollback_target_drift"
	node.set(str(snapshot.property), snapshot.value)
	if not _typed_values_equal(
		node.get(str(snapshot.property)),
		snapshot.value,
		str(declared.arguments.value.type),
	):
		return "rollback_effect_mismatch"
	return ""


func _typed_values_equal(actual, expected, expected_type: String) -> bool:
	if not _matches_value_type(actual, expected_type) \
		or not _matches_value_type(expected, expected_type):
		return false
	if expected_type == "integer":
		return int(actual) == int(expected)
	if expected_type == "number":
		return float(actual) == float(expected)
	return actual == expected


func _typed_reservation_error(params: Dictionary) -> String:
	_expire_typed_action_reservation()
	if not _keys_exact(params, ["reservation_id"]) \
		or not params.reservation_id is String \
		or not _valid_identity(str(params.reservation_id)):
		return "reservation_shape_invalid"
	if _typed_reservation.is_empty():
		return "reservation_missing"
	if str(params.reservation_id) != str(_typed_reservation.id):
		return "reservation_identity_mismatch"
	return ""


func _clear_typed_reservation(rollback: bool) -> String:
	if _typed_reservation.is_empty():
		return ""
	if rollback and bool(_typed_reservation.get("committed", false)):
		var rollback_error := _restore_typed_action_snapshot(
			_typed_reservation.declared,
			_typed_reservation.snapshot,
		)
		if not rollback_error.is_empty():
			return rollback_error
	_typed_reservation.clear()
	return ""


func _expire_typed_action_reservation() -> void:
	if _typed_reservation.is_empty():
		return
	var age := Time.get_ticks_msec() - int(_typed_reservation.created_msec)
	if age >= TYPED_ACTION_RESERVATION_TTL_MSEC:
		_clear_typed_reservation(true)


func _new_typed_reservation_id(action_id: String) -> String:
	var source := "%s:%s:%d" % [_typed_runtime_id, action_id, Time.get_ticks_usec()]
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(source.to_utf8_buffer())
	return hashing.finish().hex_encode().substr(0, 32)


func _find_declared_action(manifest: Dictionary, action_id: String) -> Dictionary:
	for value in manifest.actions:
		if str(value.id) == action_id:
			return value
	return {}


func _typed_path_error(path: String) -> String:
	if not path.begins_with("res://") or ".." in path or path.contains("\\"):
		return "manifest_path_escape"
	var relative := path.trim_prefix("res://")
	var parts := relative.split("/", false)
	var current_path := "res://"
	for part in parts:
		var directory := DirAccess.open(current_path)
		if directory == null:
			return "" if part == parts[-1] else "manifest_path_unavailable"
		if directory.is_link(part):
			return "manifest_path_reparse"
		current_path = current_path.path_join(part)
	return ""


func _keys_exact(value: Dictionary, required: Array) -> bool:
	if value.size() != required.size():
		return false
	for key in required:
		if not value.has(key):
			return false
	return true


func _array_values_unique(values: Array) -> bool:
	for index in range(values.size()):
		for prior in range(index):
			if values[index] == values[prior]:
				return false
	return true


func _valid_node_path(value: String) -> bool:
	if value.length() > 500:
		return false
	var pattern := RegEx.new()
	pattern.compile("^/root/[A-Za-z0-9_./:-]+$")
	return pattern.search(value) != null


func _valid_script_path(value: String) -> bool:
	if value.length() > 500:
		return false
	var pattern := RegEx.new()
	pattern.compile("^res://[A-Za-z0-9_./-]+[.]gd$")
	return pattern.search(value) != null


func _valid_identity(value: String) -> bool:
	if value.is_empty() or value.length() > 128:
		return false
	var pattern := RegEx.new()
	pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]*$")
	return pattern.search(value) != null


func _valid_digest(value: String) -> bool:
	if value.length() != 64:
		return false
	var pattern := RegEx.new()
	pattern.compile("^[0-9a-f]{64}$")
	return pattern.search(value) != null


func _selector_values_allowed(action_id: String, target: Dictionary) -> bool:
	var values := [action_id]
	values.append_array(target.values())
	for value in values:
		var lowered := str(value).to_lower()
		for term in FORBIDDEN_ACTION_SELECTOR_TERMS:
			if term in lowered:
				return false
	return true


func _typed_project_id() -> String:
	return str(ProjectSettings.get_setting("dcc_mcp/playtest/project_id", ""))


func _typed_session_id() -> String:
	var operator_value := OS.get_environment("DCC_MCP_GODOT_PLAYTEST_SESSION_ID")
	return operator_value if not operator_value.is_empty() else str(
		ProjectSettings.get_setting("dcc_mcp/playtest/session_id", "")
	)


func _typed_authority_id() -> String:
	var operator_value := OS.get_environment("DCC_MCP_GODOT_PLAYTEST_AUTHORITY_ID")
	return operator_value if not operator_value.is_empty() else str(
		ProjectSettings.get_setting("dcc_mcp/playtest/authority_id", "")
	)


func _is_number(value) -> bool:
	return value is int or value is float


func _is_integer_number(value) -> bool:
	return value is int or (value is float and is_equal_approx(value, round(value)))


func _json_scalar(value) -> bool:
	return value is bool or value is int or value is float or value is String


func _matches_value_type(value, expected: String) -> bool:
	if expected == "boolean": return value is bool
	if expected == "integer": return _is_integer_number(value) and not value is bool
	if expected == "number": return _is_number(value) and not value is bool
	if expected == "string": return value is String
	return false


func _typed_error(code: String) -> Dictionary:
	return {"__error__": "typed_action_rejected:%s" % code}


func _screenshot(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", "res://.dcc-mcp/game.png"))
	if not _safe_png_path(path): return _error("Screenshot path must be a .png below res://")
	var image := get_viewport().get_texture().get_image()
	var format_name := "rgba8" if image.get_format() == Image.FORMAT_RGBA8 else ("rgb8" if image.get_format() == Image.FORMAT_RGB8 else "")
	if format_name.is_empty() or image.has_mipmaps():
		return _error("Game screenshot requires a non-mipmapped RGB8 or RGBA8 viewport image")
	var directory := ProjectSettings.globalize_path(path.get_base_dir())
	var mkdir_error := DirAccess.make_dir_recursive_absolute(directory)
	if mkdir_error != OK: return _error("Unable to create game screenshot directory: %s" % error_string(mkdir_error))
	# Godot documents get_data() as a copy. Capture that immutable snapshot while
	# the viewport belongs to this thread; the adapter encodes it after this call.
	var pixels := image.get_data()
	var staging_path := "%s.dcc-mcp-%d.raw" % [path, Time.get_ticks_usec()]
	var staging_file := FileAccess.open(staging_path, FileAccess.WRITE)
	if staging_file == null: return _error("Unable to stage game screenshot pixels")
	staging_file.store_buffer(pixels)
	var write_error := staging_file.get_error()
	staging_file.close()
	if write_error != OK:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(staging_path))
		return _error("Unable to stage game screenshot pixels: %s" % error_string(write_error))
	return {
		"path": path,
		"width": image.get_width(),
		"height": image.get_height(),
		"__raw_snapshot__": {
			"path": ProjectSettings.globalize_path(staging_path),
			"output_path": ProjectSettings.globalize_path(path),
			"format": format_name,
			"byte_length": pixels.size(),
		},
	}


func _capture_frames(params: Dictionary) -> Dictionary:
	var count := clampi(int(params.get("count", 1)), 1, 10)
	var base := str(params.get("path", "res://.dcc-mcp/frames/frame"))
	if not base.begins_with("res://") or ".." in base: return _error("Frame path must remain below res://")
	var paths: Array[String] = []
	for index in range(count):
		var path := "%s_%03d.png" % [base, index]
		var image := get_viewport().get_texture().get_image()
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path.get_base_dir()))
		var save_error := image.save_png(path)
		if save_error != OK: return _error("Unable to save game screenshot: %s" % error_string(save_error))
		paths.append(path)
	return {"paths": paths, "count": paths.size(), "note": "Frames are captured from the current rendered frame."}


func _monitor_properties(params: Dictionary) -> Dictionary:
	var targets: Array = params.get("targets", [])
	var samples: Array[Dictionary] = []
	for target in targets.slice(0, MAX_RESULTS):
		if not target is Dictionary: continue
		var node := _node(target)
		var property_name := str(target.get("property", ""))
		if node != null and _has_property(node, property_name): samples.append({"node_path": str(node.get_path()), "property": property_name, "value": _json_value(node.get(property_name))})
	return {"samples": samples, "frame": Engine.get_process_frames()}


func _simulate_key(params: Dictionary) -> Dictionary:
	var event := InputEventKey.new()
	event.keycode = int(params.get("keycode", 0))
	event.physical_keycode = int(params.get("physical_keycode", 0))
	event.pressed = bool(params.get("pressed", true))
	event.echo = bool(params.get("echo", false))
	Input.parse_input_event(event)
	_record_event("key", params)
	return {"simulated": true, "type": "key", "pressed": event.pressed}


func _simulate_mouse_click(params: Dictionary) -> Dictionary:
	var event := InputEventMouseButton.new()
	event.position = _vector2(params.get("position", [0, 0]))
	event.global_position = event.position
	event.button_index = int(params.get("button", MOUSE_BUTTON_LEFT)) as MouseButton
	event.pressed = bool(params.get("pressed", true))
	Input.parse_input_event(event)
	_record_event("mouse_click", params)
	return {"simulated": true, "type": "mouse_click", "position": _json_value(event.position), "pressed": event.pressed}


func _simulate_mouse_move(params: Dictionary) -> Dictionary:
	var event := InputEventMouseMotion.new()
	event.position = _vector2(params.get("position", [0, 0]))
	event.global_position = event.position
	event.relative = _vector2(params.get("relative", [0, 0]))
	Input.parse_input_event(event)
	_record_event("mouse_move", params)
	return {"simulated": true, "type": "mouse_move", "position": _json_value(event.position)}


func _simulate_action(params: Dictionary) -> Dictionary:
	var action := StringName(str(params.get("action", "")))
	if not InputMap.has_action(action): return _error("Input action not found: %s" % action)
	if bool(params.get("pressed", true)): Input.action_press(action, float(params.get("strength", 1.0)))
	else: Input.action_release(action)
	_record_event("action", params)
	return {"simulated": true, "type": "action", "action": str(action), "pressed": bool(params.get("pressed", true))}


func _simulate_sequence(params: Dictionary) -> Dictionary:
	var events: Array = params.get("events", [])
	if events.size() > 100: return _error("Input sequence is limited to 100 events")
	var results: Array[Dictionary] = []
	for item in events:
		if not item is Dictionary: continue
		var kind := str(item.get("type", "action"))
		var result := _simulate_key(item) if kind == "key" else (_simulate_mouse_click(item) if kind == "mouse_click" else (_simulate_mouse_move(item) if kind == "mouse_move" else _simulate_action(item)))
		results.append(result)
	return {"simulated": true, "count": results.size(), "results": results}


func _record_event(kind: String, params: Dictionary) -> void:
	if _recording: _recorded_events.append({"type": kind, "params": params.duplicate(true), "frame": Engine.get_process_frames()})


func _replay_recording(params: Dictionary) -> Dictionary:
	var events: Array = params.get("events", _recorded_events)
	var normalized: Array[Dictionary] = []
	for item in events:
		if not item is Dictionary:
			continue
		var event: Dictionary = item.get("params", item).duplicate(true)
		if item.has("type") and not event.has("type"):
			event["type"] = item.type
		normalized.append(event)
	return _simulate_sequence({"events": normalized})


func _find_nodes_by_script(params: Dictionary) -> Dictionary:
	var root := get_tree().current_scene
	if root == null: return _error("Running game has no current scene")
	var script_path := str(params.get("script_path", ""))
	var paths: Array[String] = []
	_collect_nodes(root, func(node): return node.get_script() != null and node.get_script().resource_path == script_path, paths)
	return {"script_path": script_path, "nodes": paths}


func _get_autoload(params: Dictionary) -> Dictionary:
	var name := str(params.get("name", ""))
	var node := get_node_or_null("/root/%s" % name)
	if node == null: return _error("Autoload not found: %s" % name)
	return {"name": name, "snapshot": _snapshot(node, 0), "properties": _get_node_properties({"node_path": str(node.get_path())}).properties}


func _batch_get_properties(params: Dictionary) -> Dictionary:
	var targets: Array = params.get("targets", [])
	var results: Array[Dictionary] = []
	for target in targets.slice(0, MAX_RESULTS):
		if target is Dictionary: results.append(_get_node_properties(target))
	return {"results": results, "count": results.size()}


func _find_ui_elements(params: Dictionary) -> Dictionary:
	var root := get_tree().current_scene
	if root == null: return _error("Running game has no current scene")
	var cursor_result := _decode_node_cursor(str(params.get("cursor", "")))
	if cursor_result.has("__error__"): return cursor_result
	var cursor: Array[int] = cursor_result.indices
	var max_nodes := clampi(int(params.get("max_nodes", DEFAULT_PAGE_SIZE)), 1, MAX_PAGE_SIZE)
	var text_query := str(params.get("text", "")).to_lower()
	var elements: Array[Dictionary] = []
	var nodes_scanned := 0
	while nodes_scanned < max_nodes:
		var node := _node_at_cursor(root, cursor)
		if node == null: return _error("Runtime UI cursor no longer identifies a node")
		if node is Control and node.is_visible_in_tree():
			var text := str(node.get("text")) if _has_property(node, "text") else ""
			if text_query.is_empty() or text_query in text.to_lower():
				elements.append({"path": str(node.get_path()), "type": node.get_class(), "text": text, "position": _json_value(node.global_position), "size": _json_value(node.size)})
		nodes_scanned += 1
		var next_cursor = _next_node_cursor(root, cursor)
		if next_cursor == null:
			cursor = []
			break
		cursor = next_cursor
	var has_more := not cursor.is_empty()
	return {
		"elements": elements,
		"count": elements.size(),
		"nodes_scanned": nodes_scanned,
		"truncated": has_more,
		"next_cursor": _encode_node_cursor(cursor) if has_more else null,
	}


func _click_button_by_text(params: Dictionary) -> Dictionary:
	var found := _find_ui_elements(params)
	if found.has("__error__"): return found
	for item in found.elements:
		var node := get_node_or_null(NodePath(item.path))
		if node is BaseButton and str(node.text) == str(params.get("text", "")) and not node.disabled:
			node.emit_signal("pressed")
			return {"clicked": true, "path": str(node.get_path()), "text": node.text}
	if found.next_cursor != null:
		return _error("Visible enabled button text was not found in this page; retry click_button_by_text with cursor=%s" % found.next_cursor)
	return _error("Visible enabled button text was not found")


func _wait_for_node(params: Dictionary) -> Dictionary:
	var node := _node(params)
	return {"found": node != null, "node_path": str(node.get_path()) if node else str(params.get("node_path", "")), "frame": Engine.get_process_frames(), "note": "This call checks the current frame."}


func _find_nearby_nodes(params: Dictionary) -> Dictionary:
	var origin_node := _node(params)
	if origin_node == null: return _error("Origin node not found")
	var radius := float(params.get("radius", 100.0))
	var nearby: Array[Dictionary] = []
	var root := get_tree().current_scene
	_collect_nearby(root, origin_node, radius, nearby)
	return {"origin": str(origin_node.get_path()), "radius": radius, "nodes": nearby}


func _navigate_to(params: Dictionary) -> Dictionary:
	var node := _node(params)
	if node is NavigationAgent2D: node.target_position = _vector2(params.get("target", [0, 0]))
	elif node is NavigationAgent3D: node.target_position = _vector3(params.get("target", [0, 0, 0]))
	else: return _error("node_path must identify NavigationAgent2D or NavigationAgent3D")
	return {"updated": true, "node_path": str(node.get_path()), "target": _json_value(node.target_position)}


func _move_to(params: Dictionary) -> Dictionary:
	var node := _node(params)
	var amount := maxf(0.0, float(params.get("amount", params.get("speed", 100.0) * get_process_delta_time())))
	if node is Node2D: node.global_position = node.global_position.move_toward(_vector2(params.get("target", [0, 0])), amount)
	elif node is Node3D: node.global_position = node.global_position.move_toward(_vector3(params.get("target", [0, 0, 0])), amount)
	else: return _error("node_path must identify Node2D or Node3D")
	return {"moved": true, "node_path": str(node.get_path()), "position": _json_value(node.global_position)}


func _assert_node_state(params: Dictionary) -> Dictionary:
	var node := _node(params)
	var failures: Array[String] = []
	if node == null: failures.append("Node not found")
	else:
		for key in (params.get("equals", {}) as Dictionary):
			if not _has_property(node, str(key)) or node.get(str(key)) != params.equals[key]: failures.append("%s did not equal expected value" % key)
	var result := {"passed": failures.is_empty(), "failures": failures, "node_path": str(params.get("node_path", ""))}
	_last_test_report = {"status": "passed" if result.passed else "failed", "assertions": [result]}
	return result


func _assert_screen_text(params: Dictionary) -> Dictionary:
	var found := _find_ui_elements(params)
	if found.has("__error__"): return found
	var result := {"passed": not found.elements.is_empty(), "text": str(params.get("text", "")), "matches": found.elements, "next_cursor": found.next_cursor}
	_last_test_report = {"status": "passed" if result.passed else "failed", "assertions": [result]}
	return result


func _run_test_scenario(params: Dictionary) -> Dictionary:
	var steps: Array = params.get("steps", [])
	if steps.size() > 100: return _error("Test scenario is limited to 100 steps")
	var results: Array[Dictionary] = []
	var passed := true
	for step in steps:
		if not step is Dictionary: continue
		var result := _execute(str(step.get("action", "")), step.get("params", {}))
		results.append(result)
		if result.has("__error__") or result.get("passed") == false: passed = false
	_last_test_report = {"status": "passed" if passed else "failed", "assertions": results, "step_count": results.size()}
	return _last_test_report


func _run_stress_test(params: Dictionary) -> Dictionary:
	var frames := clampi(int(params.get("frames", 60)), 1, MAX_FRAMES)
	var metrics := _get_performance_monitors()
	_last_test_report = {"status": "sampled", "frames_requested": frames, "metrics": metrics, "note": "Metrics are sampled from the current frame; use repeated calls for a time series."}
	return _last_test_report


func _get_performance_monitors() -> Dictionary:
	var monitors := {}
	for monitor in range(Performance.MONITOR_MAX): monitors[str(monitor)] = Performance.get_monitor(monitor)
	return {"fps": Engine.get_frames_per_second(), "frame": Engine.get_process_frames(), "monitors": monitors}


func _collect_nodes(node: Node, predicate: Callable, output: Array[String]) -> void:
	if predicate.call(node): output.append(str(node.get_path()))
	for child in node.get_children(): _collect_nodes(child, predicate, output)


func _collect_nearby(node: Node, origin: Node, radius: float, output: Array[Dictionary]) -> void:
	if node != origin and node is Node2D and origin is Node2D:
		var distance: float = node.global_position.distance_to(origin.global_position)
		if distance <= radius: output.append({"path": str(node.get_path()), "distance": distance})
	elif node != origin and node is Node3D and origin is Node3D:
		var distance: float = node.global_position.distance_to(origin.global_position)
		if distance <= radius: output.append({"path": str(node.get_path()), "distance": distance})
	for child in node.get_children(): _collect_nearby(child, origin, radius, output)


func _has_property(object: Object, property_name: String) -> bool:
	for item in object.get_property_list():
		if str(item.get("name", "")) == property_name: return true
	return false


func _coerce_value(previous, value):
	if previous is Vector2 and value is Array and value.size() >= 2: return _vector2(value)
	if previous is Vector2i and value is Array and value.size() >= 2: return Vector2i(int(value[0]), int(value[1]))
	if previous is Vector3 and value is Array and value.size() >= 3: return _vector3(value)
	if previous is Color and value is String: return Color.from_string(value, previous)
	if previous is StringName: return StringName(str(value))
	if previous is NodePath: return NodePath(str(value))
	return value


func _json_value(value):
	if value == null or value is bool or value is int or value is float or value is String: return value
	if value is StringName or value is NodePath: return str(value)
	if value is Vector2 or value is Vector2i: return [value.x, value.y]
	if value is Vector3 or value is Vector3i: return [value.x, value.y, value.z]
	if value is Color: return [value.r, value.g, value.b, value.a]
	if value is Resource: return {"type": value.get_class(), "path": value.resource_path}
	if value is Object: return {"type": value.get_class(), "instance_id": value.get_instance_id()}
	if value is Array:
		var array: Array = []
		for item in value: array.append(_json_value(item))
		return array
	if value is Dictionary:
		var dictionary := {}
		for key in value: dictionary[str(key)] = _json_value(value[key])
		return dictionary
	return str(value)


func _vector2(value) -> Vector2:
	return Vector2(float(value[0]), float(value[1])) if value is Array and value.size() >= 2 else Vector2.ZERO


func _vector3(value) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2])) if value is Array and value.size() >= 3 else Vector3.ZERO


func _safe_png_path(path: String) -> bool:
	return path.begins_with("res://") and path.ends_with(".png") and ".." not in path


func _error(message: String) -> Dictionary:
	return {"__error__": message}
