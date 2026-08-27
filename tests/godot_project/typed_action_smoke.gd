extends SceneTree

const MANIFEST_PATH := "res://.dcc-mcp/playtest-actions.v1.json"
const RuntimePeer = preload("res://addons/dcc_mcp_godot/runtime_peer.gd")
const TypedActionTarget = preload("res://typed_action_target.gd")

var _failures: Array[String] = []


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	ProjectSettings.set_setting("dcc_mcp/playtest/project_id", "dcc-mcp-godot-ci")
	ProjectSettings.set_setting("dcc_mcp/playtest/session_id", "typed-action-smoke")
	ProjectSettings.set_setting("dcc_mcp/playtest/authority_id", "ci-playtest-owner")
	var scene := Node.new()
	scene.name = "TypedActionRoot"
	root.add_child(scene)
	current_scene = scene
	var target := TypedActionTarget.new()
	target.name = "Player"
	scene.add_child(target)

	var original_manifest := FileAccess.get_file_as_string(MANIFEST_PATH)
	var peer = await _new_peer()
	var status: Dictionary = peer._execute("get_runtime_status", {})
	var identity: Dictionary = status.get("typed_actions", {})
	_expect(
		bool(identity.get("available", false)),
		"typed action manifest was not available: %s" % identity,
	)

	var arbitrary := _request(identity, {
		"id": "arbitrary_method",
		"kind": "call_method",
		"target": {"node_path": str(target.get_path()), "method": "arbitrary_public_method"},
		"arguments": {},
	})
	_expect_error(peer._execute("execute_typed_action", arbitrary), "unknown_action_kind")
	_expect(target.arbitrary_method_calls == 0, "typed action path called an arbitrary public method")

	var extra := _request(identity, _set_speed_action(2.0))
	extra["unexpected"] = true
	_expect_error(peer._execute("execute_typed_action", extra), "request_shape_invalid")
	_expect_error(
		peer._execute("execute_typed_action", _request(identity, _input_action("missing", "ui_accept", true))),
		"unknown_action",
	)
	_expect_error(
		peer._execute("execute_typed_action", _request(identity, _set_speed_action("fast"))),
		"argument_type_mismatch",
	)
	_expect_error(
		peer._execute("execute_typed_action", _request(identity, _set_speed_action(6.0))),
		"argument_out_of_bounds",
	)
	var wrong_project := _request(identity, _set_speed_action(2.0))
	wrong_project["project_id"] = "other-project"
	_expect_error(peer._execute("execute_typed_action", wrong_project), "project_identity_mismatch")
	var wrong_runtime := _request(identity, _set_speed_action(2.0))
	wrong_runtime["runtime_id"] = "stale-runtime"
	_expect_error(peer._execute("execute_typed_action", wrong_runtime), "runtime_identity_mismatch")
	var wrong_authority := _request(identity, _set_speed_action(2.0))
	wrong_authority["authority_id"] = "other-owner"
	_expect_error(peer._execute("execute_typed_action", wrong_authority), "authority_mismatch")
	ProjectSettings.set_setting("dcc_mcp/playtest/session_id", "replacement-session")
	_expect_error(
		peer._execute("execute_typed_action", _request(identity, _set_speed_action(2.0))),
		"session_identity_mismatch",
	)
	ProjectSettings.set_setting("dcc_mcp/playtest/session_id", "typed-action-smoke")
	_expect_error(
		peer._execute("execute_typed_action", _request(identity, _input_action("physics_only", "ui_cancel", true))),
		"physics_thread_unavailable",
	)

	var applied: Dictionary = peer._execute(
		"execute_typed_action", _request(identity, _set_speed_action(3.5))
	)
	_expect(applied.get("status") == "applied", "safe property action did not apply")
	_expect(is_equal_approx(float(target.speed), 3.5), "safe property action did not mutate target")
	_expect(
		is_equal_approx(float(applied.get("readback", {}).get("value", -1.0)), 3.5),
		"safe property action did not return measured readback",
	)
	var pressed: Dictionary = peer._execute(
		"execute_typed_action",
		_request(identity, _input_action("press_accept", "ui_accept", true)),
	)
	_expect(pressed.get("readback", {}).get("pressed") == true, "input action readback was not measured")
	_expect_error(
		peer._execute(
			"execute_typed_action",
			_request(identity, _input_action("press_accept", "ui_accept", false)),
		),
		"rate_limit_exceeded",
	)
	Input.action_release("ui_accept")

	_write_text(MANIFEST_PATH, original_manifest + "\n")
	_expect_error(
		peer._execute("execute_typed_action", _request(identity, _set_speed_action(2.0))),
		"manifest_drift",
	)
	peer.queue_free()
	await process_frame

	var invalid_manifest: Dictionary = JSON.parse_string(original_manifest)
	invalid_manifest["unexpected"] = true
	_write_text(MANIFEST_PATH, JSON.stringify(invalid_manifest))
	peer = await _new_peer()
	status = peer._execute("get_runtime_status", {})
	_expect(status.get("typed_actions", {}).get("available") == false, "extra manifest field was accepted")
	_expect(
		"manifest_shape_invalid" in str(status.get("typed_actions", {}).get("reason", "")),
		"extra manifest field did not return a stable rejection code",
	)
	peer.queue_free()
	await process_frame

	var budget_manifest: Dictionary = JSON.parse_string(original_manifest)
	budget_manifest.authority.max_actions = 1
	budget_manifest.authority.rate_limit.max_actions = 10
	_write_text(MANIFEST_PATH, JSON.stringify(budget_manifest))
	peer = await _new_peer()
	status = peer._execute("get_runtime_status", {})
	identity = status.get("typed_actions", {})
	peer._execute("execute_typed_action", _request(identity, _set_speed_action(2.0)))
	_expect_error(
		peer._execute("execute_typed_action", _request(identity, _set_speed_action(2.5))),
		"action_budget_exhausted",
	)

	_write_text(MANIFEST_PATH, original_manifest)
	if _failures.is_empty():
		print("TYPED_ACTION_SMOKE_OK")
		quit(0)
	else:
		for failure in _failures:
			push_error(failure)
		quit(1)


func _new_peer():
	var peer = RuntimePeer.new()
	root.add_child(peer)
	await process_frame
	return peer


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


func _set_speed_action(value) -> Dictionary:
	return {
		"id": "set_speed",
		"kind": "set_property",
		"target": {
			"node_path": "/root/TypedActionRoot/Player",
			"node_type": "Node",
			"script_path": "res://typed_action_target.gd",
			"script_sha256": FileAccess.get_sha256("res://typed_action_target.gd"),
			"property": "speed",
		},
		"arguments": {"value": value},
	}


func _input_action(id: String, action: String, pressed: bool) -> Dictionary:
	return {
		"id": id,
		"kind": "input_action",
		"target": {"action": action},
		"arguments": {"pressed": pressed, "strength": 1.0},
	}


func _write_text(path: String, text: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_failures.append("could not write test manifest")
		return
	file.store_string(text)
	file.close()


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_failures.append(message)


func _expect_error(result: Dictionary, code: String) -> void:
	_expect(result.has("__error__"), "expected rejection %s" % code)
	_expect(code in str(result.get("__error__", "")), "expected rejection code %s" % code)
