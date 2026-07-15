@tool
extends RefCounted

const TEMPLATE_ROOT := "res://addons/dcc_mcp_godot/templates/roguelike"
const ROGUELIKE_ROOT := "res://roguelike"
const Capabilities = preload("res://addons/dcc_mcp_godot/capabilities.gd")

var _plugin: EditorPlugin
var _capabilities


func _init(plugin: EditorPlugin) -> void:
	_plugin = plugin
	_capabilities = Capabilities.new(plugin)


func execute(method: String, params: Dictionary) -> Dictionary:
	match method:
		"project.inspect":
			return _inspect_project()
		"project.write_script":
			return _write_script(params)
		"assets.refresh":
			return _refresh_assets()
		"assets.set_plugin_enabled":
			return _set_plugin_enabled(params)
		"scene.inspect":
			return _inspect_scene()
		"scene.create_node":
			return _create_node(params)
		"scene.set_property":
			return _set_property(params)
		"scene.save":
			return _save_scene()
		"roguelike.create_prototype":
			return _create_roguelike(params)
		"roguelike.validate_prototype":
			return _validate_roguelike()
		_:
			if method.begins_with("capability."):
				return _capabilities.execute(method.trim_prefix("capability."), params)
			return _error("Unknown Godot action: %s" % method)


func _inspect_project() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	return {
		"name": ProjectSettings.get_setting("application/config/name", "Unnamed Project"),
		"project_path": ProjectSettings.globalize_path("res://"),
		"engine_version": Engine.get_version_info().get("string", "unknown"),
		"current_scene": root.scene_file_path if root else "",
		"main_scene": ProjectSettings.get_setting("application/run/main_scene", ""),
	}


func _write_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", ""))
	var source := str(params.get("source", ""))
	var overwrite := bool(params.get("overwrite", false))
	if not path.begins_with("res://") or not path.ends_with(".gd") or ".." in path:
		return _error("Script path must be a .gd file below res://")
	if source.length() > 100000:
		return _error("Script source exceeds 100000 characters")
	if FileAccess.file_exists(path) and not overwrite:
		return _error("Script already exists; set overwrite=true to replace it")
	var absolute_dir := ProjectSettings.globalize_path(path.get_base_dir())
	var mkdir_error := DirAccess.make_dir_recursive_absolute(absolute_dir)
	if mkdir_error != OK:
		return _error("Unable to create script directory: %s" % error_string(mkdir_error))
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return _error("Unable to open script for writing")
	file.store_string(source)
	file.close()
	EditorInterface.get_resource_filesystem().scan()
	return {"path": path, "bytes": source.to_utf8_buffer().size(), "written": true}


func _refresh_assets() -> Dictionary:
	EditorInterface.get_resource_filesystem().scan()
	return {"refreshed": true}


func _set_plugin_enabled(params: Dictionary) -> Dictionary:
	var plugin_name := str(params.get("plugin_name", ""))
	var enabled := bool(params.get("enabled", false))
	if plugin_name.is_empty() or plugin_name.begins_with("/") or ".." in plugin_name:
		return _error("Plugin name must be a relative directory below res://addons")
	var plugin_config := "res://addons/%s/plugin.cfg" % plugin_name
	if not FileAccess.file_exists(plugin_config):
		return _error("Godot plugin configuration not found: %s" % plugin_config)
	var before := EditorInterface.is_plugin_enabled(plugin_name)
	if before != enabled:
		EditorInterface.set_plugin_enabled(plugin_name, enabled)
	var after := EditorInterface.is_plugin_enabled(plugin_name)
	if after != enabled:
		return _error("Godot did not apply the requested plugin state")
	return {"plugin_name": plugin_name, "before": before, "enabled": after}


func _inspect_scene() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _error("No scene is open")
	return {"scene_path": root.scene_file_path, "root": _node_snapshot(root, 0)}


func _node_snapshot(node: Node, depth: int) -> Dictionary:
	var snapshot := {
		"name": node.name,
		"type": node.get_class(),
		"path": str(node.get_path()),
		"children": [],
	}
	if depth >= 8:
		return snapshot
	for child in node.get_children():
		snapshot["children"].append(_node_snapshot(child, depth + 1))
	return snapshot


