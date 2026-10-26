@tool
extends RefCounted

const UITexture = preload("res://addons/dcc_mcp_godot/ui_texture.gd")

const MAX_TEXT_BYTES := 1000000
const MAX_RESULTS := 500
const DEFAULT_MAIN_THREAD_BUDGET_MS := 40
const MAX_MAIN_THREAD_BUDGET_MS := 50
const PREVIEW_DEFAULT_WIDTH := 1280
const PREVIEW_DEFAULT_HEIGHT := 720
const PREVIEW_MIN_DIMENSION := 16
const PREVIEW_MAX_DIMENSION := 4096
const PREVIEW_DEFAULT_FRAMES := 3
const PREVIEW_MAX_FRAMES := 8
const PREVIEW_BOUNDS_MAX_NODES := 2000
const RUNTIME_ACTIONS := [
	"get_game_screenshot", "simulate_key", "simulate_mouse_click", "simulate_mouse_move",
	"simulate_action", "simulate_sequence", "get_runtime_status", "get_game_scene_tree",
	"get_game_node_properties", "set_game_node_property", "execute_game_script",
	"reserve_typed_action", "commit_typed_action", "finalize_typed_action",
	"rollback_typed_action", "capture_frames",
	"monitor_properties", "start_recording", "stop_recording", "replay_recording",
	"find_nodes_by_script", "get_autoload", "batch_get_properties", "find_ui_elements",
	"click_button_by_text", "wait_for_node", "find_nearby_nodes", "navigate_to", "move_to",
	"run_test_scenario", "assert_node_state", "assert_screen_text", "run_stress_test",
	"get_test_report", "get_performance_monitors",
]

var _plugin: EditorPlugin
var _messages: Array[Dictionary] = []
var _pending_preview: Dictionary = {}
var _pending_resource_preview: Dictionary = {}
var _resource_preview_generation := 0

const RESOURCE_PREVIEW_TIMEOUT_MS := 20000
const RESOURCE_PREVIEW_MAX_DIMENSION := 1024
const RESOURCE_PREVIEW_MAX_IMAGE_BYTES := 4194304


func _init(plugin: EditorPlugin) -> void:
	_plugin = plugin


func execute(action: String, params: Dictionary) -> Dictionary:
	if action in RUNTIME_ACTIONS:
		return {"__runtime_action__": action, "params": params}
	match action:
		"get_project_info": return _get_project_info()
		"get_filesystem_tree": return _get_filesystem_tree(params)
		"search_files": return _search_files(params)
		"get_project_settings": return _get_project_settings(params)
		"set_project_setting": return _set_project_setting(params)
		"uid_to_project_path": return _uid_to_path(params)
		"project_path_to_uid": return _path_to_uid(params)
		"get_scene_tree": return _get_scene_tree(params)
		"get_scene_file_content": return _read_text(params, ["tscn"])
		"create_scene": return _create_scene(params)
		"open_scene": return _open_scene(params)
		"delete_scene": return _delete_scene(params)
		"add_scene_instance": return _add_scene_instance(params)
		"play_scene": return _play_scene(params)
		"stop_scene": return _stop_scene()
		"save_scene": return _save_scene(params)
		"add_node": return _add_node(params)
		"delete_node": return _delete_node(params)
		"duplicate_node": return _duplicate_node(params)
		"move_node": return _move_node(params)
		"update_property": return _update_property(params)
		"get_node_properties": return _get_node_properties(params)
		"add_resource": return _add_resource(params)
		"assign_ui_texture": return UITexture.assign_texture(_plugin, params)
		"set_anchor_preset": return _set_anchor_preset(params)
		"rename_node": return _rename_node(params)
		"connect_signal": return _connect_signal(params)
		"disconnect_signal": return _disconnect_signal(params)
		"get_node_groups": return _get_node_groups(params)
		"set_node_groups": return _set_node_groups(params)
		"find_nodes_in_group": return _find_nodes_in_group(params)
		"list_scripts": return _list_scripts()
		"read_script": return _read_text(params, ["gd"])
		"create_script": return _create_script(params)
		"edit_script": return _edit_text(params, ["gd"])
		"attach_script": return _attach_script(params)
		"get_open_scripts": return _get_open_scripts()
		"validate_script": return _validate_script(params)
		"search_in_files": return _search_in_files(params)
		"get_editor_errors", "get_output_log": return {"messages": _messages.duplicate(true)}
		"get_editor_screenshot": return _get_editor_screenshot(params)
		"render_scene_preview": return _render_scene_preview(params)
		"execute_editor_script": return _execute_editor_script(params)
		"clear_output": _messages.clear(); return {"cleared": true}
		"get_signals": return _get_signals(params)
		"reload_plugin": return _reload_plugin()
		"reload_project": return _reload_project()
		"get_input_actions": return _get_input_actions(params)
		"set_input_action": return _set_input_action(params)
		"find_nodes_by_type": return _find_nodes_by_type(params)
		"find_signal_connections": return _find_signal_connections()
		"batch_set_property": return _batch_set_property(params)
		"find_node_references", "find_script_references": return _search_in_files(params)
		"get_scene_dependencies": return _get_scene_dependencies(params)
		"cross_scene_set_property": return _cross_scene_set_property(params)
		"detect_circular_dependencies": return _detect_circular_dependencies()
		"analyze_scene_complexity": return _analyze_scene_complexity()
		"analyze_signal_flow": return _find_signal_connections()
		"find_unused_resources": return _find_unused_resources()
		"get_project_statistics": return _get_project_statistics()
		"get_editor_performance": return _get_editor_performance()
		"list_export_presets": return _list_export_presets()
		"export_project": return _export_project(params)
		"get_export_info": return _get_export_info()
		"get_export_job_context": return _get_export_job_context()
		"create_fire_vfx": return _create_fire_vfx(params)
		"create_dynamic_fire_vfx": return _create_vfx_node(params, false)
		"create_spell_projectile": return _create_vfx_node(params, true)
		"create_spellcasting_demo": return _create_spellcasting_demo(params)
		"create_combat_vfx": return _create_combat_vfx(params)
		"install_combat_vfx_library": return _install_combat_vfx_library(params)
		"create_shader": return _create_shader(params)
		"read_shader": return _read_text(params, ["gdshader"])
		"edit_shader": return _edit_text(params, ["gdshader"])
		"assign_shader_material": return _assign_shader_material(params)
		"set_shader_param": return _set_shader_param(params)
		"get_shader_params": return _get_shader_params(params)
		"read_resource": return _read_resource(params)
		"edit_resource": return _edit_resource(params)
		"create_resource": return _create_resource(params)
		"get_resource_preview": return _get_resource_preview(params)
		"add_autoload": return _add_autoload(params)
		"remove_autoload": return _remove_autoload(params)
		_:
			return _execute_authoring(action, params)


func _get_project_info() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	var autoloads: Array[Dictionary] = []
	for property in ProjectSettings.get_property_list():
		var key := str(property.get("name", ""))
		if key.begins_with("autoload/"):
			autoloads.append({"name": key.trim_prefix("autoload/"), "path": ProjectSettings.get_setting(key)})
	return {
		"name": ProjectSettings.get_setting("application/config/name", "Unnamed Project"),
		"project_path": ProjectSettings.globalize_path("res://"),
		"engine_version": Engine.get_version_info().get("string", "unknown"),
		"current_scene": root.scene_file_path if root else "",
		"main_scene": ProjectSettings.get_setting("application/run/main_scene", ""),
		"viewport": {
			"width": ProjectSettings.get_setting("display/window/size/viewport_width", 1152),
			"height": ProjectSettings.get_setting("display/window/size/viewport_height", 648),
		},
		"autoloads": autoloads,
	}


func _get_filesystem_tree(params: Dictionary) -> Dictionary:
	var extensions := _string_array(params.get("extensions", []))
	var files := _collect_files("res://", extensions)
	return {"root": "res://", "files": files, "count": files.size(), "truncated": files.size() >= MAX_RESULTS}


func _search_files(params: Dictionary) -> Dictionary:
	var query := str(params.get("query", "")).to_lower()
	var extension := str(params.get("extension", "")).trim_prefix(".").to_lower()
	var matches: Array[String] = []
	for path in _collect_files("res://", []):
		if (query.is_empty() or query in path.to_lower()) and (extension.is_empty() or path.get_extension().to_lower() == extension):
			matches.append(path)
	return {"query": query, "files": matches, "count": matches.size()}


func _get_project_settings(params: Dictionary) -> Dictionary:
	var prefix := str(params.get("prefix", params.get("key", "")))
	var settings := {}
	for property in ProjectSettings.get_property_list():
		var key := str(property.get("name", ""))
		if prefix.is_empty() or key == prefix or key.begins_with(prefix):
			settings[key] = _json_value(ProjectSettings.get_setting(key))
			if settings.size() >= MAX_RESULTS:
				break
	return {"settings": settings, "count": settings.size()}


func _set_project_setting(params: Dictionary) -> Dictionary:
	var key := str(params.get("key", ""))
	if key.is_empty() or key.begins_with("autoload/"):
		return _error("A non-autoload project setting key is required")
	ProjectSettings.set_setting(key, params.get("value"))
	var save_error := ProjectSettings.save()
	if save_error != OK:
		return _error("Unable to save project settings: %s" % error_string(save_error))
	return {"updated": true, "key": key, "value": _json_value(ProjectSettings.get_setting(key))}


func _uid_to_path(params: Dictionary) -> Dictionary:
	var raw := str(params.get("uid", ""))
	var uid := ResourceUID.text_to_id(raw) if raw.begins_with("uid://") else int(raw)
	if uid < 0 or not ResourceUID.has_id(uid):
		return _error("Unknown resource UID")
	return {"uid": ResourceUID.id_to_text(uid), "path": ResourceUID.get_id_path(uid)}


func _path_to_uid(params: Dictionary) -> Dictionary:
	var path_error := _validated_path(params.get("path", ""), [])
	if path_error.has("error"):
		return _error(path_error.error)
	var uid := ResourceLoader.get_resource_uid(path_error.path)
	if uid < 0:
		return _error("Resource path has no UID: %s" % path_error.path)
	return {"path": path_error.path, "uid": ResourceUID.id_to_text(uid), "id": uid}


func _get_scene_tree(params: Dictionary) -> Dictionary:
	var unsupported := _unsupported_params(params, ["scene_path", "path"])
	if not unsupported.is_empty():
		return _error(
			"get_scene_tree does not support: %s; only scene_path (or path) is read"
			% ", ".join(unsupported)
		)
	# scene_path and path are aliases; two different values are a caller bug,
	# and silently preferring one reproduces the silent-wrong-answer defect.
	var explicit_path := str(params.get("scene_path", ""))
	var alias_path := str(params.get("path", ""))
	# An explicitly empty alias is a caller mistake, not "no scene requested":
	# answering with the edited scene would hide it.
	if (params.has("scene_path") and explicit_path.is_empty()) or (
		params.has("path") and alias_path.is_empty()
	):
		return _error("scene_path (or path) must be a non-empty res:// path when supplied")
	if not explicit_path.is_empty() and not alias_path.is_empty() and explicit_path != alias_path:
		return _error(
			"Conflicting scene paths: scene_path=%s but path=%s" % [explicit_path, alias_path]
		)
	var requested := explicit_path if not explicit_path.is_empty() else alias_path
	if requested.is_empty():
		return _edited_scene_tree()
	var checked := _existing_path(requested, ["tscn", "scn"])
	if checked.has("error"): return _error(checked.error)
	var edited := EditorInterface.get_edited_scene_root()
	if edited != null and edited.scene_file_path == checked.path:
		return _edited_scene_tree()
	return _packed_scene_tree(checked.path)


func _edited_scene_tree() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _error("No scene is open")
	return {"scene_path": root.scene_file_path, "source": "edited", "root": _node_snapshot(root, 0, 16)}


# Read a scene from disk without opening it: the PackedScene is instantiated,
# snapshotted, and freed, so the edited scene and editor state are untouched.
func _packed_scene_tree(path: String) -> Dictionary:
	# Instantiating runs @tool script constructors, but the instance stays out
	# of the scene tree, so _ready() never runs and @onready values remain at
	# their init value. It is never added to the editor tree and is freed after
	# the snapshot, so the edited scene keeps its identity and node addresses.
	# Bypass the resource cache so a caller polling a scene another process or
	# an external edit has just changed reads the file, not a stale instance.
	var packed = ResourceLoader.load(
		path, "", ResourceLoader.CACHE_MODE_IGNORE_DEEP
	)
	if not packed is PackedScene:
		return _error("Scene path is not a PackedScene resource: %s" % path)
	var instance: Node = packed.instantiate()
	if instance == null:
		return _error("Unable to instantiate scene for reading: %s" % path)
	var snapshot := _node_snapshot(instance, 0, 16, instance.name)
	instance.free()
	return {"scene_path": path, "source": "file", "root": snapshot}


func _create_scene(params: Dictionary) -> Dictionary:
	var checked := _validated_path(params.get("path", ""), ["tscn"])
	if checked.has("error"):
		return _error(checked.error)
	if FileAccess.file_exists(checked.path) and not bool(params.get("overwrite", false)):
		return _error("Scene already exists; set overwrite=true to replace it")
	var type_name := str(params.get("root_type", "Node2D"))
	var root = ClassDB.instantiate(type_name)
	if not root is Node:
		if root != null: root.free()
		return _error("Root type is not a Node: %s" % type_name)
	root.name = str(params.get("root_name", "Root"))
	var packed := PackedScene.new()
	var pack_error := packed.pack(root)
	root.free()
	if pack_error != OK:
		return _error("Unable to pack scene: %s" % error_string(pack_error))
	var mkdir_error := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(checked.path.get_base_dir()))
	if mkdir_error != OK:
		return _error("Unable to create scene directory: %s" % error_string(mkdir_error))
	var save_error := ResourceSaver.save(packed, checked.path)
	if save_error != OK:
		return _error("Unable to save scene: %s" % error_string(save_error))
	if bool(params.get("open", true)):
		EditorInterface.open_scene_from_path(checked.path)
	return {"created": true, "path": checked.path, "root_type": type_name}


func _open_scene(params: Dictionary) -> Dictionary:
	var checked := _existing_path(params.get("path", ""), ["tscn"])
	if checked.has("error"): return _error(checked.error)
	EditorInterface.open_scene_from_path(checked.path)
	return {"opened": true, "path": checked.path}


func _delete_scene(params: Dictionary) -> Dictionary:
	var checked := _existing_path(params.get("path", ""), ["tscn"])
	if checked.has("error"): return _error(checked.error)
	var root := EditorInterface.get_edited_scene_root()
	if root != null and root.scene_file_path == checked.path:
		return _error("Close the scene before deleting it")
	var remove_error := DirAccess.remove_absolute(ProjectSettings.globalize_path(checked.path))
	if remove_error != OK: return _error("Unable to delete scene: %s" % error_string(remove_error))
	EditorInterface.get_resource_filesystem().scan()
	return {"deleted": true, "path": checked.path}


func _add_scene_instance(params: Dictionary) -> Dictionary:
	# Godot imports GLTF assets as PackedScene resources. Keep the path scoped
	# to res:// while allowing the standard cross-DCC scene interchange forms.
	var checked := _existing_path(params.get("scene_path", ""), ["tscn", "scn", "glb", "gltf"])
	if checked.has("error"): return _error(checked.error)
	var packed = load(checked.path)
	if not packed is PackedScene: return _error("Resource is not a PackedScene")
	var instance: Node = packed.instantiate()
	instance.name = str(params.get("name", instance.name))
	return _add_existing_node(instance, str(params.get("parent_path", ".")))


func _play_scene(params: Dictionary) -> Dictionary:
	var mode := str(params.get("mode", "current"))
	if mode == "main": EditorInterface.play_main_scene()
	elif mode == "current": EditorInterface.play_current_scene()
	elif mode == "custom":
		var checked := _existing_path(params.get("path", ""), ["tscn", "scn"])
		if checked.has("error"): return _error(checked.error)
		EditorInterface.play_custom_scene(checked.path)
	else: return _error("mode must be main, current, or custom")
	return {"playing": true, "mode": mode}


func _stop_scene() -> Dictionary:
	EditorInterface.stop_playing_scene()
	return {"stopped": true}


