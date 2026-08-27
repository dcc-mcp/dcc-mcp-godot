extends SceneTree

const MANIFEST_PATH := "res://.dcc-mcp/playtest-actions.v1.json"
const RuntimePeer = preload("res://addons/dcc_mcp_godot/runtime_peer.gd")
const IgnoredTarget = preload("res://typed_action_ignored_target.gd")
const DriftTarget = preload("res://typed_action_drift_target.gd")
const TypedActionTarget = preload("res://typed_action_target.gd")

var _failures: Array[String] = []
var _original_manifest := ""
var _original_drift_script := ""
var _scene: Node


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	ProjectSettings.set_setting("dcc_mcp/playtest/project_id", "dcc-mcp-godot-ci")
	ProjectSettings.set_setting("dcc_mcp/playtest/session_id", "typed-action-review")
	ProjectSettings.set_setting("dcc_mcp/playtest/authority_id", "ci-playtest-owner")
	_original_manifest = FileAccess.get_file_as_string(MANIFEST_PATH)
	_original_drift_script = FileAccess.get_file_as_string(
		"res://typed_action_drift_target.gd"
	)
	_scene = Node.new()
	_scene.name = "ReviewRoot"
	root.add_child(_scene)
	current_scene = _scene
	var ignored := IgnoredTarget.new()
	ignored.name = "Ignored"
	_scene.add_child(ignored)
	var drift := DriftTarget.new()
	drift.name = "Drift"
	_scene.add_child(drift)
	var normal := TypedActionTarget.new()
	normal.name = "Normal"
	_scene.add_child(normal)
	if not InputMap.has_action("review_action"):
		InputMap.add_action("review_action")

	await _rejected_action_does_not_consume_authority()
	await _ignored_setter_does_not_apply_or_consume_authority(ignored)
	await _script_drift_fails_closed_and_rolls_back(drift)
	await _orphaned_commit_rolls_back_without_charging_authority(normal)
	await _published_schema_is_enforced_at_runtime()

	Input.action_release("review_action")
	_write_text(MANIFEST_PATH, _original_manifest)
	_write_text("res://typed_action_drift_target.gd", _original_drift_script)
	if _failures.is_empty():
		print("REVIEWER_TYPED_ACTION_REGRESSIONS_OK")
		quit(0)
	else:
		for failure in _failures:
			push_error(failure)
		quit(1)


func _rejected_action_does_not_consume_authority() -> void:
	var missing := _property_action(
		"missing_target",
		"/root/ReviewRoot/Missing",
		"res://typed_action_ignored_target.gd",
		FileAccess.get_sha256("res://typed_action_ignored_target.gd"),
		"speed",
	)
	_write_manifest([missing, _input_manifest_action("valid_after_missing")], 1, 1)
	var peer = await _new_peer()
	var identity := _identity(peer)
	_expect_error(
		peer._execute("execute_typed_action", _request(identity, _property_request(missing, 3.5))),
		"target_missing",
	)
	var valid: Dictionary = peer._execute(
		"execute_typed_action",
		_request(identity, _input_request("valid_after_missing")),
	)
	_expect(valid.get("status") == "applied", "target_missing consumed accepted authority")
	peer.queue_free()
	await process_frame
	Input.action_release("review_action")


func _ignored_setter_does_not_apply_or_consume_authority(target: Node) -> void:
	var ignored := _property_action(
		"ignore_speed",
		str(target.get_path()),
		"res://typed_action_ignored_target.gd",
		FileAccess.get_sha256("res://typed_action_ignored_target.gd"),
		"speed",
	)
	_write_manifest([ignored, _input_manifest_action("valid_after_ignored")], 1, 1)
	var peer = await _new_peer()
	var identity := _identity(peer)
	var result: Dictionary = peer._execute(
		"execute_typed_action",
		_request(identity, _property_request(ignored, 3.5)),
	)
	_expect(result.get("status") != "applied", "ignored setter was reported as applied")
	_expect(is_equal_approx(float(target.speed), 1.0), "ignored setter changed measured value")
	var valid: Dictionary = peer._execute(
		"execute_typed_action",
		_request(identity, _input_request("valid_after_ignored")),
	)
	_expect(valid.get("status") == "applied", "ignored setter consumed accepted authority")
	peer.queue_free()
	await process_frame
	Input.action_release("review_action")


func _script_drift_fails_closed_and_rolls_back(target: Node) -> void:
	var action := _property_action(
		"drift_speed",
		str(target.get_path()),
		"res://typed_action_drift_target.gd",
		FileAccess.get_sha256("res://typed_action_drift_target.gd"),
		"speed",
	)
	_write_manifest([action], 1, 1)
	var peer = await _new_peer()
	var identity := _identity(peer)
	var result: Dictionary = peer._execute(
		"execute_typed_action",
		_request(identity, _property_request(action, 4.0)),
	)
	_expect(result.get("status") != "applied", "script drift was reported as applied")
	_expect(is_equal_approx(float(target.speed), 1.0), "script drift did not roll back property")
	peer.queue_free()
	await process_frame
	_write_text("res://typed_action_drift_target.gd", _original_drift_script)


