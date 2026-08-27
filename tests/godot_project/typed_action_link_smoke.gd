extends SceneTree

const RuntimePeer = preload("res://addons/dcc_mcp_godot/runtime_peer.gd")


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	ProjectSettings.set_setting("dcc_mcp/playtest/project_id", "dcc-mcp-godot-ci")
	ProjectSettings.set_setting("dcc_mcp/playtest/session_id", "typed-action-smoke")
	ProjectSettings.set_setting("dcc_mcp/playtest/authority_id", "ci-playtest-owner")
	var peer = RuntimePeer.new()
	root.add_child(peer)
	await process_frame
	var status: Dictionary = peer._execute("get_runtime_status", {})
	var typed: Dictionary = status.get("typed_actions", {})
	if typed.get("available") == false and "manifest_path_reparse" in str(typed.get("reason", "")):
		print("TYPED_ACTION_LINK_REJECTED")
		quit(0)
	else:
		push_error("Typed action manifest reparse point was not rejected: %s" % status)
		quit(1)