func _create_node(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _error("Open or create a scene before adding nodes")
	var type_name := str(params.get("type", "Node2D"))
	var node = ClassDB.instantiate(type_name)
	if not node is Node:
		if node != null:
			node.free()
		return _error("Type is not a Godot Node: %s" % type_name)
	var parent: Node = root
	var parent_path := str(params.get("parent_path", ""))
	if not parent_path.is_empty():
		parent = root.get_node_or_null(NodePath(parent_path))
		if parent == null:
			node.free()
			return _error("Parent node not found: %s" % parent_path)
	node.name = str(params.get("name", type_name))
	var undo := _plugin.get_undo_redo()
	undo.create_action("DCC-MCP: Create %s" % node.name)
	undo.add_do_method(parent, "add_child", node)
	undo.add_do_property(node, "owner", root)
	undo.add_undo_method(parent, "remove_child", node)
	undo.add_do_reference(node)
	undo.commit_action()
	return {"created": true, "name": node.name, "type": node.get_class(), "path": str(node.get_path())}


func _set_property(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _error("No scene is open")
	var node_path := str(params.get("node_path", "."))
	var node := root if node_path == "." else root.get_node_or_null(NodePath(node_path))
	if node == null:
		return _error("Node not found: %s" % node_path)
	var property_name := str(params.get("property", ""))
	if not _has_property(node, property_name):
		return _error("Property not found on node: %s" % property_name)
	var previous = node.get(property_name)
	var value = params.get("value")
	var undo := _plugin.get_undo_redo()
	undo.create_action("DCC-MCP: Set %s" % property_name)
	undo.add_do_property(node, property_name, value)
	undo.add_undo_property(node, property_name, previous)
	undo.commit_action()
	return {"updated": true, "node_path": node_path, "property": property_name, "value": value}


func _has_property(node: Object, property_name: String) -> bool:
	for item in node.get_property_list():
		if item.get("name") == property_name:
			return true
	return false


func _save_scene() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _error("No scene is open")
	var error := EditorInterface.save_scene()
	if error != OK:
		return _error("Unable to save scene: %s" % error_string(error))
	return {"saved": true, "scene_path": root.scene_file_path}


func _create_roguelike(params: Dictionary) -> Dictionary:
	var title := str(params.get("title", "DCC-MCP Roguelike"))
	var mkdir_error := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(ROGUELIKE_ROOT))
	if mkdir_error != OK:
		return _error("Unable to create roguelike directory: %s" % error_string(mkdir_error))
	for filename in ["main.tscn", "game.gd", "ci_smoke.gd"]:
		var source_path := "%s/%s" % [TEMPLATE_ROOT, filename]
		var target_path := "%s/%s" % [ROGUELIKE_ROOT, filename]
		var copy_error := DirAccess.copy_absolute(
			ProjectSettings.globalize_path(source_path),
			ProjectSettings.globalize_path(target_path),
		)
		if copy_error != OK:
			return _error("Unable to install %s: %s" % [filename, error_string(copy_error)])
	ProjectSettings.set_setting("application/config/name", title)
	ProjectSettings.set_setting("application/run/main_scene", "%s/main.tscn" % ROGUELIKE_ROOT)
	ProjectSettings.save()
	EditorInterface.get_resource_filesystem().scan()
	return {
		"created": true,
		"title": title,
		"main_scene": "%s/main.tscn" % ROGUELIKE_ROOT,
		"script": "%s/game.gd" % ROGUELIKE_ROOT,
		"features": ["movement", "enemy_spawning", "auto_attack", "experience", "leveling", "game_over"],
	}


func _validate_roguelike() -> Dictionary:
	var required := ["main.tscn", "game.gd", "ci_smoke.gd"]
	var missing: Array[String] = []
	for filename in required:
		if not FileAccess.file_exists("%s/%s" % [ROGUELIKE_ROOT, filename]):
			missing.append(filename)
	if not missing.is_empty():
		return _error("Missing roguelike files: %s" % ", ".join(missing))
	var scene = load("%s/main.tscn" % ROGUELIKE_ROOT)
	if scene == null:
		return _error("Roguelike main scene could not be loaded")
	var instance = scene.instantiate()
	var valid: bool = instance.has_method("get_game_state") and instance.has_method("simulate_step")
	instance.free()
	if not valid:
		return _error("Roguelike scene is missing its gameplay contract")
	return {"valid": true, "main_scene": "%s/main.tscn" % ROGUELIKE_ROOT, "files": required}


func _error(message: String) -> Dictionary:
	return {"__error__": message}