func _orphaned_commit_rolls_back_without_charging_authority(target: Node) -> void:
	var action := _property_action(
		"orphan_speed",
		str(target.get_path()),
		"res://typed_action_target.gd",
		FileAccess.get_sha256("res://typed_action_target.gd"),
		"speed",
	)
	_write_manifest([action, _input_manifest_action("valid_after_orphan")], 1, 1)
	var peer = await _new_peer()
	var identity := _identity(peer)
	var reserved: Dictionary = peer._reserve_typed_action(
		_request(identity, _property_request(action, 3.0))
	)
	_expect(reserved.get("status") == "reserved", "host-loss case was not reserved")
	var boundary := {"reservation_id": reserved.get("reservation_id", "")}
	var committed: Dictionary = peer._commit_typed_action(boundary)
	_expect(committed.get("status") == "pending_commit", "host-loss case was not committed")
	_expect(is_equal_approx(float(target.speed), 3.0), "host-loss case did not mutate")
	peer._typed_reservation.created_msec = Time.get_ticks_msec() - 6000
	peer._process(0.0)
	_expect(is_equal_approx(float(target.speed), 1.0), "orphaned host mutation was not rolled back")
	var valid: Dictionary = peer._execute(
		"execute_typed_action",
		_request(identity, _input_request("valid_after_orphan")),
	)
	_expect(valid.get("status") == "applied", "orphaned claim consumed accepted authority")
	peer.queue_free()
	await process_frame
	Input.action_release("review_action")


func _published_schema_is_enforced_at_runtime() -> void:
	var invalid_actions: Array[Dictionary] = []
	var duplicate_pressed := _input_manifest_action("duplicate_pressed")
	duplicate_pressed.arguments.pressed = [true, true]
	invalid_actions.append(duplicate_pressed)
	var empty_pressed := _input_manifest_action("empty_pressed")
	empty_pressed.arguments.pressed = []
	invalid_actions.append(empty_pressed)
	var too_many_pressed := _input_manifest_action("too_many_pressed")
	too_many_pressed.arguments.pressed = [true, false, true]
	invalid_actions.append(too_many_pressed)
	var low_strength := _input_manifest_action("low_strength")
	low_strength.arguments.strength.minimum = -0.1
	invalid_actions.append(low_strength)
	var high_strength := _input_manifest_action("high_strength")
	high_strength.arguments.strength.maximum = 1.1
	invalid_actions.append(high_strength)
	var duplicate_enum := _property_manifest_action()
	duplicate_enum.arguments.value = {"type": "string", "enum": ["walk", "walk"]}
	invalid_actions.append(duplicate_enum)
	var empty_enum := _property_manifest_action()
	empty_enum.arguments.value = {"type": "string", "enum": []}
	invalid_actions.append(empty_enum)
	var large_enum := _property_manifest_action()
	var enum_values: Array[String] = []
	for index in range(33):
		enum_values.append("value_%d" % index)
	large_enum.arguments.value = {"type": "string", "enum": enum_values}
	invalid_actions.append(large_enum)
	var invalid_input_name := _input_manifest_action("invalid_input_name")
	invalid_input_name.target.action = "bad action"
	invalid_actions.append(invalid_input_name)
	var invalid_node_path := _property_manifest_action()
	invalid_node_path.target.node_path = "/root/ReviewRoot/Bad Path"
	invalid_actions.append(invalid_node_path)
	var invalid_script_path := _property_manifest_action()
	invalid_script_path.target.script_path = "res://bad path.gd"
	invalid_actions.append(invalid_script_path)
	var long_script_path := _property_manifest_action()
	long_script_path.target.script_path = "res://" + "x".repeat(495) + ".gd"
	invalid_actions.append(long_script_path)
	var long_node_path := _property_manifest_action()
	long_node_path.target.node_path = "/root/" + "x".repeat(506)
	invalid_actions.append(long_node_path)
	var low_number := _property_manifest_action()
	low_number.arguments.value.minimum = -1000001.0
	invalid_actions.append(low_number)
	var high_number := _property_manifest_action()
	_high_bound(high_number)
	invalid_actions.append(high_number)
	var long_enum := _property_manifest_action()
	long_enum.arguments.value = {"type": "string", "enum": ["x".repeat(129)]}
	invalid_actions.append(long_enum)

	for action in invalid_actions:
		_write_manifest([action], 1, 1)
		var peer = await _new_peer()
		var status: Dictionary = peer._execute("get_runtime_status", {})
		_expect(
			status.get("typed_actions", {}).get("available") == false,
			"runtime accepted manifest outside published schema: %s" % action,
		)
		peer.queue_free()
		await process_frame

	var invalid_manifests: Array[Dictionary] = []
	for maximum in [0, 10001]:
		var max_manifest := _manifest([_input_manifest_action("bounded_input")], maximum, 1)
		invalid_manifests.append(max_manifest)
	for rate_actions in [0, 101]:
		var rate_manifest := _manifest([_input_manifest_action("bounded_input")], 1, rate_actions)
		invalid_manifests.append(rate_manifest)
	for window_msec in [9, 60001]:
		var window_manifest := _manifest([_input_manifest_action("bounded_input")], 1, 1)
		window_manifest.authority.rate_limit.window_msec = window_msec
		invalid_manifests.append(window_manifest)
	invalid_manifests.append(_manifest([], 1, 1))
	var too_many_actions: Array[Dictionary] = []
	for index in range(65):
		too_many_actions.append(_input_manifest_action("bounded_%d" % index))
	invalid_manifests.append(_manifest(too_many_actions, 1, 1))

	for manifest in invalid_manifests:
		_write_text(MANIFEST_PATH, JSON.stringify(manifest))
		var peer = await _new_peer()
		var status: Dictionary = peer._execute("get_runtime_status", {})
		_expect(
			status.get("typed_actions", {}).get("available") == false,
			"runtime accepted manifest outside published nested bounds: %s" % manifest,
		)
		peer.queue_free()
		await process_frame


