@tool
extends RefCounted

const MAX_TEXT_BYTES := 1000000
const MAX_RESULTS := 500
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
		"get_scene_tree": return _get_scene_tree()
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
		"execute_editor_script": return _execute_editor_script(params)
		"clear_output": _messages.clear(); return {"cleared": true}
		"get_signals": return _get_signals(params)
		"reload_plugin": return _reload_plugin()
		"reload_project": return _reload_project()
		"get_input_actions": return _get_input_actions()
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


func _get_scene_tree() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _error("No scene is open")
	return {"scene_path": root.scene_file_path, "root": _node_snapshot(root, 0, 16)}


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


func _add_existing_node(node: Node, parent_path: String) -> Dictionary:
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
	var source := str(params.get("source", ""))
	var path := str(params.get("path", ""))
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
	var viewport: SubViewport = EditorInterface.get_editor_viewport_3d(int(params.get("viewport", 0))) if str(params.get("mode", "3d")) == "3d" else EditorInterface.get_editor_viewport_2d()
	if viewport == null: return _error("Editor viewport is unavailable")
	var image := viewport.get_texture().get_image()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(checked.path.get_base_dir()))
	var save_error := image.save_png(checked.path)
	if save_error != OK: return _error("Unable to save screenshot: %s" % error_string(save_error))
	return {"path": checked.path, "width": image.get_width(), "height": image.get_height()}


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


func _get_input_actions() -> Dictionary:
	var actions: Array[Dictionary] = []
	for action in InputMap.get_actions():
		if str(action).begins_with("ui_"): continue
		actions.append({"name": str(action), "deadzone": InputMap.action_get_deadzone(action), "events": InputMap.action_get_events(action).map(func(event): return event.as_text())})
	return {"actions": actions}


func _set_input_action(params: Dictionary) -> Dictionary:
	var action := str(params.get("action", ""))
	if action.is_empty(): return _error("action is required")
	if not InputMap.has_action(action): InputMap.add_action(action, float(params.get("deadzone", 0.5)))
	else: InputMap.action_set_deadzone(action, float(params.get("deadzone", InputMap.action_get_deadzone(action))))
	if bool(params.get("replace_events", false)): InputMap.action_erase_events(action)
	if params.has("keycode"):
		var event := InputEventKey.new()
		event.keycode = int(params.keycode)
		InputMap.action_add_event(action, event)
	ProjectSettings.save()
	return {"updated": true, "action": action, "deadzone": InputMap.action_get_deadzone(action)}


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


func _get_export_info() -> Dictionary:
	var presets := _list_export_presets()
	return {"project": ProjectSettings.get_setting("application/config/name", ""), "version": ProjectSettings.get_setting("application/config/version", ""), "presets": presets.presets, "executable": OS.get_executable_path()}


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
	if material == null: return _error("Node has no ShaderMaterial")
	var parameter := str(params.get("parameter", ""))
	material.set_shader_parameter(parameter, params.get("value"))
	return {"updated": true, "parameter": parameter, "value": _json_value(material.get_shader_parameter(parameter))}


func _get_shader_params(params: Dictionary) -> Dictionary:
	var material = _shader_material(params)
	if material == null or material.shader == null: return _error("Node has no ShaderMaterial")
	var values := {}
	for item in material.shader.get_shader_uniform_list(): values[str(item.name)] = _json_value(material.get_shader_parameter(str(item.name)))
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
	var cache_dir := "res://.dcc-mcp/previews"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(cache_dir))
	var output := "%s/%s.png" % [cache_dir, checked.path.md5_text()]
	var texture: Texture2D = EditorInterface.get_resource_previewer().get_resource_preview(checked.path)
	if texture == null: return {"path": checked.path, "available": false}
	var image: Image = texture.get_image()
	var save_error = image.save_png(output)
	if save_error != OK: return _error("Unable to save preview")
	return {"path": checked.path, "available": true, "preview_path": output}


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
	var track := int(params.get("track", -1))
	if track < 0 or track >= animation.get_track_count(): return _error("Invalid animation track")
	var time := float(params.get("time", 0.0))
	var key := animation.track_insert_key(track, time, params.get("value"), float(params.get("transition", 1.0)))
	return {"inserted": true, "track": track, "key": key, "time": time}


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


func _node_snapshot(node: Node, depth: int, max_depth: int) -> Dictionary:
	var snapshot := {"name": node.name, "type": node.get_class(), "path": str(node.get_path()), "script": node.get_script().resource_path if node.get_script() else "", "groups": Array(node.get_groups()), "children": []}
	if depth >= max_depth: return snapshot
	for child in node.get_children(): snapshot.children.append(_node_snapshot(child, depth + 1, max_depth))
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
