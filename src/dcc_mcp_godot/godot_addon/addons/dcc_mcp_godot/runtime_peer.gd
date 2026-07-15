extends Node

const MAX_DEPTH := 16
const MAX_RESULTS := 500
const MAX_FRAMES := 120

var _recording := false
var _recorded_events: Array[Dictionary] = []
var _last_test_report := {"status": "not_run", "assertions": []}
var _debugger_registered := false


func _ready() -> void:
	set_process(true)
	_register_debugger()


func _process(_delta: float) -> void:
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
		"get_runtime_status": return {"connected": true, "playing": true, "scene": get_tree().current_scene.scene_file_path if get_tree().current_scene else ""}
		"get_game_scene_tree": return _get_scene_tree()
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


func _get_scene_tree() -> Dictionary:
	var root := get_tree().current_scene
	if root == null: return _error("Running game has no current scene")
	return {"scene_path": root.scene_file_path, "root": _snapshot(root, 0)}


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
	var properties := {}
	var requested: Array = params.get("properties", [])
	for item in node.get_property_list():
		var name := str(item.get("name", ""))
		if (requested.is_empty() and int(item.get("usage", 0)) & PROPERTY_USAGE_STORAGE) or name in requested:
			properties[name] = _json_value(node.get(name))
	return {"node_path": str(node.get_path()), "type": node.get_class(), "properties": properties}


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
	var method_name := str(params.get("method", ""))
	if method_name.is_empty() or method_name.begins_with("_") or not node.has_method(method_name): return _error("A public node method is required")
	var arguments: Array = params.get("arguments", [])
	if arguments.size() > 8: return _error("At most 8 method arguments are allowed")
	return {"called": true, "method": method_name, "result": _json_value(node.callv(method_name, arguments))}


func _screenshot(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", "res://.dcc-mcp/game.png"))
	if not _safe_png_path(path): return _error("Screenshot path must be a .png below res://")
	var image := get_viewport().get_texture().get_image()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path.get_base_dir()))
	var save_error := image.save_png(path)
	if save_error != OK: return _error("Unable to save game screenshot: %s" % error_string(save_error))
	return {"path": path, "width": image.get_width(), "height": image.get_height()}


func _capture_frames(params: Dictionary) -> Dictionary:
	var count := clampi(int(params.get("count", 1)), 1, 10)
	var base := str(params.get("path", "res://.dcc-mcp/frames/frame"))
	if not base.begins_with("res://") or ".." in base: return _error("Frame path must remain below res://")
	var paths: Array[String] = []
	for index in range(count):
		var path := "%s_%03d.png" % [base, index]
		var result := _screenshot({"path": path})
		if result.has("__error__"): return result
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
	var text_query := str(params.get("text", "")).to_lower()
	var elements: Array[Dictionary] = []
	_collect_ui(root, text_query, elements)
	return {"elements": elements, "count": elements.size()}


func _click_button_by_text(params: Dictionary) -> Dictionary:
	var found := _find_ui_elements({"text": params.get("text", "")})
	for item in found.elements:
		var node := get_node_or_null(NodePath(item.path))
		if node is BaseButton and str(node.text) == str(params.get("text", "")) and not node.disabled:
			node.emit_signal("pressed")
			return {"clicked": true, "path": str(node.get_path()), "text": node.text}
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
	var found := _find_ui_elements({"text": params.get("text", "")})
	var result := {"passed": not found.elements.is_empty(), "text": str(params.get("text", "")), "matches": found.elements}
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


func _collect_ui(node: Node, query: String, output: Array[Dictionary]) -> void:
	if output.size() >= MAX_RESULTS: return
	if node is Control and node.is_visible_in_tree():
		var text := str(node.get("text")) if _has_property(node, "text") else ""
		if query.is_empty() or query in text.to_lower(): output.append({"path": str(node.get_path()), "type": node.get_class(), "text": text, "position": _json_value(node.global_position), "size": _json_value(node.size)})
	for child in node.get_children(): _collect_ui(child, query, output)


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