func _high_bound(action: Dictionary) -> void:
	action.arguments.value.maximum = 1000001.0


func _new_peer():
	var peer = RuntimePeer.new()
	root.add_child(peer)
	await process_frame
	return peer


func _identity(peer) -> Dictionary:
	var status: Dictionary = peer._execute("get_runtime_status", {})
	var identity: Dictionary = status.get("typed_actions", {})
	_expect(bool(identity.get("available", false)), "valid review manifest unavailable: %s" % identity)
	return identity


func _request(identity: Dictionary, action: Dictionary) -> Dictionary:
	return {
		"project_id": identity.get("project_id", ""),
		"session_id": identity.get("session_id", ""),
		"runtime_id": identity.get("runtime_id", ""),
		"authority_id": identity.get("authority_id", ""),
		"manifest_id": identity.get("manifest_id", ""),
		"manifest_digest": identity.get("manifest_digest", ""),
		"action": action,
	}


func _write_manifest(actions: Array, max_actions: int, rate_actions: int) -> void:
	_write_text(MANIFEST_PATH, JSON.stringify(_manifest(actions, max_actions, rate_actions)))


func _manifest(actions: Array, max_actions: int, rate_actions: int) -> Dictionary:
	return {
		"schema_version": 1,
		"manifest_id": "dcc-mcp-godot-review-v1",
		"project_id": "dcc-mcp-godot-ci",
		"session_id": "typed-action-review",
		"authority": {
			"id": "ci-playtest-owner",
			"max_actions": max_actions,
			"rate_limit": {"max_actions": rate_actions, "window_msec": 60000},
		},
		"actions": actions,
	}


func _input_manifest_action(id: String) -> Dictionary:
	return {
		"id": id,
		"kind": "input_action",
		"thread": "main",
		"target": {"action": "review_action"},
		"arguments": {
			"pressed": [true, false],
			"strength": {"minimum": 0.0, "maximum": 1.0},
		},
		"readback": {"kind": "input_action"},
	}


func _input_request(id: String) -> Dictionary:
	return {
		"id": id,
		"kind": "input_action",
		"target": {"action": "review_action"},
		"arguments": {"pressed": true, "strength": 1.0},
	}


func _property_action(
	id: String,
	node_path: String,
	script_path: String,
	script_sha256: String,
	property: String,
) -> Dictionary:
	var action := _property_manifest_action()
	action.id = id
	action.target.node_path = node_path
	action.target.script_path = script_path
	action.target.script_sha256 = script_sha256
	action.target.property = property
	action.readback.node_path = node_path
	action.readback.property = property
	return action


func _property_request(definition: Dictionary, value: float) -> Dictionary:
	return {
		"id": definition.id,
		"kind": "set_property",
		"target": definition.target.duplicate(true),
		"arguments": {"value": value},
	}


func _property_manifest_action() -> Dictionary:
	return {
		"id": "set_speed",
		"kind": "set_property",
		"thread": "main",
		"target": {
			"node_path": "/root/ReviewRoot/Ignored",
			"node_type": "Node",
			"script_path": "res://typed_action_ignored_target.gd",
			"script_sha256": FileAccess.get_sha256("res://typed_action_ignored_target.gd"),
			"property": "speed",
		},
		"arguments": {
			"value": {"type": "number", "minimum": 0.0, "maximum": 5.0},
		},
		"readback": {
			"kind": "property",
			"node_path": "/root/ReviewRoot/Ignored",
			"property": "speed",
		},
	}


func _write_text(path: String, content: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_failures.append("could not write review fixture: %s" % path)
		return
	file.store_string(content)
	file.close()


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_failures.append(message)


func _expect_error(result: Dictionary, code: String) -> void:
	_expect(result.has("__error__"), "expected rejection %s" % code)
	_expect(code in str(result.get("__error__", "")), "expected rejection code %s" % code)