func _save_scene(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null: return _error("No scene is open")
	var path := str(params.get("path", ""))
	if not path.is_empty():
		var checked := _validated_path(path, ["tscn"])
		if checked.has("error"): return _error(checked.error)
		EditorInterface.save_scene_as(checked.path, false)
		return {"saved": true, "scene_path": checked.path}
	if DisplayServer.get_name() == "headless" and not root.scene_file_path.is_empty():
		EditorInterface.save_scene_as(root.scene_file_path, false)
		return {"saved": true, "scene_path": root.scene_file_path}
	var save_error := EditorInterface.save_scene()
	if save_error != OK: return _error("Unable to save scene: %s" % error_string(save_error))
	return {"saved": true, "scene_path": root.scene_file_path}


func _add_node(params: Dictionary) -> Dictionary:
	var type_name := str(params.get("type", "Node2D"))
	var node = ClassDB.instantiate(type_name)
	if not node is Node:
		if node != null: node.free()
		return _error("Type is not a Godot Node: %s" % type_name)
	node.name = str(params.get("name", type_name))
	for property_name in (params.get("properties", {}) as Dictionary):
		if not _has_property(node, str(property_name)):
			node.free()
			return _error("Property not found on %s: %s" % [type_name, property_name])
		node.set(str(property_name), _coerce_value(node.get(str(property_name)), params.properties[property_name]))
	return _add_existing_node(node, str(params.get("parent_path", ".")))


func _add_existing_node(node: Node, parent_path: String, own_children: bool = false) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		node.free()
		return _error("Open or create a scene before adding nodes")
	var parent := _scene_node(parent_path)
	if parent == null:
		node.free()
		return _error("Parent node not found: %s" % parent_path)
	var undo := _plugin.get_undo_redo()
	undo.create_action("DCC-MCP: Add %s" % node.name)
	undo.add_do_method(parent, "add_child", node)
	undo.add_do_property(node, "owner", root)
	if own_children:
		for child in node.find_children("*", "", true, false):
			undo.add_do_property(child, "owner", root)
	undo.add_undo_method(parent, "remove_child", node)
	undo.add_do_reference(node)
	undo.commit_action()
	return {"created": true, "path": str(node.get_path()), "name": node.name, "type": node.get_class()}


func _delete_node(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", "")))
	var root := EditorInterface.get_edited_scene_root()
	if node == null or node == root: return _error("A non-root scene node is required")
	var parent := node.get_parent()
	var index := node.get_index()
	var undo := _plugin.get_undo_redo()
	undo.create_action("DCC-MCP: Delete %s" % node.name)
	undo.add_do_method(parent, "remove_child", node)
	undo.add_undo_method(parent, "add_child", node)
	undo.add_undo_method(parent, "move_child", node, index)
	undo.add_undo_property(node, "owner", root)
	undo.add_undo_reference(node)
	undo.commit_action()
	return {"deleted": true, "node_path": str(params.get("node_path", ""))}


func _duplicate_node(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", "")))
	if node == null: return _error("Node not found")
	var duplicate := node.duplicate()
	duplicate.name = str(params.get("name", "%sCopy" % node.name))
	return _add_existing_node(duplicate, str(params.get("parent_path", str(node.get_parent().get_path()))))


func _move_node(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", "")))
	var parent := _scene_node(str(params.get("parent_path", "")))
	if node == null or parent == null or node == EditorInterface.get_edited_scene_root(): return _error("Valid non-root node and parent are required")
	if node == parent or node.is_ancestor_of(parent): return _error("Cannot create a scene-tree cycle")
	var old_parent := node.get_parent()
	var undo := _plugin.get_undo_redo()
	undo.create_action("DCC-MCP: Move %s" % node.name)
	undo.add_do_method(node, "reparent", parent, bool(params.get("keep_global_transform", true)))
	undo.add_undo_method(node, "reparent", old_parent, bool(params.get("keep_global_transform", true)))
	undo.commit_action()
	return {"moved": true, "path": str(node.get_path())}


func _update_property(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null: return _error("Node not found")
	var property_name := str(params.get("property", ""))
	if not _has_property(node, property_name): return _error("Property not found: %s" % property_name)
	var previous = node.get(property_name)
	var value = _coerce_value(previous, params.get("value"))
	var undo := _plugin.get_undo_redo()
	undo.create_action("DCC-MCP: Set %s" % property_name)
	undo.add_do_property(node, property_name, value)
	undo.add_undo_property(node, property_name, previous)
	undo.commit_action()
	return {"updated": true, "node_path": str(node.get_path()), "property": property_name, "value": _json_value(value)}


func _get_node_properties(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null: return _error("Node not found")
	var properties := {}
	for info in node.get_property_list():
		if int(info.get("usage", 0)) & PROPERTY_USAGE_STORAGE:
			properties[str(info.name)] = _json_value(node.get(str(info.name)))
	return {"path": str(node.get_path()), "type": node.get_class(), "properties": properties}


func _add_resource(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null: return _error("Node not found")
	var property_name := str(params.get("property", ""))
	if not _has_property(node, property_name): return _error("Property not found")
	var resource = ClassDB.instantiate(str(params.get("resource_type", "Resource")))
	if not resource is Resource:
		if resource != null: resource.free()
		return _error("Type is not a Resource")
	for key in (params.get("properties", {}) as Dictionary):
		if _has_property(resource, str(key)): resource.set(str(key), _coerce_value(resource.get(str(key)), params.properties[key]))
	node.set(property_name, resource)
	return {"assigned": true, "node_path": str(node.get_path()), "property": property_name, "resource_type": resource.get_class()}


func _set_anchor_preset(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if not node is Control: return _error("Node must be a Control")
	node.set_anchors_preset(int(params.get("preset", Control.PRESET_FULL_RECT)), bool(params.get("keep_offsets", false)))
	return {"updated": true, "node_path": str(node.get_path()), "preset": int(params.get("preset", Control.PRESET_FULL_RECT))}


func _rename_node(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", "")))
	if node == null: return _error("Node not found")
	var new_name := str(params.get("name", ""))
	if new_name.is_empty() or "/" in new_name: return _error("A valid node name is required")
	var previous := node.name
	var undo := _plugin.get_undo_redo()
	undo.create_action("DCC-MCP: Rename %s" % previous)
	undo.add_do_property(node, "name", new_name)
	undo.add_undo_property(node, "name", previous)
	undo.commit_action()
	return {"renamed": true, "name": node.name, "path": str(node.get_path())}


func _connect_signal(params: Dictionary) -> Dictionary:
	var source := _scene_node(str(params.get("source_path", "")))
	var target := _scene_node(str(params.get("target_path", "")))
	var signal_name := str(params.get("signal", ""))
	var method_name := str(params.get("__method__", params.get("method", "")))
	if source == null or target == null or not source.has_signal(signal_name) or not target.has_method(method_name): return _error("Valid source signal and target method are required")
	var callable := Callable(target, method_name)
	if source.is_connected(signal_name, callable): return {"connected": true, "already_connected": true}
	var connect_error := source.connect(signal_name, callable, int(params.get("flags", 0)))
	if connect_error != OK: return _error("Unable to connect signal: %s" % error_string(connect_error))
	return {"connected": true, "signal": signal_name, "target": str(target.get_path()), "method": method_name}


func _disconnect_signal(params: Dictionary) -> Dictionary:
	var source := _scene_node(str(params.get("source_path", "")))
	var target := _scene_node(str(params.get("target_path", "")))
	var signal_name := str(params.get("signal", ""))
	var callable := Callable(target, str(params.get("__method__", params.get("method", "")))) if target else Callable()
	if source == null or not callable.is_valid() or not source.is_connected(signal_name, callable): return _error("Signal connection not found")
	source.disconnect(signal_name, callable)
	return {"disconnected": true, "signal": signal_name}


func _get_node_groups(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null: return _error("Node not found")
	return {"node_path": str(node.get_path()), "groups": Array(node.get_groups()).map(func(value): return str(value))}


func _set_node_groups(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null: return _error("Node not found")
	var groups := _string_array(params.get("groups", []))
	for existing in node.get_groups():
		if str(existing) not in groups: node.remove_from_group(existing)
	for group in groups:
		if not node.is_in_group(group): node.add_to_group(group, true)
	return {"updated": true, "groups": groups}


func _find_nodes_in_group(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null: return _error("No scene is open")
	var group := str(params.get("group", ""))
	var paths: Array[String] = []
	_collect_matching_nodes(root, func(node): return node.is_in_group(group), paths)
	return {"group": group, "nodes": paths}


func _list_scripts() -> Dictionary:
	var scripts := _collect_files("res://", ["gd"])
	var global_classes: Array[Dictionary] = []
	for item in ProjectSettings.get_global_class_list():
		global_classes.append({"class": item.get("class", ""), "base": item.get("base", ""), "path": item.get("path", "")})
	return {"scripts": scripts, "global_classes": global_classes}


func _create_script(params: Dictionary) -> Dictionary:
	var checked := _validated_path(params.get("path", ""), ["gd"])
	if checked.has("error"): return _error(checked.error)
	if FileAccess.file_exists(checked.path) and not bool(params.get("overwrite", false)): return _error("Script exists; set overwrite=true")
	var base := str(params.get("base_type", "Node"))
	var source := str(params.get("source", "extends %s\n" % base))
	return _write_text(checked.path, source)


func _attach_script(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	var checked := _existing_path(params.get("script_path", ""), ["gd"])
	if node == null: return _error("Node not found")
	if checked.has("error"): return _error(checked.error)
	var script = load(checked.path)
	if not script is Script: return _error("Resource is not a Script")
	node.set_script(script)
	return {"attached": true, "node_path": str(node.get_path()), "script_path": checked.path}


func _get_open_scripts() -> Dictionary:
	var scripts: Array[String] = []
	for script in EditorInterface.get_script_editor().get_open_scripts(): scripts.append(script.resource_path)
	return {"scripts": scripts}


func _validate_script(params: Dictionary) -> Dictionary:
	var unsupported := _unsupported_params(params, ["path", "script_path", "source"])
	if not unsupported.is_empty():
		return _error(
			"validate_script does not support: %s; only path (or script_path) and source are read"
			% ", ".join(unsupported)
		)
	# path and script_path are aliases. Reading path and never reading
	# script_path is the original defect: a caller naming one script was
	# answered about an empty path, and empty GDScript reloads as OK, so the
	# caller got valid: true for no script at all.
	var explicit_path := str(params.get("path", ""))
	var alias_path := str(params.get("script_path", ""))
	# An explicitly empty alias is a caller mistake, not "validate nothing":
	# falling through reloads empty source and answers valid: true.
	if (params.has("path") and explicit_path.is_empty()) or (
		params.has("script_path") and alias_path.is_empty()
	):
		return _error("path (or script_path) must be a non-empty res:// path when supplied")
	if not explicit_path.is_empty() and not alias_path.is_empty() and explicit_path != alias_path:
		return _error(
			"Conflicting script paths: path=%s but script_path=%s" % [explicit_path, alias_path]
		)
	var path := explicit_path if not explicit_path.is_empty() else alias_path
	var source := str(params.get("source", ""))
	# Nothing to compile is an error, never a successful empty check. Whitespace
	# is not source either: reload() answers OK for "   " and "\n" exactly as it
	# does for "", so an untrimmed guard reported valid: true for a blank source.
	# The two cases are distinguished by whether the caller supplied a source at
	# all, not by whether the path is empty: an absent source means "read the
	# file at path", while an explicit blank source is rejected outright so it
	# can never be reinterpreted as "no source" and read back from disk.
	if params.has("source") and source.strip_edges().is_empty():
		return _error("validate_script requires a non-empty source, or path (or script_path)")
	if not params.has("source") and path.is_empty():
		return _error("validate_script requires a non-empty source, or path (or script_path)")
	if source.is_empty():
		var read := _read_text({"path": path}, ["gd"])
		if read.has("__error__"): return read
		source = read.content
	var script := GDScript.new()
	script.source_code = source
	var reload_error := script.reload()
	return {"valid": reload_error == OK, "error": error_string(reload_error), "path": path}


func _search_in_files(params: Dictionary) -> Dictionary:
	var query := str(params.get("query", params.get("pattern", params.get("reference", ""))))
	if query.is_empty(): return _error("query is required")
	var extensions := _string_array(params.get("extensions", ["gd", "tscn", "tres", "gdshader", "cfg", "json"]))
	var matches: Array[Dictionary] = []
	for path in _collect_files("res://", extensions):
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null or file.get_length() > MAX_TEXT_BYTES: continue
		var lines := file.get_as_text().split("\n")
		for index in range(lines.size()):
			if query.to_lower() in str(lines[index]).to_lower():
				matches.append({"path": path, "line": index + 1, "text": str(lines[index]).strip_edges().left(300)})
				if matches.size() >= MAX_RESULTS: return {"matches": matches, "truncated": true}
	return {"query": query, "matches": matches, "count": matches.size()}


func _get_editor_screenshot(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", "res://.dcc-mcp/editor.png"))
	var checked := _validated_path(path, ["png"])
	if checked.has("error"): return _error(checked.error)
	var budget_ms := _main_thread_budget_ms(params)
	var started_usec := Time.get_ticks_usec()
	var mkdir_error := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(checked.path.get_base_dir()))
	if mkdir_error != OK:
		return _error("Unable to create editor screenshot directory: %s" % error_string(mkdir_error))
	var viewport: SubViewport = EditorInterface.get_editor_viewport_3d(int(params.get("viewport", 0))) if str(params.get("mode", "3d")) == "3d" else EditorInterface.get_editor_viewport_2d()
	if viewport == null: return _error("Editor viewport is unavailable")
	var image := viewport.get_texture().get_image()
	if image == null: return _error("Editor viewport image is unavailable")
	if image.get_format() != Image.FORMAT_RGBA8: image.convert(Image.FORMAT_RGBA8)
	var pixels := image.get_data()
	var staging_path := "%s.dcc-mcp-%d.raw" % [checked.path, Time.get_ticks_usec()]
	var staging_file := FileAccess.open(staging_path, FileAccess.WRITE)
	if staging_file == null: return _error("Unable to stage editor screenshot pixels")
	staging_file.store_buffer(pixels)
	var write_error := staging_file.get_error()
	staging_file.close()
	if write_error != OK:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(staging_path))
		return _error("Unable to stage editor screenshot pixels: %s" % error_string(write_error))
	var elapsed_ms := int((Time.get_ticks_usec() - started_usec) / 1000)
	return {
		"path": checked.path,
		"width": image.get_width(),
		"height": image.get_height(),
		"budget_ms": budget_ms,
		"elapsed_ms": elapsed_ms,
		"budget_exceeded": elapsed_ms >= budget_ms,
		"__raw_snapshot__": {
			"path": ProjectSettings.globalize_path(staging_path),
			"output_path": ProjectSettings.globalize_path(checked.path),
			"format": "rgba8",
			"byte_length": pixels.size(),
		},
	}


func _execute_editor_script(params: Dictionary) -> Dictionary:
	var checked := _existing_path(params.get("path", ""), ["gd"])
	if checked.has("error"): return _error(checked.error)
	var script = load(checked.path)
	if not script is Script or not script.is_tool(): return _error("Editor script must be an @tool GDScript")
	var instance = script.new()
	var method_name := str(params.get("__method__", params.get("method", "run")))
	if not instance.has_method(method_name): return _error("Editor script method not found: %s" % method_name)
	var budget_ms := clampi(int(params.get("budget_ms", 50)), 1, 50)
	var chunked := bool(params.get("chunked", false))
	var started_ms := Time.get_ticks_msec()
	var result = instance.call(method_name, params.get("arguments", {}))
	var elapsed_ms := int(Time.get_ticks_msec() - started_ms)
	var response := {
		"executed": true,
		"result": _json_value(result),
		"elapsed_ms": elapsed_ms,
		"budget_ms": budget_ms,
		"budget_exceeded": elapsed_ms > budget_ms,
		"chunked": chunked,
	}
	if chunked:
		if not result is Dictionary or not result.has("done") or not result.done is bool:
			return _error("Chunked editor scripts must return {done: bool, next_cursor?: value}")
		response["chunk"] = {
			"done": result.done,
			"next_cursor": _json_value(result.get("next_cursor")),
		}
		if not result.done:
			response["next_step"] = {
				"tool": "execute_editor_script",
				"arguments": {
					"path": checked.path,
					"method": method_name,
					"arguments": {"cursor": _json_value(result.get("next_cursor"))},
					"budget_ms": budget_ms,
					"chunked": true,
				},
			}
	return response


func _render_scene_preview(params: Dictionary) -> Dictionary:
	# A scene preview needs a real display driver. Under --headless Godot drops to
	# rendering/dummy, where an offscreen SubViewport never yields readable pixels,
	# so this refuses instead of returning a blank PNG that looks like a success.
	var budget_ms := _main_thread_budget_ms(params)
	var started_usec := Time.get_ticks_usec()
	var display_driver := DisplayServer.get_name()
	var rendering_method := RenderingServer.get_current_rendering_method()
	if display_driver == "headless":
		return _error("Scene previews require a windowed Godot host: this host runs the '%s' display driver, which degrades rendering to dummy and cannot read back pixels. Start the editor in windowed mode with the main window hidden (DCC_MCP_GODOT_HIDE_WINDOW=1, or a private desktop on Windows) instead of --headless." % display_driver)
	if not _pending_preview.is_empty():
		return _error("A scene preview is already rendering on this host; wait for it to finish")
	var requested_method := str(params.get("rendering_method", "")).strip_edges()
	if not requested_method.is_empty() and requested_method != rendering_method:
		return _error("Requested rendering_method '%s' is not active on this host (active: '%s'). Restart the host with the matching --rendering-driver; scene previews never silently fall back to another backend." % [requested_method, rendering_method])
	var width := clampi(int(params.get("width", PREVIEW_DEFAULT_WIDTH)), PREVIEW_MIN_DIMENSION, PREVIEW_MAX_DIMENSION)
	var height := clampi(int(params.get("height", PREVIEW_DEFAULT_HEIGHT)), PREVIEW_MIN_DIMENSION, PREVIEW_MAX_DIMENSION)
	var frame_count := clampi(int(params.get("frame_count", PREVIEW_DEFAULT_FRAMES)), 1, PREVIEW_MAX_FRAMES)
	var scene_path := str(params.get("scene_path", "")).strip_edges()
	if scene_path.is_empty():
		var edited_root := EditorInterface.get_edited_scene_root()
		if edited_root == null: return _error("scene_path is required when no scene is open in the editor")
		scene_path = edited_root.scene_file_path
		if scene_path.is_empty(): return _error("The edited scene is unsaved; pass scene_path explicitly")
	var checked := _existing_path(scene_path, ["tscn", "scn"])
	if checked.has("error"): return _error(checked.error)
	var packed = load(checked.path)
	if not packed is PackedScene: return _error("Scene is not a PackedScene: %s" % checked.path)
	var raw_output := str(params.get("path", "")).strip_edges()
	if raw_output.is_empty():
		raw_output = "res://.dcc-mcp/preview/%s-%dx%d.png" % [checked.path.md5_text(), width, height]
	var output := _validated_path(raw_output, ["png"])
	if output.has("error"): return _error(output.error)
	var tree := _plugin.get_tree() if _plugin != null else null
	if tree == null: return _error("The DCC-MCP plugin has no SceneTree; scene previews need a running editor host")
	var mkdir_error := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output.path.get_base_dir()))
	if mkdir_error != OK:
		return _error("Unable to create scene preview directory: %s" % error_string(mkdir_error))
	var viewport := SubViewport.new()
	viewport.size = Vector2i(width, height)
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.own_world_3d = true
	viewport.transparent_bg = false
	viewport.disable_3d = false
	tree.root.add_child(viewport)
	var instance = packed.instantiate()
	if not instance is Node:
		_free_preview_viewport(viewport)
		return _error("Scene could not be instantiated: %s" % checked.path)
	viewport.add_child(instance)
	var camera_source := "none"
	var reported_camera_path := str(params.get("camera_path", "")).strip_edges()
	var camera: Node = null
	if not reported_camera_path.is_empty():
		camera = instance.get_node_or_null(NodePath(reported_camera_path))
		if camera == null:
			_free_preview_viewport(viewport)
			return _error("camera_path does not resolve inside the scene: %s" % reported_camera_path)
		if not (camera is Camera3D or camera is Camera2D):
			_free_preview_viewport(viewport)
			return _error("camera_path must resolve to a Camera2D or Camera3D: %s" % reported_camera_path)
		camera_source = "explicit"
	else:
		camera = _first_preview_camera(instance)
		if camera != null:
			camera_source = "scene"
			reported_camera_path = str(instance.get_path_to(camera))
		else:
			var bounds := _preview_scene_bounds(instance, [PREVIEW_BOUNDS_MAX_NODES])
			if bounds.has_bounds:
				camera = _framed_preview_camera(bounds.aabb, float(width) / float(height))
				viewport.add_child(camera)
				camera_source = "framed"
	if camera != null: camera.make_current()
	# A render target only receives pixels once the engine runs real frames:
	# every synchronous draw path (force_draw, VIEWPORT_UPDATE_ONCE, update
	# mode changes) was measured to return a fully blank frame here. The host
	# therefore parks this request and finishes it from the editor's _process
	# tick once frame_count real frames have elapsed.
	_pending_preview = {
		"viewport": viewport,
		"instance": instance,
		"frames_done": 0,
		"frames_target": frame_count,
		"output": output.path,
		"scene_path": checked.path,
		"camera_path": reported_camera_path,
		"camera_source": camera_source,
		"display_driver": display_driver,
		"rendering_method": rendering_method,
		"budget_ms": budget_ms,
		"started_usec": started_usec,
		"created_frame": Engine.get_process_frames(),
		# Only work actually done on the host thread counts against the budget.
		# The parked wait is idle time for this thread, not a main-thread stall.
		"thread_usec": Time.get_ticks_usec() - started_usec,
	}
	return {"__deferred_preview__": true}


func has_pending_preview() -> bool:
	return not _pending_preview.is_empty()


func cancel_pending_preview() -> void:
	if _pending_preview.is_empty(): return
	_free_preview_viewport(_pending_preview.get("viewport"))
	_pending_preview = {}


func poll_pending_preview():
	"""Advance a parked scene preview by one real frame, returning its result when done."""
	if _pending_preview.is_empty(): return null
	if not is_instance_valid(_pending_preview.get("viewport")):
		_pending_preview = {}
		return _error("The pending scene preview viewport was released before it finished rendering")
	# Skip the frame the viewport was created on: it has not been drawn yet.
	if Engine.get_process_frames() <= int(_pending_preview.get("created_frame")): return null
	_pending_preview.frames_done = int(_pending_preview.frames_done) + 1
	if int(_pending_preview.frames_done) < int(_pending_preview.frames_target): return null
	return _finish_pending_preview()


func _finish_pending_preview() -> Dictionary:
	var finish_started_usec := Time.get_ticks_usec()
	var viewport: SubViewport = _pending_preview.get("viewport")
	var image: Image = viewport.get_texture().get_image()
	if image == null:
		_free_preview_viewport(viewport)
		_pending_preview = {}
		return _error("Scene preview produced no image: this host cannot read back rendered pixels (display driver '%s', rendering method '%s')" % [_pending_preview.get("display_driver"), _pending_preview.get("rendering_method")])
	if image.get_format() != Image.FORMAT_RGBA8: image.convert(Image.FORMAT_RGBA8)
	var pixels := image.get_data()
	var output_path := str(_pending_preview.get("output"))
	var display_driver := str(_pending_preview.get("display_driver"))
	var rendering_method := str(_pending_preview.get("rendering_method"))
	var started_usec := int(_pending_preview.get("started_usec"))
	var staging_path := "%s.dcc-mcp-%d.raw" % [output_path, Time.get_ticks_usec()]
	var staging_file := FileAccess.open(staging_path, FileAccess.WRITE)
	if staging_file == null:
		_free_preview_viewport(viewport)
		_pending_preview = {}
		return _error("Unable to stage scene preview pixels")
	staging_file.store_buffer(pixels)
	var write_error := staging_file.get_error()
	staging_file.close()
	if write_error != OK:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(staging_path))
		_free_preview_viewport(viewport)
		_pending_preview = {}
		return _error("Unable to stage scene preview pixels: %s" % error_string(write_error))
	var thread_ms := int(
		(
			int(_pending_preview.get("thread_usec"))
			+ Time.get_ticks_usec()
			- finish_started_usec
		)
		/ 1000
	)
	var elapsed_ms := int((Time.get_ticks_usec() - started_usec) / 1000)
	var result := {
		"path": output_path,
		"width": image.get_width(),
		"height": image.get_height(),
		"scene_path": str(_pending_preview.get("scene_path")),
		"camera_path": str(_pending_preview.get("camera_path")),
		"camera_source": str(_pending_preview.get("camera_source")),
		"frame_count": int(_pending_preview.get("frames_target")),
		"display_driver": display_driver,
		"rendering_method": rendering_method,
		"video_adapter": RenderingServer.get_video_adapter_name(),
		"has_rendering_device": RenderingServer.get_rendering_device() != null,
		"budget_ms": int(_pending_preview.get("budget_ms")),
		# Wall clock for the whole call, including the parked wait.
		"elapsed_ms": elapsed_ms,
		# Host-thread time only, so an idle parked wait is not reported as a
		# main-thread budget overrun.
		"thread_ms": thread_ms,
		"budget_exceeded": thread_ms >= int(_pending_preview.get("budget_ms")),
		"__raw_snapshot__": {
			"path": ProjectSettings.globalize_path(staging_path),
			"output_path": ProjectSettings.globalize_path(output_path),
			"format": "rgba8",
			"byte_length": pixels.size(),
		},
	}
	_free_preview_viewport(viewport)
	_pending_preview = {}
	return result


func _free_preview_viewport(viewport: SubViewport) -> void:
	if viewport == null or not is_instance_valid(viewport): return
	viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	viewport.queue_free()


func _first_preview_camera(node: Node) -> Node:
	if node is Camera3D or node is Camera2D: return node
	for child in node.get_children():
		var found := _first_preview_camera(child)
		if found != null: return found
	return null


func _preview_scene_bounds(node: Node, budget: Array) -> Dictionary:
	var entries: Array = []
	_collect_preview_bounds(node, Transform3D.IDENTITY, budget, entries)
	if entries.is_empty(): return {"has_bounds": false, "aabb": AABB()}
	# Sort by extent so the smallest object is always the fallback subject.
	entries.sort_custom(
		func(a, b): return (a.aabb as AABB).size.length() < (b.aabb as AABB).size.length()
	)
	# A ground plane is routinely orders of magnitude larger than the objects it
	# carries; letting it into the union would park the framing camera far
	# outside the actual subject and render a near-empty frame. Reject those
	# outliers against the median extent instead.
	var middle := (entries[entries.size() / 2].aabb as AABB).size.length()
	var limit := maxf(middle * 4.0, 0.001)
	var result := {"has_bounds": true, "aabb": entries[0].aabb}
	for entry in entries:
		var aabb: AABB = entry.aabb
		if aabb.size.length() > limit: break
		result.aabb = (result.aabb as AABB).merge(aabb)
	return result


func _collect_preview_bounds(
	node: Node, parent_transform: Transform3D, budget: Array, entries: Array
) -> void:
	# Walk the transform chain by hand: the engine has not propagated global
	# transforms for a scene that was instantiated moments ago.
	if budget[0] <= 0: return
	budget[0] -= 1
	var transform := parent_transform
	if node is Node3D:
		transform = parent_transform * (node as Node3D).transform
		# Only visible geometry frames the shot. Lights, probes, and other
		# VisualInstance3D helpers carry a helper AABB that would drag the
		# framing centre away from the subject.
		if node is GeometryInstance3D:
			var local_aabb := (node as GeometryInstance3D).get_aabb()
			if local_aabb.size.length_squared() > 0.0:
				entries.append({"aabb": transform * local_aabb})
	for child in node.get_children():
		if budget[0] <= 0: return
		_collect_preview_bounds(child, transform, budget, entries)


func _framed_preview_camera(bounds: AABB, aspect: float) -> Camera3D:
	var camera := Camera3D.new()
	var center := bounds.get_center()
	var radius := maxf(bounds.size.length() * 0.5, 0.05)
	var fov := 50.0
	var distance := radius / tan(deg_to_rad(fov) * 0.5) * 1.2
	if aspect < 1.0:
		distance /= maxf(aspect, 0.05)
	camera.fov = fov
	# look_at() needs the node to be inside the tree; this camera is added to
	# the preview viewport only after it is configured, so position and
	# orientation are set together while it is still detached.
	camera.look_at_from_position(
		center + Vector3(0.6, 0.45, 1.0).normalized() * distance, center, Vector3.UP
	)
	camera.near = maxf(0.01, distance - radius * 4.0)
	camera.far = distance + radius * 8.0
	return camera


func _get_signals(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null: return _error("Node not found")
	var signals: Array[Dictionary] = []
	for info in node.get_signal_list():
		var connections: Array[Dictionary] = []
		for item in node.get_signal_connection_list(str(info.name)):
			var callable: Callable = item.callable
			connections.append({"target": str(callable.get_object().get_path()) if callable.get_object() is Node else str(callable.get_object()), "method": callable.get_method(), "flags": item.flags})
		signals.append({"name": info.name, "arguments": info.args, "connections": connections})
	return {"node_path": str(node.get_path()), "signals": signals}


func _reload_plugin() -> Dictionary:
	# Disabling the plugin synchronously destroys this very call stack before
	# the matching enable can run. Queue both operations on the persistent
	# EditorInterface singleton so the RPC response completes first.
	EditorInterface.set_plugin_enabled.call_deferred("dcc_mcp_godot", false)
	EditorInterface.set_plugin_enabled.call_deferred("dcc_mcp_godot", true)
	return {"reloading": true}


func _reload_project() -> Dictionary:
	EditorInterface.get_resource_filesystem().scan()
	var root := EditorInterface.get_edited_scene_root()
	if root != null and not root.scene_file_path.is_empty(): EditorInterface.reload_scene_from_path(root.scene_file_path)
	return {"reloaded": true}


func _get_input_actions(params: Dictionary = {}) -> Dictionary:
	for field in params:
		if field != "source": return _error("Unsupported input query field: %s" % field)
	var source = params.get("source", "editor")
	if source not in ["editor", "project"]: return _error("source must be editor or project")
	var actions: Array[Dictionary] = []
	if source == "project":
		# EditorPlugin InputMap contains editor shortcuts, not the project's bindings.
		for property in ProjectSettings.get_property_list():
			var name := str(property.name)
			if not name.begins_with("input/"): continue
			var setting = ProjectSettings.get_setting(name)
			if not _valid_input_setting(setting): return _error("Invalid project input setting: %s" % name)
			actions.append({"name": name.trim_prefix("input/"), "deadzone": float(setting.get("deadzone", 0.2)), "events": setting.events.map(func(event): return event.as_text() if event != null else "(empty event)")})
	else:
		for action in InputMap.get_actions():
			if str(action).begins_with("ui_"): continue
			actions.append({"name": str(action), "deadzone": InputMap.action_get_deadzone(action), "events": InputMap.action_get_events(action).map(func(event): return event.as_text())})
	return {"actions": actions, "source": source}


func _valid_input_setting(setting) -> bool:
	if not setting is Dictionary or not setting.get("events") is Array: return false
	var deadzone = setting.get("deadzone", 0.2)
	if not (deadzone is int or deadzone is float) or not is_finite(float(deadzone)) or deadzone < 0 or deadzone > 1: return false
	for event in setting.events:
		if event != null and not event is InputEvent: return false
	return true


func _set_input_action(params: Dictionary) -> Dictionary:
	# Validate everything before either editor InputMap or ProjectSettings changes.
	for field in params:
		if field not in ["action", "keycode", "deadzone", "replace_events", "persist"]:
			return _error("Unsupported input action field: %s" % field)
	var action = params.get("action")
	if not action is String or action.is_empty() or action.length() > 500:
		return _error("action must be a non-empty string of at most 500 characters")
	for index in action.length():
		if action.unicode_at(index) < 32 or action[index] in ["/", ":", "=", "\\", "\""]:
			return _error("action contains a character forbidden by the Godot Input Map editor")
	for flag in ["persist", "replace_events"]:
		if params.has(flag) and not params[flag] is bool: return _error("%s must be a boolean" % flag)
	if params.has("deadzone"):
		var raw = params.deadzone
		if not (raw is int or raw is float) or not is_finite(float(raw)) or raw < 0 or raw > 1:
			return _error("deadzone must be a finite number between 0 and 1")
	var event: InputEventKey = null
	if params.has("keycode"):
		var raw = params.keycode
		if not (raw is int or raw is float) or not is_finite(float(raw)) or raw != floor(float(raw)) or raw < 1 or raw >= KEY_UNKNOWN or not _valid_input_keycode(int(raw)):
			return _error("keycode must be a known raw Godot Key integer, without modifier masks")
		event = InputEventKey.new()
		event.keycode = int(raw)
	if params.get("persist", false): return _set_project_input_action(params, action, event)
	# Backward-compatible editor-process-only mode. Never saves project settings.
	if not InputMap.has_action(action): InputMap.add_action(action, float(params.get("deadzone", 0.5)))
	else: InputMap.action_set_deadzone(action, float(params.get("deadzone", InputMap.action_get_deadzone(action))))
	if params.get("replace_events", false): InputMap.action_erase_events(action)
	if event != null: InputMap.action_add_event(action, event)
	return {"updated": true, "action": action, "deadzone": InputMap.action_get_deadzone(action), "source": "editor", "persisted": false}


func _valid_input_keycode(code: int) -> bool:
	# Public raw Key constants shared by the supported Godot 4.4+ API. These
	# ranges deliberately exclude enum holes, lowercase ASCII and modifier masks.
	return ((code >= KEY_SPACE and code <= KEY_QUOTELEFT)
		or (code >= KEY_BRACELEFT and code <= KEY_ASCIITILDE)
		or code in [KEY_YEN, KEY_SECTION, KEY_MENU, KEY_HYPER, KEY_HELP]
		or (code >= KEY_ESCAPE and code <= KEY_F35)
		or (code >= KEY_BACK and code <= KEY_VOLUMEUP)
		or (code >= KEY_MEDIAPLAY and code <= KEY_JIS_KANA)
		or (code >= KEY_KP_MULTIPLY and code <= KEY_KP_9))


func _set_project_input_action(params: Dictionary, action: String, event: InputEventKey) -> Dictionary:
	var key := "input/" + action
	var existed := ProjectSettings.has_setting(key)
	var previous = ProjectSettings.get_setting(key) if existed else null
	if existed and not _valid_input_setting(previous): return _error("Invalid existing project input setting: %s" % key)
	var setting: Dictionary = previous.duplicate() if existed else {"deadzone": 0.5, "events": []}
	if not setting.has("deadzone"): setting.deadzone = 0.2
	var events: Array = [] if params.get("replace_events", false) else setting.events.duplicate()
	if event != null:
		var duplicate := false
		for existing in events:
			# is_match ignores device and may use key-label/physical fallback. Do not
			# swallow a distinct device, physical key, label, location or modifier bind.
			if existing is InputEventKey and existing.device == event.device and existing.physical_keycode == 0 and existing.key_label == 0 and existing.location == event.location and existing.is_match(event, true):
				duplicate = true
				break
		if not duplicate: events.append(event)
	setting.events = events
	if params.has("deadzone"): setting.deadzone = float(params.deadzone)
	ProjectSettings.set_setting(key, setting)
	var saved := ProjectSettings.save()
	if saved != OK:
		if existed: ProjectSettings.set_setting(key, previous)
		else: ProjectSettings.clear(key)
		return _error("Project input action save failed (%s); target setting restored in memory, disk state unverified" % error_string(saved))
	# Saving project defaults does not rewrite editor shortcuts or a running game.
	return {"updated": true, "action": action, "deadzone": float(setting.deadzone), "source": "project", "persisted": true}


func _find_nodes_by_type(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null: return _error("No scene is open")
	var type_name := str(params.get("type", "Node"))
	var paths: Array[String] = []
	_collect_matching_nodes(root, func(node): return node.is_class(type_name), paths)
	return {"type": type_name, "nodes": paths}


func _find_signal_connections() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null: return _error("No scene is open")
	var connections: Array[Dictionary] = []
	_collect_connections(root, connections)
	return {"connections": connections, "count": connections.size()}


func _batch_set_property(params: Dictionary) -> Dictionary:
	var found := _find_nodes_by_type(params)
	if found.has("__error__"): return found
	var updated: Array[String] = []
	for path in found.nodes:
		var result := _update_property({"node_path": path, "property": params.get("property", ""), "value": params.get("value")})
		if not result.has("__error__"): updated.append(path)
	return {"updated": updated, "count": updated.size()}


func _get_scene_dependencies(params: Dictionary) -> Dictionary:
	var checked := _existing_path(params.get("path", ""), ["tscn", "scn"])
	if checked.has("error"): return _error(checked.error)
	return {"path": checked.path, "dependencies": Array(ResourceLoader.get_dependencies(checked.path))}


func _cross_scene_set_property(params: Dictionary) -> Dictionary:
	var changed: Array[String] = []
	for path in _collect_files("res://", ["tscn"]):
		var packed = load(path)
		if not packed is PackedScene: continue
		var root = packed.instantiate()
		var type_name := str(params.get("type", "Node"))
		var property_name := str(params.get("property", ""))
		var count := _set_property_recursive(root, type_name, property_name, params.get("value"))
		if count > 0:
			var replacement := PackedScene.new()
			if replacement.pack(root) == OK and ResourceSaver.save(replacement, path) == OK: changed.append(path)
		root.free()
	return {"changed_scenes": changed, "count": changed.size()}


func _detect_circular_dependencies() -> Dictionary:
	var graph := {}
	for path in _collect_files("res://", ["tscn"]): graph[path] = Array(ResourceLoader.get_dependencies(path)).filter(func(dep): return str(dep).get_slice("::", 2).ends_with(".tscn"))
	var cycles: Array[Array] = []
	for start in graph:
		_find_cycles(str(start), str(start), graph, [], cycles)
	return {"cycles": cycles, "count": cycles.size()}


func _analyze_scene_complexity() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null: return _error("No scene is open")
	var stats := {"nodes": 0, "scripts": 0, "physics_nodes": 0, "lights": 0, "particles": 0, "controls": 0}
	_accumulate_complexity(root, stats)
	return {"scene_path": root.scene_file_path, "statistics": stats}


func _find_unused_resources() -> Dictionary:
	var resources := _collect_files("res://", ["tres", "res", "png", "jpg", "wav", "ogg", "glb", "gltf"])
	var text := ""
	for path in _collect_files("res://", ["gd", "tscn", "tres", "gdshader"]):
		var file := FileAccess.open(path, FileAccess.READ)
		if file != null and file.get_length() <= MAX_TEXT_BYTES: text += file.get_as_text()
	var unused: Array[String] = []
	for path in resources:
		if path not in text: unused.append(path)
	return {"candidates": unused, "count": unused.size(), "note": "Candidates are based on text references; dynamic loads may not be visible."}


func _get_project_statistics() -> Dictionary:
	var files := _collect_files("res://", [])
	var counts := {"files": files.size(), "scenes": 0, "scripts": 0, "resources": 0, "shaders": 0}
	for path in files:
		match path.get_extension().to_lower():
			"tscn", "scn": counts.scenes += 1
			"gd": counts.scripts += 1
			"tres", "res": counts.resources += 1
			"gdshader": counts.shaders += 1
	return counts


func _get_editor_performance() -> Dictionary:
	return {"process_memory_bytes": OS.get_static_memory_usage(), "peak_memory_bytes": OS.get_static_memory_peak_usage(), "editor_fps": Engine.get_frames_per_second(), "playing": EditorInterface.is_playing_scene()}


func _list_export_presets() -> Dictionary:
	var presets: Array[Dictionary] = []
	var config := ConfigFile.new()
	if config.load("res://export_presets.cfg") != OK: return {"presets": presets}
	for section in config.get_sections():
		if not section.begins_with("preset.") or ".options" in section: continue
		presets.append({"index": int(section.trim_prefix("preset.")), "name": config.get_value(section, "name", ""), "platform": config.get_value(section, "platform", ""), "runnable": config.get_value(section, "runnable", false), "export_path": config.get_value(section, "export_path", "")})
	return {"presets": presets}


func _export_project(params: Dictionary) -> Dictionary:
	var preset := str(params.get("preset", ""))
	if preset.is_empty(): return _error("preset is required")
	var path := str(params.get("path", ""))
	if path.is_empty() or path.is_absolute_path() or ".." in path: return _error("Export path must be relative to the project")
	var absolute := ProjectSettings.globalize_path("res://" + path.trim_prefix("res://"))
	var args := PackedStringArray(["--path", ProjectSettings.globalize_path("res://"), "--headless", "--export-debug" if bool(params.get("debug", false)) else "--export-release", preset, absolute])
	var output: Array = []
	var exit_code := OS.execute(OS.get_executable_path(), args, output, true, false)
	return {"exported": exit_code == 0, "exit_code": exit_code, "path": "res://" + path.trim_prefix("res://"), "output": "\n".join(output).right(20000)}


func _get_export_job_context() -> Dictionary:
	if EditorInterface.get_resource_filesystem().is_scanning():
		return _error("Resource scan is active; export context is not ready")
	for path in ["res://project.godot", "res://export_presets.cfg"]:
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null: return _error("Saved project and export presets are required")
		if file.get_length() > 1048576: return _error("Export configuration exceeds bounded context limit")
		file.close()
	var names: Array[String] = []
	for preset in _list_export_presets().presets:
		names.append(str(preset.name))
	return {"project_path": ProjectSettings.globalize_path("res://"),
		"executable": OS.get_executable_path(), "engine_version": Engine.get_version_info().string,
		"preset_names": names, "project_sha256": FileAccess.get_sha256("res://project.godot"),
		"presets_sha256": FileAccess.get_sha256("res://export_presets.cfg")}


func _get_export_info() -> Dictionary:
	var presets := _list_export_presets()
	return {"project": ProjectSettings.get_setting("application/config/name", ""), "version": ProjectSettings.get_setting("application/config/version", ""), "presets": presets.presets, "executable": OS.get_executable_path()}


func _create_fire_vfx(params: Dictionary) -> Dictionary:
	var parent_path := str(params.get("parent_path", "."))
	var parent := _scene_node(parent_path)
	var root := EditorInterface.get_edited_scene_root()
	if not parent is Node3D or (parent != root and not root.is_ancestor_of(parent)):
		return _error("Fire VFX requires a Node3D parent in the edited scene")
	var node_name := str(params.get("name", "FireVFX"))
	if node_name.strip_edges().is_empty() or node_name != node_name.validate_node_name():
		return _error("name must be a non-empty valid Godot node name")
	var shader_path := "res://addons/dcc_mcp_godot/templates/vfx/stylized_fire.gdshader"
	var shader := load(shader_path) as Shader
	if shader == null: return _error("Bundled fire shader is unavailable")
	var material := ShaderMaterial.new()
	material.shader = shader
	material.resource_local_to_scene = true
	# Headless saves must not serialize unset shader defaults as null overrides.
	var defaults := {
		"scroll_speed": 0.65, "noise_scale": Vector2(3.0, 1.4), "detail_scale": Vector2(5.0, 2.0),
		"erosion": 0.4, "edge_softness": 0.08, "sway": 0.18, "twist": 0.9,
		"emission_strength": 1.6, "dissolve": 0.0,
	}
	for parameter in defaults: material.set_shader_parameter(parameter, defaults[parameter])
	for index in range(2):
		var noise := FastNoiseLite.new()
		noise.seed = 1701 + index * 7919
		noise.frequency = 0.03 if index == 0 else 0.045
		var texture := NoiseTexture2D.new()
		texture.width = 256
		texture.height = 256
		texture.seamless = true
		texture.noise = noise
		material.set_shader_parameter("noise_texture" if index == 0 else "detail_texture", texture)
	var gradient := Gradient.new()
	gradient.offsets = PackedFloat32Array([0.0, 0.4, 0.75, 1.0])
	gradient.colors = PackedColorArray([Color("fff4b0"), Color("ffad24"), Color("f2350c"), Color("4a0802")])
	var ramp := GradientTexture1D.new()
	ramp.gradient = gradient
	material.set_shader_parameter("color_ramp", ramp)
	var mesh := CylinderMesh.new()
	mesh.height = 2.4
	mesh.bottom_radius = 0.55
	mesh.top_radius = 0.35
	mesh.radial_segments = 64
	mesh.rings = 24
	mesh.cap_top = false
	mesh.cap_bottom = false
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.position.y = mesh.height * 0.5
	node.material_override = material
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	# Vertex sway reaches beyond the undeformed mesh bounds.
	node.custom_aabb = AABB(Vector3(-1.6, -1.2, -1.6), Vector3(3.2, 2.4, 3.2))
	var result := _add_existing_node(node, parent_path)
	if result.has("__error__"): return result
	result.merge({"node_path": str(node.get_path()), "effect": "stylized_fire", "shader_path": shader_path, "mesh": "CylinderMesh"})
	return result


func _vfx_tint(params: Dictionary) -> Dictionary:
	var tint = params.get("tint", "#ff6018")
	if not tint is String or tint.length() != 7 or not tint.begins_with("#") or not Color.html_is_valid(tint):
		return {"error": "tint must be a #RRGGBB color"}
	return {"value": Color.html(tint)}


func _create_vfx_node(params: Dictionary, projectile: bool) -> Dictionary:
	var parent_path := str(params.get("parent_path", "."))
	var parent := _scene_node(parent_path)
	var root := EditorInterface.get_edited_scene_root()
	if not parent is Node3D or (parent != root and not root.is_ancestor_of(parent)):
		return _error("VFX requires a Node3D parent in the edited scene")
	var node_name := str(params.get("name", "SpellProjectile" if projectile else "DynamicFire"))
	if node_name.strip_edges().is_empty() or node_name.length() > 100 or node_name != node_name.validate_node_name():
		return _error("name must be a valid Godot node name of 1-100 characters")
	var tint := _vfx_tint(params)
	if tint.has("error"): return _error(tint.error)
	var node: Node3D
	var template_dir := "res://addons/dcc_mcp_godot/templates/vfx/"
	if projectile:
		var speed = params.get("speed", 8.0)
		var lifetime = params.get("lifetime", 4.0)
		if not _finite_shader_number(speed) or speed < 0.1 or speed > 100.0:
			return _error("speed must be a finite number between 0.1 and 100")
		if not _finite_shader_number(lifetime) or lifetime < 0.1 or lifetime > 30.0:
			return _error("lifetime must be a finite number between 0.1 and 30")
		var script := load(template_dir + "spell_projectile.gd") as GDScript
		if script == null or script.reload() != OK: return _error("Bundled projectile script is unavailable")
		node = Node3D.new()
		node.set_script(script)
		node.set("speed", float(speed))
		node.set("lifetime", float(lifetime))
		node.set("tint", tint.value)
	else:
		var amount = params.get("amount", 48)
		if not _finite_shader_number(amount) or amount != floor(amount) or amount < 8 or amount > 256:
			return _error("amount must be an integer between 8 and 256")
		var texture: Texture2D
		if params.has("texture_path"):
			var checked := _existing_path(params.texture_path, ["png", "jpg", "jpeg", "webp", "svg", "tres", "res"])
			if checked.has("error"): return _error(checked.error)
			texture = load(checked.path) as Texture2D
			if texture == null: return _error("texture_path must identify an imported Texture2D")
		var script := load(template_dir + "dynamic_fire.gd") as GDScript
		if script == null or not script.can_instantiate(): return _error("Bundled dynamic fire script is unavailable")
		node = script.create(tint.value, int(amount), texture)
	if node == null: return _error("Unable to create VFX")
	node.name = node_name
	var result := _add_existing_node(node, parent_path, true)
	if not result.has("__error__"):
		result.merge({"node_path": str(node.get_path()), "effect": "spell_projectile" if projectile else "dynamic_fire"})
	return result


func _new_vfx_directory(directory) -> Dictionary:
	if not directory is String or directory.length() > 500 or not directory.begins_with("res://"):
		return _error("directory must be a new folder below res://")
	var cursor := "res://"
	for component in directory.trim_prefix("res://").split("/"):
		if component.is_empty() or component in [".", ".."] or component != component.validate_filename():
			return _error("directory contains an invalid path component")
		var parent_dir := DirAccess.open(cursor)
		if parent_dir != null and parent_dir.is_link(component):
			return _error("directory must not traverse a symbolic link")
		cursor = cursor.path_join(component)
	if DirAccess.dir_exists_absolute(directory) or FileAccess.file_exists(directory):
		return _error("VFX directory already exists; choose a new directory to preserve existing files")
	return {"directory": directory}


func _create_spellcasting_demo(params: Dictionary) -> Dictionary:
	var checked_directory := _new_vfx_directory(params.get("directory", "res://spell_vfx"))
	if checked_directory.has("__error__"): return checked_directory
	var directory: String = checked_directory.directory
	var tint := _vfx_tint(params)
	if tint.has("error"): return _error(tint.error)
	var auto_cast = params.get("auto_cast", true)
	if not auto_cast is bool: return _error("auto_cast must be a boolean")
	var mage: PackedScene
	if params.has("mage_path"):
		var checked := _existing_path(params.mage_path, ["glb", "gltf", "tscn", "scn"])
		if checked.has("error"): return _error(checked.error)
		mage = load(checked.path) as PackedScene
		if mage == null: return _error("mage_path must identify an imported PackedScene")
		var instance := mage.instantiate()
		if not instance is Node3D:
			instance.free()
			return _error("mage_path must have a Node3D root")
		var has_hand := false
		var has_cast := false
		for child in instance.find_children("*", "", true, false):
			if child is Skeleton3D and child.find_bone("RightCastSocket") >= 0: has_hand = true
			if child is AnimationPlayer:
				for animation_name in child.get_animation_list():
					if str(animation_name).get_file() == "Cast" and is_equal_approx(child.get_animation(animation_name).length, 1.6): has_cast = true
		instance.free()
		if not has_hand or not has_cast:
			return _error("mage_path requires a child Skeleton3D with RightCastSocket and a 1.6-second Cast animation; static models must be rigged first")
	var installed := _copy_vfx_templates(directory)
	if installed.has("__error__"): return installed
	var demo_script := load(directory.path_join("spellcasting_demo.gd")) as GDScript
	if demo_script == null or demo_script.reload() != OK: return _error("Demo script could not load; written files were preserved")
	var demo := Node3D.new()
	demo.name = "SpellcastingDemo"
	demo.set_script(demo_script)
	demo.set("mage_scene", mage)
	demo.set("tint", tint.value)
	demo.set("auto_cast", auto_cast)
	var packed := PackedScene.new()
	var pack_error := packed.pack(demo)
	demo.free()
	if pack_error != OK: return _error("Unable to pack demo scene")
	var scene_path: String = directory.path_join("spellcasting_demo.tscn")
	var save_error := ResourceSaver.save(packed, scene_path)
	if save_error != OK: return _error("Unable to save demo scene: %s" % error_string(save_error))
	EditorInterface.get_resource_filesystem().scan()
	return {"created": true, "scene_path": scene_path, "directory": directory, "mage_path": params.get("mage_path", ""), "main_scene_changed": false}


func _copy_vfx_templates(directory: String) -> Dictionary:
	var source_dir := "res://addons/dcc_mcp_godot/templates/vfx"
	var sources := {}
	for filename in DirAccess.get_files_at(source_dir):
		if filename.get_extension() not in ["gd", "gdshader", "tscn"]: continue
		var source := FileAccess.open(source_dir.path_join(filename), FileAccess.READ)
		if source == null: return _error("Bundled VFX template is unreadable: %s" % filename)
		sources[filename] = source.get_buffer(source.get_length())
	for required in ["dynamic_fire.gd", "dynamic_fire.gdshader", "stylized_fire.gdshader", "spell_projectile.gd", "spell_trail.gdshader", "spellcasting_demo.gd", "spellcasting_demo.tscn", "combat_effect.gd", "combat_ring.gdshader", "attack_slash.tscn", "spell_impact.tscn", "magic_aura.tscn", "fire_projectile.tscn", "mesh_fire.tscn", "particle_fire.tscn", "combat_vfx_gallery.gd", "combat_vfx_gallery.tscn"]:
		if not sources.has(required): return _error("Bundled VFX template is missing: %s" % required)
	var mkdir_error := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory.get_base_dir()))
	if mkdir_error != OK: return _error("Unable to create VFX parent directory: %s" % error_string(mkdir_error))
	# Claim the new leaf without accepting a destination created by another caller.
	mkdir_error = DirAccess.make_dir_absolute(ProjectSettings.globalize_path(directory))
	if mkdir_error != OK: return _error("Unable to create new VFX directory: %s" % error_string(mkdir_error))
	for filename in sources:
		var output := FileAccess.open(directory.path_join(filename), FileAccess.WRITE)
		if output == null: return _error("Unable to write demo file: %s" % directory.path_join(filename))
		output.store_buffer(sources[filename])
		var write_error := output.get_error()
		output.close()
		if write_error != OK: return _error("Unable to finish writing demo file: %s" % directory.path_join(filename))
	return {"directory": directory, "files": sources.keys()}


func _install_combat_vfx_library(params: Dictionary) -> Dictionary:
	var checked := _new_vfx_directory(params.get("directory", "res://combat_vfx"))
	if checked.has("__error__"): return checked
	var directory: String = checked.directory
	var installed := _copy_vfx_templates(directory)
	if installed.has("__error__"): return installed
	var presets := {}
	for preset in ["attack_slash", "spell_impact", "magic_aura", "fire_projectile", "mesh_fire", "particle_fire"]:
		presets[preset] = directory.path_join(preset + ".tscn")
	EditorInterface.get_resource_filesystem().scan()
	return {"installed": true, "directory": directory, "presets": presets, "gallery_scene": directory.path_join("combat_vfx_gallery.tscn"), "files": installed.files, "main_scene_changed": false}


func _create_combat_vfx(params: Dictionary) -> Dictionary:
	var parent_path := str(params.get("parent_path", "."))
	var parent := _scene_node(parent_path)
	var root := EditorInterface.get_edited_scene_root()
	if not parent is Node3D or (parent != root and not root.is_ancestor_of(parent)):
		return _error("Combat VFX requires a Node3D parent in the edited scene")
	var effect = params.get("effect", "aura")
	if effect not in ["slash", "impact", "aura"]: return _error("effect must be slash, impact, or aura")
	var node_name := str(params.get("name", "CombatVFX"))
	if node_name.strip_edges().is_empty() or node_name.length() > 100 or node_name != node_name.validate_node_name():
		return _error("name must be a valid Godot node name of 1-100 characters")
	var radius = params.get("radius", 1.5)
	var duration = params.get("duration", 0.6)
	if not _finite_shader_number(radius) or radius < 0.1 or radius > 20.0:
		return _error("radius must be a finite number between 0.1 and 20")
	if not _finite_shader_number(duration) or duration < 0.05 or duration > 10.0:
		return _error("duration must be a finite number between 0.05 and 10")
	var autoplay = params.get("autoplay", true)
	var auto_free = params.get("auto_free", false)
	if not autoplay is bool or not auto_free is bool: return _error("autoplay and auto_free must be booleans")
	var tint := _vfx_tint(params)
	if tint.has("error"): return _error(tint.error)
	var script := load("res://addons/dcc_mcp_godot/templates/vfx/combat_effect.gd") as GDScript
	if script == null or script.reload(true) != OK: return _error("Bundled combat VFX script is unavailable")
	var node := Node3D.new()
	node.name = node_name
	node.set_script(script)
	var values := {"kind": effect, "tint": tint.value, "radius": float(radius), "duration": float(duration), "autoplay": autoplay, "auto_free": auto_free}
	for property in values: node.set(property, values[property])
	var result := _add_existing_node(node, parent_path)
	if not result.has("__error__"): result.merge({"node_path": str(node.get_path()), "effect": effect})
	return result


func _create_shader(params: Dictionary) -> Dictionary:
	var checked := _validated_path(params.get("path", ""), ["gdshader"])
	if checked.has("error"): return _error(checked.error)
	var shader_type := str(params.get("shader_type", "canvas_item"))
	if shader_type not in ["canvas_item", "spatial", "particles", "sky", "fog"]: return _error("Unsupported shader_type")
	var source := str(params.get("source", "shader_type %s;\n\nvoid fragment() {\n}\n" % shader_type))
	return _write_text(checked.path, source)


func _assign_shader_material(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	var checked := _existing_path(params.get("shader_path", ""), ["gdshader"])
	if node == null: return _error("Node not found")
	if checked.has("error"): return _error(checked.error)
	var material := ShaderMaterial.new()
	material.shader = load(checked.path)
	if node is CanvasItem: node.material = material
	elif node is GeometryInstance3D: node.material_override = material
	else: return _error("Node must be CanvasItem or GeometryInstance3D")
	return {"assigned": true, "node_path": str(node.get_path()), "shader_path": checked.path}


func _shader_material(params: Dictionary):
	var node := _scene_node(str(params.get("node_path", ".")))
	if node is CanvasItem and node.material is ShaderMaterial: return node.material
	if node is GeometryInstance3D and node.material_override is ShaderMaterial: return node.material_override
	return null


func _set_shader_param(params: Dictionary) -> Dictionary:
	var material = _shader_material(params)
	if material == null or material.shader == null: return _error("Node has no ShaderMaterial")
	if not params.has("value"): return _error("value is required; pass null explicitly to clear a texture")
	var parameter := str(params.get("parameter", ""))
	for uniform in material.shader.get_shader_uniform_list():
		if str(uniform.name) != parameter: continue
		var converted := _shader_uniform_value(uniform, params.get("value"))
		if converted.has("error"): return _error(converted.error)
		material.set_shader_parameter(parameter, converted.value)
		return {"updated": true, "parameter": parameter, "value": _json_value(material.get_shader_parameter(parameter))}
	return _error("Shader parameter not found: %s" % parameter)


func _shader_uniform_value(uniform: Dictionary, value) -> Dictionary:
	var uniform_type := int(uniform.type)
	if uniform_type == TYPE_INT and int(uniform.get("hint", 0)) == PROPERTY_HINT_FLAGS:
		return {"error": "Boolean vector uniforms are unsupported"}
	if uniform_type == TYPE_INT and str(uniform.get("hint_string", "")) == "0,4294967295":
		return {"error": "Unsigned shader integers are not supported"}
	if uniform_type == TYPE_BOOL and value is bool: return {"value": value}
	if uniform_type in [TYPE_INT, TYPE_FLOAT] and _finite_shader_number(value):
		if uniform_type == TYPE_FLOAT: return {"value": float(value)}
		if value == floor(value) and value >= -2147483648 and value <= 2147483647:
			return {"value": int(value)}
	if uniform_type == TYPE_COLOR and value is String:
		if value.begins_with("#") and value.length() in [7, 9] and Color.html_is_valid(value):
			return {"value": Color.html(value)}
	if uniform_type in [TYPE_VECTOR2, TYPE_VECTOR3, TYPE_VECTOR4, TYPE_COLOR] and value is Array:
		var size := 2 if uniform_type == TYPE_VECTOR2 else (3 if uniform_type == TYPE_VECTOR3 else 4)
		if value.size() != size: return {"error": "Shader vector/color requires exactly %d components" % size}
		for component in value:
			if not _finite_shader_number(component): return {"error": "Shader components must be finite numbers"}
		match uniform_type:
			TYPE_VECTOR2: return {"value": Vector2(value[0], value[1])}
			TYPE_VECTOR3: return {"value": Vector3(value[0], value[1], value[2])}
			TYPE_VECTOR4: return {"value": Vector4(value[0], value[1], value[2], value[3])}
			TYPE_COLOR: return {"value": Color(value[0], value[1], value[2], value[3])}
	if uniform_type == TYPE_OBJECT and str(uniform.get("hint_string", "")) == "Texture2D":
		if value == null: return {"value": null}
		if value is String:
			var checked := _existing_path(value, [])
			if checked.has("error"): return checked
			var texture := load(checked.path) as Texture2D
			if texture != null: return {"value": texture}
			return {"error": "Shader sampler requires a Texture2D project resource"}
	return {"error": "Invalid or unsupported value for shader parameter: %s" % uniform.name}


func _finite_shader_number(value) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and abs(float(value)) <= 3.4028234663852886e38


func _get_shader_params(params: Dictionary) -> Dictionary:
	var material = _shader_material(params)
	if material == null or material.shader == null: return _error("Node has no ShaderMaterial")
	var values := {}
	for item in material.shader.get_shader_uniform_list():
		var parameter := str(item.name)
		var value = material.get_shader_parameter(parameter)
		if value == null:
			value = RenderingServer.shader_get_parameter_default(material.shader.get_rid(), parameter)
		values[parameter] = _json_value(value)
	return {"parameters": values}


func _read_resource(params: Dictionary) -> Dictionary:
	var checked := _existing_path(params.get("path", ""), ["tres", "res"])
	if checked.has("error"): return _error(checked.error)
	var resource = load(checked.path)
	if resource == null: return _error("Unable to load resource")
	return {"path": checked.path, "type": resource.get_class(), "properties": _stored_properties(resource)}


func _edit_resource(params: Dictionary) -> Dictionary:
	var checked := _existing_path(params.get("path", ""), ["tres", "res"])
	if checked.has("error"): return _error(checked.error)
	var resource = load(checked.path)
	if resource == null: return _error("Unable to load resource")
	for key in (params.get("properties", {}) as Dictionary):
		if not _has_property(resource, str(key)): return _error("Resource property not found: %s" % key)
		resource.set(str(key), _coerce_value(resource.get(str(key)), params.properties[key]))
	var save_error := ResourceSaver.save(resource, checked.path)
	if save_error != OK: return _error("Unable to save resource: %s" % error_string(save_error))
	return {"updated": true, "path": checked.path, "properties": _stored_properties(resource)}


func _create_resource(params: Dictionary) -> Dictionary:
	var checked := _validated_path(params.get("path", ""), ["tres", "res"])
	if checked.has("error"): return _error(checked.error)
	var resource = ClassDB.instantiate(str(params.get("type", "Resource")))
	if not resource is Resource:
		if resource != null: resource.free()
		return _error("Type is not a Resource")
	for key in (params.get("properties", {}) as Dictionary):
		if _has_property(resource, str(key)): resource.set(str(key), _coerce_value(resource.get(str(key)), params.properties[key]))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(checked.path.get_base_dir()))
	var save_error := ResourceSaver.save(resource, checked.path)
	if save_error != OK: return _error("Unable to save resource: %s" % error_string(save_error))
	return {"created": true, "path": checked.path, "type": resource.get_class()}


func _get_resource_preview(params: Dictionary) -> Dictionary:
	var checked := _existing_path(params.get("path", ""), [])
	if checked.has("error"): return _error(checked.error)
	var path: String = checked.path
	var identity := _resource_preview_identity(path)
	if identity.has("error"): return _error(identity.error)
	if DisplayServer.get_name() == "headless":
		return {"path": path, "available": false, "reason": "Resource previews require a windowed editor; the headless preview worker is disabled"}
	if not _pending_resource_preview.is_empty():
		return _error("A resource preview is already pending; wait for its terminal result")
	if EditorInterface.get_resource_filesystem().is_scanning():
		return _error("Resource import is still scanning; retry after import completes")
	_resource_preview_generation += 1
	var token := _resource_preview_generation
	# A cache hit can invoke the callback inside queue_resource_preview. Install
	# ownership first, and never save or re-enter the previewer from the callback.
	_pending_resource_preview = {
		"token": token, "path": path, "identity": identity,
		"deadline_ms": Time.get_ticks_msec() + RESOURCE_PREVIEW_TIMEOUT_MS,
		"completed": false,
	}
	var previewer := EditorInterface.get_resource_previewer()
	previewer.check_for_invalidation(path)
	previewer.queue_resource_preview(path, self, "_resource_preview_ready", token)
	return {"__deferred_resource_preview__": true}


func _resource_preview_ready(path: String, preview: Texture2D, _small_preview: Texture2D, token) -> void:
	if _pending_resource_preview.is_empty(): return
	if token != _pending_resource_preview.token or path != _pending_resource_preview.path: return
	if Time.get_ticks_msec() >= int(_pending_resource_preview.deadline_ms): return
	if bool(_pending_resource_preview.completed): return
	_pending_resource_preview["texture"] = preview
	_pending_resource_preview.completed = true


func cancel_pending_resource_preview() -> void:
	# Godot has no dequeue API. Late callbacks are invalidated locally and may
	# not publish a response or write a file, including same-path retries.
	_resource_preview_generation += 1
	_pending_resource_preview = {}


func poll_pending_resource_preview():
	if _pending_resource_preview.is_empty(): return null
	if Time.get_ticks_msec() >= int(_pending_resource_preview.deadline_ms):
		cancel_pending_resource_preview()
		return _error("Resource preview timed out before a valid result was available")
	if not bool(_pending_resource_preview.completed): return null
	var pending := _pending_resource_preview
	_pending_resource_preview = {}
	var path: String = pending.path
	var identity := _resource_preview_identity(path)
	if identity.has("error") or identity != pending.identity:
		return _error("Resource or import metadata changed while the preview was pending")
	var texture: Texture2D = pending.get("texture")
	if texture == null: return {"path": path, "available": false, "reason": "Godot has no preview for this resource"}
	if texture.get_width() < 1 or texture.get_height() < 1 or texture.get_width() > RESOURCE_PREVIEW_MAX_DIMENSION or texture.get_height() > RESOURCE_PREVIEW_MAX_DIMENSION:
		return _error("Resource preview texture exceeds the bounded dimensions")
	var image := texture.get_image()
	if image == null or image.is_empty(): return _error("Resource preview produced no readable image")
	if image.get_width() > RESOURCE_PREVIEW_MAX_DIMENSION or image.get_height() > RESOURCE_PREVIEW_MAX_DIMENSION or image.get_data_size() > RESOURCE_PREVIEW_MAX_IMAGE_BYTES:
		return _error("Resource preview image exceeds the bounded size limit")
	if image.is_compressed() and image.decompress() != OK:
		return _error("Resource preview image could not be decompressed")
	image.convert(Image.FORMAT_RGBA8)
	if image.get_data_size() > RESOURCE_PREVIEW_MAX_IMAGE_BYTES:
		return _error("Decoded resource preview exceeds the bounded image size")
	var directory := "res://.dcc-mcp/previews"
	var output := "%s/%s.png" % [directory, path.md5_text()]
	var temporary := "%s/%s-%s.tmp.png" % [directory, path.md5_text(), pending.token]
	if not _resource_preview_safe_path(output) or not _resource_preview_safe_path(temporary):
		return _error("Resource preview output path is unsafe")
	var mkdir_error := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	if mkdir_error != OK: return _error("Unable to create resource preview directory")
	# A failed save/rename must not replace an earlier valid preview.
	if FileAccess.file_exists(temporary): return _error("Resource preview staging path is already occupied")
	var save_error := image.save_png(temporary)
	if save_error != OK:
		DirAccess.remove_absolute(temporary)
		return _error("Unable to save resource preview")
	if Time.get_ticks_msec() >= int(pending.deadline_ms) or _resource_preview_identity(path) != pending.identity or not _resource_preview_safe_path(output):
		DirAccess.remove_absolute(temporary)
		return _error("Resource preview expired or source/output changed before publication")
	var rename_error := DirAccess.rename_absolute(temporary, output)
	if rename_error != OK:
		DirAccess.remove_absolute(temporary)
		return _error("Unable to publish resource preview")
	return {"path": path, "available": true, "preview_path": output, "width": image.get_width(), "height": image.get_height()}


func _resource_preview_safe_path(path: String) -> bool:
	if not path.begins_with("res://") or path.length() > 500 or "\\" in path: return false
	var directory := DirAccess.open("res://")
	if directory == null: return false
	var current := "res://"
	for part in path.trim_prefix("res://").split("/"):
		if part.is_empty() or part in [".", ".."] or ":" in part: return false
		current = current.path_join(part)
		if directory.is_link(current): return false
	return not DirAccess.dir_exists_absolute(path)


func _resource_preview_identity(path: String) -> Dictionary:
	var stamps: Array = []
	for file_path in [path, path + ".import"]:
		if not _resource_preview_safe_path(file_path): return {"error": "Resource preview path must remain in the project without symlinks"}
		if not FileAccess.file_exists(file_path):
			if file_path == path: return {"error": "Resource preview source is missing"}
			stamps.append(null)
			continue
		var file := FileAccess.open(file_path, FileAccess.READ)
		if file == null: return {"error": "Resource preview source cannot be opened"}
		stamps.append([FileAccess.get_modified_time(file_path), file.get_length()])
	# This follows Godot's metadata-based cache semantics, not a content hash.
	# Same-second equal-length edits need explicit editor cache invalidation.
	return {"stamps": stamps}


func _add_autoload(params: Dictionary) -> Dictionary:
	var name := str(params.get("name", ""))
	var checked := _existing_path(params.get("path", ""), ["gd", "tscn"])
	if name.is_empty() or "/" in name: return _error("A valid autoload name is required")
	if checked.has("error"): return _error(checked.error)
	_plugin.add_autoload_singleton(name, checked.path)
	return {"added": true, "name": name, "path": checked.path}


func _remove_autoload(params: Dictionary) -> Dictionary:
	var name := str(params.get("name", ""))
	if name.is_empty() or not ProjectSettings.has_setting("autoload/%s" % name): return _error("Autoload not found")
	_plugin.remove_autoload_singleton(name)
	return {"removed": true, "name": name}


func _execute_authoring(action: String, params: Dictionary) -> Dictionary:
	match action:
		"list_animations": return _list_animations(params)
		"create_animation": return _create_animation(params)
		"add_animation_track": return _add_animation_track(params)
		"set_animation_keyframe": return _set_animation_keyframe(params)
		"get_animation_info": return _get_animation_info(params)
		"remove_animation": return _remove_animation(params)
		"create_animation_tree": return _create_animation_tree(params)
		"get_animation_tree_structure": return _get_animation_tree_structure(params)
		"set_tree_parameter": return _set_tree_parameter(params)
		"add_state_machine_state": return _add_state_machine_state(params)
		"remove_state_machine_state": return _remove_state_machine_state(params)
		"add_state_machine_transition": return _add_state_machine_transition(params)
		"remove_state_machine_transition": return _remove_state_machine_transition(params)
		"set_blend_tree_node": return _set_blend_tree_node(params)
		"add_mesh_instance": return _add_mesh_instance(params)
		"setup_camera_3d": return _setup_camera_3d(params)
		"setup_lighting": return _setup_lighting(params)
		"setup_environment": return _setup_environment(params)
		"add_gridmap": return _add_gridmap(params)
		"set_material_3d": return _set_material_3d(params)
		"setup_physics_body": return _configure_node(params)
		"setup_collision": return _setup_collision(params)
		"set_physics_layers": return _set_physics_layers(params)
		"get_physics_layers": return _get_physics_layers(params)
		"get_collision_info": return _get_collision_info(params)
		"add_raycast": return _add_raycast(params)
		"create_particles": return _create_particles(params)
		"set_particle_material": return _set_particle_material(params)
		"set_particle_color_gradient": return _set_particle_color_gradient(params)
		"apply_particle_preset": return _apply_particle_preset(params)
		"get_particle_info": return _get_node_properties(params)
		"setup_navigation_region", "setup_navigation_agent": return _setup_navigation_node(action, params)
		"bake_navigation_mesh": return _bake_navigation_mesh(params)
		"set_navigation_layers": return _set_navigation_layers(params)
		"get_navigation_info": return _get_node_properties(params)
		"query_navigation_path": return _query_navigation_path(params)
		"add_audio_player": return _add_audio_player(params)
		"add_audio_bus": return _add_audio_bus(params)
		"add_audio_bus_effect": return _add_audio_bus_effect(params)
		"set_audio_bus": return _set_audio_bus(params)
		"get_audio_bus_layout": return _get_audio_bus_layout()
		"get_audio_info": return _get_node_properties(params)
		"tilemap_set_cell": return _tilemap_set_cell(params)
		"tilemap_fill_rect": return _tilemap_fill_rect(params)
		"tilemap_get_cell": return _tilemap_get_cell(params)
		"tilemap_clear": return _tilemap_clear(params)
		"tilemap_get_info": return _tilemap_get_info(params)
		"tilemap_get_used_cells": return _tilemap_get_used_cells(params)
		"create_theme": return _create_theme(params)
		"set_theme_color": return _set_theme_item("color", params)
		"set_theme_constant": return _set_theme_item("constant", params)
		"set_theme_font_size": return _set_theme_item("font_size", params)
		"set_theme_stylebox": return _set_theme_item("stylebox", params)
		"get_theme_info": return _get_theme_info(params)
		"compare_screenshots": return _compare_screenshots(params)
		_:
			return _error("Runtime game peer is required for capability: %s" % action)


func _animation_player(params: Dictionary) -> AnimationPlayer:
	var node := _scene_node(str(params.get("node_path", ".")))
	return node as AnimationPlayer


func _animation(params: Dictionary) -> Animation:
	var player := _animation_player(params)
	if player == null: return null
	return player.get_animation(str(params.get("animation", "")))


func _list_animations(params: Dictionary) -> Dictionary:
	var player := _animation_player(params)
	if player == null: return _error("node_path must identify an AnimationPlayer")
	var libraries := {}
	for library_name in player.get_animation_library_list():
		var names: Array[String] = []
		for animation_name in player.get_animation_library(library_name).get_animation_list(): names.append(str(animation_name))
		libraries[str(library_name)] = names
	return {"node_path": str(player.get_path()), "libraries": libraries}


func _create_animation(params: Dictionary) -> Dictionary:
	var player := _animation_player(params)
	if player == null: return _error("node_path must identify an AnimationPlayer")
	var library_name := str(params.get("library", ""))
	if not player.has_animation_library(library_name): player.add_animation_library(library_name, AnimationLibrary.new())
	var library := player.get_animation_library(library_name)
	var name := str(params.get("animation", params.get("name", "")))
	if name.is_empty(): return _error("animation name is required")
	if library.has_animation(name) and not bool(params.get("overwrite", false)): return _error("Animation already exists")
	if library.has_animation(name): library.remove_animation(name)
	var animation := Animation.new()
	animation.length = maxf(0.001, float(params.get("length", 1.0)))
	animation.loop_mode = int(params.get("loop_mode", Animation.LOOP_NONE)) as Animation.LoopMode
	library.add_animation(name, animation)
	return {"created": true, "animation": name, "library": library_name, "length": animation.length}


func _add_animation_track(params: Dictionary) -> Dictionary:
	var animation := _animation(params)
	if animation == null: return _error("Animation not found")
	var type_names := {"value": Animation.TYPE_VALUE, "position_3d": Animation.TYPE_POSITION_3D, "rotation_3d": Animation.TYPE_ROTATION_3D, "scale_3d": Animation.TYPE_SCALE_3D, "method": Animation.TYPE_METHOD, "bezier": Animation.TYPE_BEZIER, "audio": Animation.TYPE_AUDIO, "animation": Animation.TYPE_ANIMATION}
	var type_name := str(params.get("track_type", "value"))
	if not type_names.has(type_name): return _error("Unsupported animation track type")
	var index := animation.add_track(type_names[type_name])
	animation.track_set_path(index, NodePath(str(params.get("property_path", params.get("path", "")))))
	animation.track_set_interpolation_type(index, int(params.get("interpolation", Animation.INTERPOLATION_LINEAR)) as Animation.InterpolationType)
	return {"created": true, "track": index, "track_type": type_name, "path": str(animation.track_get_path(index))}


func _set_animation_keyframe(params: Dictionary) -> Dictionary:
	var animation := _animation(params)
	if animation == null: return _error("Animation not found")
	var raw_track = params.get("track", -1)
	if not _animation_finite_number(raw_track) or float(raw_track) != floor(float(raw_track)):
		return _error("Animation track must be an integer")
	if raw_track < 0 or raw_track >= animation.get_track_count(): return _error("Invalid animation track")
	var track := int(raw_track)
	var raw_time = params.get("time", 0.0)
	var raw_transition = params.get("transition", 1.0)
	if not _animation_finite_number(raw_time) or raw_time < 0:
		return _error("Animation time must be finite and non-negative")
	if not _animation_finite_number(raw_transition) or absf(float(raw_transition)) > 3.4028234663852886e38:
		return _error("Animation transition must be a finite engine scalar")
	if not params.has("value"): return _error("Animation key value is required")
	var prepared := _animation_key_value(animation.track_get_type(track), params.value)
	if prepared.has("__error__"): return prepared
	# Conversion and resource validation finish before the only animation mutation.
	var time := float(raw_time)
	var key := animation.track_insert_key(track, time, prepared.value, float(raw_transition))
	if key < 0: return _error("Godot rejected the animation key; no successful insertion")
	return {"inserted": true, "track": track, "key": key, "time": time}


func _animation_finite_number(value) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func _animation_key_value(track_type: int, value) -> Dictionary:
	if track_type in [Animation.TYPE_POSITION_3D, Animation.TYPE_SCALE_3D, Animation.TYPE_ROTATION_3D]:
		var size := 4 if track_type == Animation.TYPE_ROTATION_3D else 3
		if not value is Array or value.size() != size:
			return _error("3D animation key requires exactly %d numeric components" % size)
		for component in value:
			if not _animation_finite_number(component): return _error("3D animation components must be finite numbers")
		if track_type == Animation.TYPE_ROTATION_3D:
			# Godot uses x, y, z, w. Do not silently normalize or interpret Euler angles.
			var rotation := Quaternion(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
			if not rotation.is_finite() or not rotation.is_normalized():
				return _error("Rotation key must be a finite unit quaternion [x, y, z, w]")
			return {"value": rotation}
		var vector := Vector3(float(value[0]), float(value[1]), float(value[2]))
		# JSON doubles can overflow the engine's real_t when converted to Vector3.
		if not vector.is_finite(): return _error("3D animation components exceed the engine scalar range")
		return {"value": vector}
	if track_type == Animation.TYPE_AUDIO:
		return _animation_audio_key(value)
	# Keep the existing value, method, bezier and animation-track payload semantics.
	return {"value": value}


func _animation_audio_key(value) -> Dictionary:
	if not value is Dictionary: return _error("Audio key requires stream_path and optional start_offset/end_offset")
	for name in value:
		if name not in ["stream_path", "start_offset", "end_offset"]: return _error("Unsupported audio key field: %s" % name)
	var path = value.get("stream_path")
	if not path is String or not UITexture._valid_resource_path(path):
		return _error("Audio stream_path must be a normalized project file below res://")
	var types := {"wav": "AudioStreamWAV", "ogg": "AudioStreamOggVorbis", "mp3": "AudioStreamMP3"}
	var extension: String = path.get_extension().to_lower()
	if not types.has(extension): return _error("Audio stream_path must end in wav, ogg or mp3")
	var directory := DirAccess.open("res://")
	if directory == null: return _error("Project directory is unavailable")
	var checked_path := "res://"
	for part in path.trim_prefix("res://").split("/"):
		checked_path = checked_path.path_join(part)
		if directory.is_link(checked_path): return _error("Audio paths cannot contain symlinks or reparse points")
	if DirAccess.dir_exists_absolute(path) or not FileAccess.file_exists(path):
		return _error("Audio source file is missing or not a regular file")
	var start = value.get("start_offset", 0.0)
	var end = value.get("end_offset", 0.0)
	for offset in [start, end]:
		if not _animation_finite_number(offset) or offset < 0 or offset > 3.4028234663852886e38:
			return _error("Audio offsets must be finite non-negative engine scalars")
	var filesystem := EditorInterface.get_resource_filesystem()
	if filesystem == null or filesystem.is_scanning(): return _error("Audio import is not ready; finish editor import first")
	var folder := filesystem.get_filesystem_path(path.get_base_dir())
	var index := folder.find_file_index(path.get_file()) if folder != null else -1
	if index < 0 or not folder.get_file_import_is_valid(index) or folder.get_file_type(index) != types[extension]:
		return _error("Audio import is not ready or has an unsupported type")
	# Never parse .import metadata or load an arbitrary resource here. Both can
	# instantiate scripted resources before a post-load type check can reject them.
	# The normal editor/scene must already hold this imported native AudioStream.
	var stream := ResourceLoader.get_cached_ref(path)
	if stream == null: return _error("Audio is not loaded; bind the imported stream to an AudioStreamPlayer first")
	if not stream is AudioStream or stream.get_class() != types[extension] or stream.get_script() != null or stream.resource_path != path:
		return _error("Audio key requires a cached native AudioStream at the exact project path")
	return {"value": {"stream": stream, "start_offset": float(start), "end_offset": float(end)}}


func _get_animation_info(params: Dictionary) -> Dictionary:
	var animation := _animation(params)
	if animation == null: return _error("Animation not found")
	var tracks: Array[Dictionary] = []
	for track in range(animation.get_track_count()):
		var keys: Array[Dictionary] = []
		for key in range(animation.track_get_key_count(track)):
			keys.append({"time": animation.track_get_key_time(track, key), "value": _json_value(animation.track_get_key_value(track, key)), "transition": animation.track_get_key_transition(track, key)})
		tracks.append({"index": track, "type": animation.track_get_type(track), "path": str(animation.track_get_path(track)), "keys": keys})
	return {"length": animation.length, "loop_mode": animation.loop_mode, "tracks": tracks}


func _remove_animation(params: Dictionary) -> Dictionary:
	var player := _animation_player(params)
	if player == null: return _error("node_path must identify an AnimationPlayer")
	var library_name := str(params.get("library", ""))
	var name := str(params.get("animation", ""))
	if not player.has_animation_library(library_name) or not player.get_animation_library(library_name).has_animation(name): return _error("Animation not found")
	player.get_animation_library(library_name).remove_animation(name)
	return {"removed": true, "animation": name}


func _create_animation_tree(params: Dictionary) -> Dictionary:
	var result := _add_node({"type": "AnimationTree", "name": params.get("name", "AnimationTree"), "parent_path": params.get("parent_path", ".")})
	if result.has("__error__"): return result
	var tree := _scene_node(result.path) as AnimationTree
	var mode := str(params.get("tree_type", "state_machine"))
	if mode == "state_machine": tree.tree_root = AnimationNodeStateMachine.new()
	elif mode == "blend_tree": tree.tree_root = AnimationNodeBlendTree.new()
	else: return _error("tree_type must be state_machine or blend_tree")
	tree.active = bool(params.get("active", true))
	return {"created": true, "path": str(tree.get_path()), "tree_type": mode}


func _animation_tree(params: Dictionary) -> AnimationTree:
	return _scene_node(str(params.get("node_path", "."))) as AnimationTree


func _get_animation_tree_structure(params: Dictionary) -> Dictionary:
	var tree := _animation_tree(params)
	if tree == null or tree.tree_root == null: return _error("AnimationTree with a tree_root is required")
	var parameters := {}
	for key in _stored_properties(tree):
		if str(key).begins_with("parameters/"): parameters[key] = _json_value(tree.get(key))
	return {"node_path": str(tree.get_path()), "active": tree.active, "tree_type": tree.tree_root.get_class(), "parameters": parameters}


func _set_tree_parameter(params: Dictionary) -> Dictionary:
	var tree := _animation_tree(params)
	if tree == null: return _error("AnimationTree not found")
	var parameter := str(params.get("parameter", ""))
	if not parameter.begins_with("parameters/"): parameter = "parameters/" + parameter
	tree.set(parameter, params.get("value"))
	return {"updated": true, "parameter": parameter, "value": _json_value(tree.get(parameter))}


func _state_machine(params: Dictionary) -> AnimationNodeStateMachine:
	var tree := _animation_tree(params)
	return tree.tree_root as AnimationNodeStateMachine if tree else null


func _add_state_machine_state(params: Dictionary) -> Dictionary:
	var machine := _state_machine(params)
	if machine == null: return _error("AnimationTree root must be AnimationNodeStateMachine")
	var name := str(params.get("state", params.get("name", "")))
	var node := AnimationNodeAnimation.new()
	node.animation = StringName(str(params.get("animation", name)))
	machine.add_node(name, node, _vector2(params.get("position", [0, 0])))
	return {"added": true, "state": name}


func _remove_state_machine_state(params: Dictionary) -> Dictionary:
	var machine := _state_machine(params)
	var name := str(params.get("state", ""))
	if machine == null or not machine.has_node(name): return _error("State not found")
	machine.remove_node(name)
	return {"removed": true, "state": name}


func _add_state_machine_transition(params: Dictionary) -> Dictionary:
	var machine := _state_machine(params)
	if machine == null: return _error("AnimationTree root must be AnimationNodeStateMachine")
	var transition := AnimationNodeStateMachineTransition.new()
	transition.xfade_time = float(params.get("xfade_time", 0.0))
	transition.advance_mode = int(params.get("advance_mode", AnimationNodeStateMachineTransition.ADVANCE_MODE_ENABLED)) as AnimationNodeStateMachineTransition.AdvanceMode
	machine.add_transition(str(params.get("from", "")), str(params.get("to", "")), transition)
	return {"added": true, "from": params.get("from", ""), "to": params.get("to", "")}


func _remove_state_machine_transition(params: Dictionary) -> Dictionary:
	var machine := _state_machine(params)
	if machine == null: return _error("AnimationTree root must be AnimationNodeStateMachine")
	machine.remove_transition(str(params.get("from", "")), str(params.get("to", "")))
	return {"removed": true, "from": params.get("from", ""), "to": params.get("to", "")}


func _set_blend_tree_node(params: Dictionary) -> Dictionary:
	var tree := _animation_tree(params)
	var blend := tree.tree_root as AnimationNodeBlendTree if tree else null
	if blend == null: return _error("AnimationTree root must be AnimationNodeBlendTree")
	var type_name := str(params.get("type", "AnimationNodeAnimation"))
	var node = ClassDB.instantiate(type_name)
	if not node is AnimationNode:
		if node != null: node.free()
		return _error("Type is not an AnimationNode")
	var name := str(params.get("name", "Node"))
	if blend.has_node(name): blend.remove_node(name)
	blend.add_node(name, node, _vector2(params.get("position", [0, 0])))
	return {"updated": true, "name": name, "type": type_name}


func _add_mesh_instance(params: Dictionary) -> Dictionary:
	var mesh_types := {"box": "BoxMesh", "sphere": "SphereMesh", "capsule": "CapsuleMesh", "cylinder": "CylinderMesh", "plane": "PlaneMesh", "quad": "QuadMesh", "prism": "PrismMesh", "torus": "TorusMesh"}
	var primitive := str(params.get("primitive", "box"))
	if not mesh_types.has(primitive): return _error("Unsupported primitive mesh")
	var node := MeshInstance3D.new()
	node.name = str(params.get("name", "Mesh"))
	node.mesh = ClassDB.instantiate(mesh_types[primitive])
	for key in (params.get("mesh_properties", {}) as Dictionary):
		if _has_property(node.mesh, str(key)): node.mesh.set(str(key), _coerce_value(node.mesh.get(str(key)), params.mesh_properties[key]))
	return _add_existing_node(node, str(params.get("parent_path", ".")))


func _setup_camera_3d(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", "")))
	if node == null:
		var added := _add_node({"type": "Camera3D", "name": params.get("name", "Camera3D"), "parent_path": params.get("parent_path", ".")})
		if added.has("__error__"): return added
		node = _scene_node(added.path)
	if not node is Camera3D: return _error("Node must be Camera3D")
	_configure_properties(node, params.get("properties", params))
	return {"configured": true, "path": str(node.get_path()), "current": node.current}


func _setup_lighting(params: Dictionary) -> Dictionary:
	var types := {"directional": "DirectionalLight3D", "omni": "OmniLight3D", "spot": "SpotLight3D"}
	var type_name := str(params.get("light_type", "directional"))
	if not types.has(type_name): return _error("light_type must be directional, omni, or spot")
	var added := _add_node({"type": types[type_name], "name": params.get("name", types[type_name]), "parent_path": params.get("parent_path", ".")})
	if added.has("__error__"): return added
	var node := _scene_node(added.path)
	_configure_properties(node, params.get("properties", params))
	return {"configured": true, "path": str(node.get_path()), "type": node.get_class()}


func _setup_environment(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", "")))
	if node == null:
		var added := _add_node({"type": "WorldEnvironment", "name": params.get("name", "WorldEnvironment"), "parent_path": params.get("parent_path", ".")})
		if added.has("__error__"): return added
		node = _scene_node(added.path)
	if not node is WorldEnvironment: return _error("Node must be WorldEnvironment")
	if node.environment == null: node.environment = Environment.new()
	_configure_properties(node.environment, params.get("properties", {}))
	return {"configured": true, "path": str(node.get_path())}


func _add_gridmap(params: Dictionary) -> Dictionary:
	return _add_node({"type": "GridMap", "name": params.get("name", "GridMap"), "parent_path": params.get("parent_path", "."), "properties": params.get("properties", {})})


func _set_material_3d(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", "."))) as GeometryInstance3D
	if node == null: return _error("Node must be GeometryInstance3D")
	var material := node.material_override as StandardMaterial3D
	if material == null: material = StandardMaterial3D.new(); node.material_override = material
	_configure_properties(material, params.get("properties", params))
	return {"updated": true, "node_path": str(node.get_path()), "properties": _stored_properties(material)}


func _configure_node(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null: return _error("Node not found")
	_configure_properties(node, params.get("properties", params))
	return {"configured": true, "path": str(node.get_path()), "type": node.get_class()}


func _setup_collision(params: Dictionary) -> Dictionary:
	var is_3d := bool(params.get("is_3d", true))
	var node: Node = CollisionShape3D.new() if is_3d else CollisionShape2D.new()
	node.name = str(params.get("name", "CollisionShape3D" if is_3d else "CollisionShape2D"))
	var shape_types := {"box": "BoxShape3D" if is_3d else "RectangleShape2D", "circle": "SphereShape3D" if is_3d else "CircleShape2D", "capsule": "CapsuleShape3D" if is_3d else "CapsuleShape2D"}
	var shape_name := str(params.get("shape", "box"))
	if not shape_types.has(shape_name): return _error("Unsupported collision shape")
	node.shape = ClassDB.instantiate(shape_types[shape_name])
	_configure_properties(node.shape, params.get("shape_properties", {}))
	return _add_existing_node(node, str(params.get("parent_path", ".")))


func _set_physics_layers(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null or not _has_property(node, "collision_layer") or not _has_property(node, "collision_mask"): return _error("Node does not expose collision layers")
	node.set("collision_layer", int(params.get("layer", node.get("collision_layer"))))
	node.set("collision_mask", int(params.get("mask", node.get("collision_mask"))))
	return _get_physics_layers(params)


func _get_physics_layers(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null or not _has_property(node, "collision_layer") or not _has_property(node, "collision_mask"): return _error("Node does not expose collision layers")
	return {"node_path": str(node.get_path()), "layer": node.get("collision_layer"), "mask": node.get("collision_mask")}


func _get_collision_info(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null: return _error("Node not found")
	var shapes: Array[Dictionary] = []
	for child in node.get_children():
		if child is CollisionShape2D or child is CollisionShape3D: shapes.append({"path": str(child.get_path()), "disabled": child.disabled, "shape_type": child.shape.get_class() if child.shape else "", "shape": _stored_properties(child.shape) if child.shape else {}})
	return {"node_path": str(node.get_path()), "shapes": shapes}


func _add_raycast(params: Dictionary) -> Dictionary:
	var is_3d := bool(params.get("is_3d", true))
	return _add_node({"type": "RayCast3D" if is_3d else "RayCast2D", "name": params.get("name", "RayCast"), "parent_path": params.get("parent_path", "."), "properties": params.get("properties", {})})


func _create_particles(params: Dictionary) -> Dictionary:
	var is_3d := bool(params.get("is_3d", false))
	return _add_node({"type": "GPUParticles3D" if is_3d else "GPUParticles2D", "name": params.get("name", "Particles"), "parent_path": params.get("parent_path", "."), "properties": params.get("properties", {})})


func _particle_node(params: Dictionary) -> Node:
	var node := _scene_node(str(params.get("node_path", ".")))
	return node if node is GPUParticles2D or node is GPUParticles3D else null


func _particle_material(params: Dictionary) -> ParticleProcessMaterial:
	var node := _particle_node(params)
	if node == null: return null
	var material := node.process_material as ParticleProcessMaterial
	if material == null: material = ParticleProcessMaterial.new(); node.process_material = material
	return material


func _set_particle_material(params: Dictionary) -> Dictionary:
	var material := _particle_material(params)
	if material == null: return _error("Node must be GPUParticles2D or GPUParticles3D")
	_configure_properties(material, params.get("properties", params))
	return {"updated": true, "properties": _stored_properties(material)}


func _set_particle_color_gradient(params: Dictionary) -> Dictionary:
	var material := _particle_material(params)
	if material == null: return _error("Particle node not found")
	var gradient := Gradient.new()
	var colors: Array = params.get("colors", ["#ffffffff", "#ffffff00"])
	var offsets: Array = params.get("offsets", [0.0, 1.0])
	if colors.size() != offsets.size() or colors.size() < 2: return _error("colors and offsets must have the same size of at least two")
	gradient.colors = PackedColorArray(colors.map(func(value): return Color.from_string(str(value), Color.WHITE)))
	gradient.offsets = PackedFloat32Array(offsets)
	var texture := GradientTexture1D.new(); texture.gradient = gradient
	material.color_ramp = texture
	return {"updated": true, "points": colors.size()}


func _apply_particle_preset(params: Dictionary) -> Dictionary:
	var presets := {
		"fire": {"direction": Vector3(0, -1, 0), "spread": 12.0, "initial_velocity_min": 60.0, "initial_velocity_max": 110.0, "gravity": Vector3(0, -20, 0)},
		"smoke": {"direction": Vector3(0, -1, 0), "spread": 25.0, "initial_velocity_min": 10.0, "initial_velocity_max": 25.0, "gravity": Vector3(0, -5, 0)},
		"sparks": {"direction": Vector3(0, -1, 0), "spread": 65.0, "initial_velocity_min": 120.0, "initial_velocity_max": 220.0, "gravity": Vector3(0, 180, 0)},
	}
	var preset := str(params.get("preset", "fire"))
	if not presets.has(preset): return _error("preset must be fire, smoke, or sparks")
	var material := _particle_material(params)
	if material == null: return _error("Particle node not found")
	_configure_properties(material, presets[preset])
	return {"applied": true, "preset": preset}


func _setup_navigation_node(action: String, params: Dictionary) -> Dictionary:
	var is_3d := bool(params.get("is_3d", true))
	var type_name := ("NavigationRegion3D" if is_3d else "NavigationRegion2D") if action == "setup_navigation_region" else ("NavigationAgent3D" if is_3d else "NavigationAgent2D")
	var node := _scene_node(str(params.get("node_path", "")))
	if node == null:
		var added := _add_node({"type": type_name, "name": params.get("name", type_name), "parent_path": params.get("parent_path", ".")})
		if added.has("__error__"): return added
		node = _scene_node(added.path)
	_configure_properties(node, params.get("properties", {}))
	return {"configured": true, "path": str(node.get_path()), "type": node.get_class()}


func _bake_navigation_mesh(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null or not node.has_method("bake_navigation_mesh") and not node.has_method("bake_navigation_polygon"): return _error("Navigation region does not support baking")
	if node.has_method("bake_navigation_mesh"): node.call("bake_navigation_mesh", false)
	else: node.call("bake_navigation_polygon", false)
	return {"baking": true, "node_path": str(node.get_path())}


func _set_navigation_layers(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node == null or not _has_property(node, "navigation_layers"): return _error("Node does not expose navigation_layers")
	node.set("navigation_layers", int(params.get("layers", 1)))
	return {"updated": true, "layers": node.get("navigation_layers")}


func _query_navigation_path(params: Dictionary) -> Dictionary:
	var node := _scene_node(str(params.get("node_path", ".")))
	if node is Node3D:
		var path := NavigationServer3D.map_get_path(node.get_world_3d().navigation_map, _vector3(params.get("from", [0, 0, 0])), _vector3(params.get("to", [0, 0, 0])), bool(params.get("optimize", true)))
		return {"path": Array(path).map(func(point): return _json_value(point)), "count": path.size()}
	if node is Node2D:
		var path := NavigationServer2D.map_get_path(node.get_world_2d().navigation_map, _vector2(params.get("from", [0, 0])), _vector2(params.get("to", [0, 0])), bool(params.get("optimize", true)))
		return {"path": Array(path).map(func(point): return _json_value(point)), "count": path.size()}
	return _error("node_path must identify a Node2D or Node3D")


func _add_audio_player(params: Dictionary) -> Dictionary:
	var kind := str(params.get("type", "AudioStreamPlayer"))
	if kind not in ["AudioStreamPlayer", "AudioStreamPlayer2D", "AudioStreamPlayer3D"]: return _error("Unsupported audio player type")
	var added := _add_node({"type": kind, "name": params.get("name", kind), "parent_path": params.get("parent_path", "."), "properties": params.get("properties", {})})
	if added.has("__error__"): return added
	if params.has("stream_path"):
		var checked := _existing_path(params.stream_path, ["wav", "ogg", "mp3"])
		if checked.has("error"): return _error(checked.error)
		_scene_node(added.path).stream = load(checked.path)
	return added


func _add_audio_bus(params: Dictionary) -> Dictionary:
	var name := str(params.get("name", ""))
	if name.is_empty(): return _error("Bus name is required")
	if AudioServer.get_bus_index(name) >= 0: return {"added": true, "already_exists": true, "name": name}
	AudioServer.add_bus(int(params.get("index", -1)))
	var index := AudioServer.bus_count - 1 if int(params.get("index", -1)) < 0 else int(params.index)
	AudioServer.set_bus_name(index, name)
	return {"added": true, "name": name, "index": index}


func _add_audio_bus_effect(params: Dictionary) -> Dictionary:
	var bus := AudioServer.get_bus_index(str(params.get("bus", "Master")))
	if bus < 0: return _error("Audio bus not found")
	var effect = ClassDB.instantiate(str(params.get("effect_type", "AudioEffectReverb")))
	if not effect is AudioEffect:
		if effect != null: effect.free()
		return _error("Type is not an AudioEffect")
	_configure_properties(effect, params.get("properties", {}))
	AudioServer.add_bus_effect(bus, effect, int(params.get("index", -1)))
	return {"added": true, "bus": AudioServer.get_bus_name(bus), "effect_type": effect.get_class()}


func _set_audio_bus(params: Dictionary) -> Dictionary:
	var bus := AudioServer.get_bus_index(str(params.get("bus", "Master")))
	if bus < 0: return _error("Audio bus not found")
	if params.has("volume_db"): AudioServer.set_bus_volume_db(bus, float(params.volume_db))
	if params.has("mute"): AudioServer.set_bus_mute(bus, bool(params.mute))
	if params.has("solo"): AudioServer.set_bus_solo(bus, bool(params.solo))
	if params.has("bypass"): AudioServer.set_bus_bypass_effects(bus, bool(params.bypass))
	return {"updated": true, "bus": AudioServer.get_bus_name(bus), "volume_db": AudioServer.get_bus_volume_db(bus), "mute": AudioServer.is_bus_mute(bus), "solo": AudioServer.is_bus_solo(bus), "bypass": AudioServer.is_bus_bypassing_effects(bus)}


func _get_audio_bus_layout() -> Dictionary:
	var buses: Array[Dictionary] = []
	for index in range(AudioServer.bus_count):
		var effects: Array[Dictionary] = []
		for effect_index in range(AudioServer.get_bus_effect_count(index)):
			var effect := AudioServer.get_bus_effect(index, effect_index)
			effects.append({"index": effect_index, "type": effect.get_class(), "enabled": AudioServer.is_bus_effect_enabled(index, effect_index)})
		buses.append({"index": index, "name": AudioServer.get_bus_name(index), "volume_db": AudioServer.get_bus_volume_db(index), "mute": AudioServer.is_bus_mute(index), "solo": AudioServer.is_bus_solo(index), "effects": effects})
	return {"buses": buses}


func _tilemap_layer(params: Dictionary) -> TileMapLayer:
	return _scene_node(str(params.get("node_path", "."))) as TileMapLayer


func _tilemap_set_cell(params: Dictionary) -> Dictionary:
	var layer := _tilemap_layer(params)
	if layer == null: return _error("node_path must identify a TileMapLayer")
	var cell := _vector2i(params.get("cell", [0, 0]))
	layer.set_cell(cell, int(params.get("source_id", -1)), _vector2i(params.get("atlas_coords", [-1, -1])), int(params.get("alternative", 0)))
	return {"updated": true, "cell": _json_value(cell)}


func _tilemap_fill_rect(params: Dictionary) -> Dictionary:
	var layer := _tilemap_layer(params)
	if layer == null: return _error("node_path must identify a TileMapLayer")
	var rect := Rect2i(_vector2i(params.get("position", [0, 0])), _vector2i(params.get("size", [1, 1])))
	for x in range(rect.position.x, rect.end.x):
		for y in range(rect.position.y, rect.end.y): layer.set_cell(Vector2i(x, y), int(params.get("source_id", -1)), _vector2i(params.get("atlas_coords", [-1, -1])), int(params.get("alternative", 0)))
	return {"updated": true, "cell_count": rect.size.x * rect.size.y}


func _tilemap_get_cell(params: Dictionary) -> Dictionary:
	var layer := _tilemap_layer(params)
	if layer == null: return _error("node_path must identify a TileMapLayer")
	var cell := _vector2i(params.get("cell", [0, 0]))
	return {"cell": _json_value(cell), "source_id": layer.get_cell_source_id(cell), "atlas_coords": _json_value(layer.get_cell_atlas_coords(cell)), "alternative": layer.get_cell_alternative_tile(cell)}


func _tilemap_clear(params: Dictionary) -> Dictionary:
	var layer := _tilemap_layer(params)
	if layer == null: return _error("node_path must identify a TileMapLayer")
	var count := layer.get_used_cells().size(); layer.clear()
	return {"cleared": true, "cell_count": count}


func _tilemap_get_info(params: Dictionary) -> Dictionary:
	var layer := _tilemap_layer(params)
	if layer == null: return _error("node_path must identify a TileMapLayer")
	var sources: Array[Dictionary] = []
	if layer.tile_set:
		for index in range(layer.tile_set.get_source_count()):
			var source_id := layer.tile_set.get_source_id(index)
			sources.append({"id": source_id, "type": layer.tile_set.get_source(source_id).get_class()})
	return {"node_path": str(layer.get_path()), "used_cells": layer.get_used_cells().size(), "tile_size": _json_value(layer.tile_set.tile_size) if layer.tile_set else null, "sources": sources}


func _tilemap_get_used_cells(params: Dictionary) -> Dictionary:
	var layer := _tilemap_layer(params)
	if layer == null: return _error("node_path must identify a TileMapLayer")
	return {"cells": Array(layer.get_used_cells()).map(func(cell): return _json_value(cell)), "count": layer.get_used_cells().size()}


func _create_theme(params: Dictionary) -> Dictionary:
	var checked := _validated_path(params.get("path", ""), ["tres", "res"])
	if checked.has("error"): return _error(checked.error)
	var theme := Theme.new()
	var save_error := ResourceSaver.save(theme, checked.path)
	if save_error != OK: return _error("Unable to save Theme: %s" % error_string(save_error))
	return {"created": true, "path": checked.path}


func _theme(params: Dictionary) -> Theme:
	var checked := _existing_path(params.get("path", ""), ["tres", "res"])
	if checked.has("error"): return null
	return load(checked.path) as Theme


func _set_theme_item(kind: String, params: Dictionary) -> Dictionary:
	var theme := _theme(params)
	if theme == null: return _error("Theme resource not found")
	var item := StringName(str(params.get("item", "")))
	var type_name := StringName(str(params.get("type", "Control")))
	match kind:
		"color": theme.set_color(item, type_name, Color.from_string(str(params.get("value", "#ffffffff")), Color.WHITE))
		"constant": theme.set_constant(item, type_name, int(params.get("value", 0)))
		"font_size": theme.set_font_size(item, type_name, int(params.get("value", 16)))
		"stylebox":
			var style := StyleBoxFlat.new()
			_configure_properties(style, params.get("properties", {}))
			theme.set_stylebox(item, type_name, style)
	var save_error := ResourceSaver.save(theme, theme.resource_path)
	if save_error != OK: return _error("Unable to save Theme")
	return {"updated": true, "kind": kind, "item": str(item), "type": str(type_name)}


func _get_theme_info(params: Dictionary) -> Dictionary:
	var theme := _theme(params)
	if theme == null: return _error("Theme resource not found")
	var type_name := StringName(str(params.get("type", "Control")))
	return {"path": theme.resource_path, "type": str(type_name), "colors": Array(theme.get_color_list(type_name)), "constants": Array(theme.get_constant_list(type_name)), "font_sizes": Array(theme.get_font_size_list(type_name)), "styleboxes": Array(theme.get_stylebox_list(type_name))}


func _compare_screenshots(params: Dictionary) -> Dictionary:
	var first_checked := _existing_path(params.get("first", ""), ["png"])
	var second_checked := _existing_path(params.get("second", ""), ["png"])
	if first_checked.has("error"): return _error(first_checked.error)
	if second_checked.has("error"): return _error(second_checked.error)
	var first := Image.load_from_file(first_checked.path)
	var second := Image.load_from_file(second_checked.path)
	if first == null or second == null or first.get_size() != second.get_size(): return {"equal": false, "reason": "Image dimensions differ or a PNG could not be loaded"}
	var step := maxi(1, int(params.get("sample_step", 1)))
	var threshold := float(params.get("threshold", 0.01))
	var different := 0; var sampled := 0; var total_delta := 0.0
	for x in range(0, first.get_width(), step):
		for y in range(0, first.get_height(), step):
			var color_a := first.get_pixel(x, y)
			var color_b := second.get_pixel(x, y)
			var delta: float = maxf(absf(color_a.r - color_b.r), maxf(absf(color_a.g - color_b.g), maxf(absf(color_a.b - color_b.b), absf(color_a.a - color_b.a))))
			total_delta += delta; sampled += 1
			if delta > threshold: different += 1
	return {"equal": different == 0, "sampled_pixels": sampled, "different_pixels": different, "mean_delta": total_delta / maxf(1.0, sampled)}


func _configure_properties(object: Object, properties) -> void:
	if not properties is Dictionary: return
	for key in properties:
		var name := str(key)
		if _has_property(object, name): object.set(name, _coerce_value(object.get(name), properties[key]))


func _vector2(value) -> Vector2:
	return Vector2(float(value[0]), float(value[1])) if value is Array and value.size() >= 2 else Vector2.ZERO


func _vector2i(value) -> Vector2i:
	return Vector2i(int(value[0]), int(value[1])) if value is Array and value.size() >= 2 else Vector2i.ZERO


func _vector3(value) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2])) if value is Array and value.size() >= 3 else Vector3.ZERO


func _read_text(params: Dictionary, extensions: Array) -> Dictionary:
	var checked := _existing_path(params.get("path", ""), extensions)
	if checked.has("error"): return _error(checked.error)
	var file := FileAccess.open(checked.path, FileAccess.READ)
	if file == null: return _error("Unable to open file")
	if file.get_length() > MAX_TEXT_BYTES: return _error("File exceeds %d bytes" % MAX_TEXT_BYTES)
	return {"path": checked.path, "content": file.get_as_text(), "bytes": file.get_length()}


func _edit_text(params: Dictionary, extensions: Array) -> Dictionary:
	var checked := _existing_path(params.get("path", ""), extensions)
	if checked.has("error"): return _error(checked.error)
	var read := _read_text({"path": checked.path}, extensions)
	if read.has("__error__"): return read
	var source := str(params.get("source", ""))
	if source.is_empty() and params.has("search"):
		var search := str(params.search)
		var replacement := str(params.get("replace", ""))
		if search.is_empty() or search not in read.content: return _error("Exact search text was not found")
		if int(read.content.count(search)) != 1 and not bool(params.get("replace_all", false)): return _error("Search text is not unique; set replace_all=true")
		source = str(read.content).replace(search, replacement)
	if source.is_empty() and not bool(params.get("allow_empty", false)): return _error("source or search/replace is required")
	return _write_text(checked.path, source)


func _write_text(path: String, source: String) -> Dictionary:
	if source.to_utf8_buffer().size() > MAX_TEXT_BYTES: return _error("Text exceeds %d bytes" % MAX_TEXT_BYTES)
	var mkdir_error := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path.get_base_dir()))
	if mkdir_error != OK: return _error("Unable to create directory: %s" % error_string(mkdir_error))
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null: return _error("Unable to open file for writing")
	file.store_string(source)
	file.close()
	EditorInterface.get_resource_filesystem().scan()
	return {"written": true, "path": path, "bytes": source.to_utf8_buffer().size()}


# Names a caller supplied that this action cannot honour. Reporting them beats
# ignoring them: a silently dropped parameter returns a plausible wrong answer.
func _unsupported_params(params: Dictionary, supported: Array) -> PackedStringArray:
	var unsupported := PackedStringArray()
	for key in params.keys():
		var name := str(key)
		if name.begins_with("_"): continue
		if not supported.has(name): unsupported.append(name)
	unsupported.sort()
	return unsupported


func _validated_path(raw_path, extensions: Array) -> Dictionary:
	var path := str(raw_path).replace("\\", "/")
	if not path.begins_with("res://") or ".." in path or path.ends_with("/"):
		return {"error": "Path must be a file below res:// without '..'"}
	if not extensions.is_empty() and path.get_extension().to_lower() not in extensions:
		return {"error": "Path extension must be one of: %s" % ", ".join(extensions)}
	return {"path": path}


func _existing_path(raw_path, extensions: Array) -> Dictionary:
	var checked := _validated_path(raw_path, extensions)
	if not checked.has("error") and not FileAccess.file_exists(checked.path): return {"error": "Project file not found: %s" % checked.path}
	return checked


func _collect_files(path: String, extensions: Array) -> Array[String]:
	var output: Array[String] = []
	_collect_files_recursive(path, extensions, output)
	return output


func _collect_files_recursive(path: String, extensions: Array, output: Array[String]) -> void:
	if output.size() >= MAX_RESULTS: return
	var directory := DirAccess.open(path)
	if directory == null: return
	directory.list_dir_begin()
	var name := directory.get_next()
	while not name.is_empty() and output.size() < MAX_RESULTS:
		if name.begins_with("."):
			name = directory.get_next(); continue
		var child := path.path_join(name)
		if directory.current_is_dir(): _collect_files_recursive(child, extensions, output)
		elif extensions.is_empty() or child.get_extension().to_lower() in extensions: output.append(child)
		name = directory.get_next()
	directory.list_dir_end()


func _scene_node(path: String) -> Node:
	var root := EditorInterface.get_edited_scene_root()
	if root == null: return null
	if path.is_empty() or path == "." or path == str(root.get_path()) or path == root.name: return root
	return root.get_node_or_null(NodePath(path))


func _node_snapshot(node: Node, depth: int, max_depth: int, fallback_path := "") -> Dictionary:
	# A node outside the scene tree has no path: get_path() returns "" and logs an
	# engine ERROR per node. A PackedScene read from disk is deliberately kept out
	# of the tree, so build its scene-relative path from the hierarchy instead.
	var node_path := str(node.get_path()) if node.is_inside_tree() else fallback_path
	var snapshot := {"name": node.name, "type": node.get_class(), "path": node_path, "script": node.get_script().resource_path if node.get_script() else "", "groups": Array(node.get_groups()), "children": []}
	if depth >= max_depth: return snapshot
	for child in node.get_children():
		# Both branches must be String: path_join() returns String while name is
		# StringName, and a mixed ternary infers Variant, which the default
		# inference_on_variant=2 setting promotes to a parse error.
		var child_path: String = (
			node_path.path_join(child.name) if not node_path.is_empty() else String(child.name)
		)
		snapshot.children.append(_node_snapshot(child, depth + 1, max_depth, child_path))
	return snapshot


func _has_property(object: Object, property_name: String) -> bool:
	for item in object.get_property_list():
		if str(item.get("name", "")) == property_name: return true
	return false


func _stored_properties(object: Object) -> Dictionary:
	var properties := {}
	for item in object.get_property_list():
		if int(item.get("usage", 0)) & PROPERTY_USAGE_STORAGE: properties[str(item.name)] = _json_value(object.get(str(item.name)))
	return properties


func _coerce_value(previous, value):
	if previous is Vector2 and value is Array and value.size() >= 2: return Vector2(float(value[0]), float(value[1]))
	if previous is Vector2i and value is Array and value.size() >= 2: return Vector2i(int(value[0]), int(value[1]))
	if previous is Vector3 and value is Array and value.size() >= 3: return Vector3(float(value[0]), float(value[1]), float(value[2]))
	if previous is Vector3i and value is Array and value.size() >= 3: return Vector3i(int(value[0]), int(value[1]), int(value[2]))
	if previous is Color and value is String: return Color.from_string(value, previous)
	if previous is StringName: return StringName(str(value))
	if previous is NodePath: return NodePath(str(value))
	return value


func _json_value(value):
	if value == null or value is bool or value is int or value is float or value is String: return value
	if value is StringName or value is NodePath: return str(value)
	if value is Vector2 or value is Vector2i: return [value.x, value.y]
	if value is Vector3 or value is Vector3i: return [value.x, value.y, value.z]
	if value is Vector4 or value is Vector4i or value is Quaternion: return [value.x, value.y, value.z, value.w]
	if value is Color: return [value.r, value.g, value.b, value.a]
	# PackedStringArray is not an Array, so without this branch it reaches
	# str(value) and reaches callers as the string "[\"a\", \"b\"]". Project
	# settings typed as PackedStringArray (application/config/features,
	# editor_plugins/enabled) are read through this function.
	if value is PackedStringArray:
		var packed_strings: Array = []
		for item in value: packed_strings.append(item)
		return packed_strings
	if value is Rect2 or value is Rect2i: return {"position": _json_value(value.position), "size": _json_value(value.size)}
	if value is Transform2D or value is Transform3D or value is Basis or value is Projection: return str(value)
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


func _string_array(value) -> Array[String]:
	var output: Array[String] = []
	if value is Array or value is PackedStringArray:
		for item in value: output.append(str(item).trim_prefix("."))
	elif not str(value).is_empty(): output.append(str(value).trim_prefix("."))
	return output


func _collect_matching_nodes(node: Node, predicate: Callable, output: Array[String]) -> void:
	if predicate.call(node): output.append(str(node.get_path()))
	for child in node.get_children(): _collect_matching_nodes(child, predicate, output)


func _collect_connections(node: Node, output: Array[Dictionary]) -> void:
	for signal_info in node.get_signal_list():
		for item in node.get_signal_connection_list(str(signal_info.name)):
			var callable: Callable = item.callable
			output.append({"source": str(node.get_path()), "signal": signal_info.name, "target": str(callable.get_object().get_path()) if callable.get_object() is Node else str(callable.get_object()), "method": callable.get_method()})
	for child in node.get_children(): _collect_connections(child, output)


func _set_property_recursive(node: Node, type_name: String, property_name: String, value) -> int:
	var count := 0
	if node.is_class(type_name) and _has_property(node, property_name):
		node.set(property_name, _coerce_value(node.get(property_name), value)); count += 1
	for child in node.get_children(): count += _set_property_recursive(child, type_name, property_name, value)
	return count


func _find_cycles(start: String, current: String, graph: Dictionary, stack: Array, cycles: Array[Array]) -> void:
	if current in stack:
		if current == start:
			var cycle := stack.duplicate(); cycle.append(current)
			if cycle not in cycles: cycles.append(cycle)
		return
	if not graph.has(current): return
	var next_stack := stack.duplicate(); next_stack.append(current)
	for dependency in graph[current]:
		var dep := str(dependency).get_slice("::", 2)
		_find_cycles(start, dep, graph, next_stack, cycles)


func _accumulate_complexity(node: Node, stats: Dictionary) -> void:
	stats.nodes += 1
	if node.get_script() != null: stats.scripts += 1
	if node is CollisionObject2D or node is CollisionObject3D: stats.physics_nodes += 1
	if node is Light3D or node is Light2D: stats.lights += 1
	if node is GPUParticles2D or node is GPUParticles3D: stats.particles += 1
	if node is Control: stats.controls += 1
	for child in node.get_children(): _accumulate_complexity(child, stats)


func _error(message: String) -> Dictionary:
	_messages.append({"time": Time.get_datetime_string_from_system(), "level": "error", "message": message})
	if _messages.size() > 200: _messages.pop_front()
	return {"__error__": message}


func _main_thread_budget_ms(params: Dictionary) -> int:
	return clampi(
		int(params.get("budget_ms", DEFAULT_MAIN_THREAD_BUDGET_MS)),
		1,
		MAX_MAIN_THREAD_BUDGET_MS,
	)
