@tool
extends RefCounted

# File preflight runs in Python. Recheck bounded native files and their digest
# immediately before loading, and again before the scene mutation.
const MAX_PNG_BYTES := 16777216
const MAX_IMPORT_BYTES := 33554432
const MAX_METADATA_BYTES := 65536
const MAX_DIMENSION := 4096
const MAX_PIXELS := 4194304


static func assign_texture(plugin: EditorPlugin, params: Dictionary) -> Dictionary:
	var node_path = params.get("node_path")
	var texture_path = params.get("texture_path")
	var proof = params.get("_validated_texture")
	if not node_path is String or not texture_path is String or not proof is Dictionary:
		return _failure("rejected", "Validated PNG request is required")
	if not _valid_node_path(node_path) or not _valid_resource_path(texture_path) or not texture_path.ends_with(".png"):
		return _failure("rejected", "Expected a relative node path and a project PNG")
	var project_path := ProjectSettings.globalize_path("res://").simplify_path().trim_suffix("/")
	var proof_project_path := str(proof.get("project_path", "")).replace("\\", "/")
	if OS.get_name() == "Windows":
		project_path = project_path.to_lower()
		proof_project_path = proof_project_path.to_lower()
	if proof_project_path != project_path:
		return _failure("rejected", "Editor project changed during validation")
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _failure("rejected", "Open an edited scene first")
	var node := root.get_node_or_null(NodePath(node_path))
	if node == null or (node != root and not root.is_ancestor_of(node)):
		return _failure("rejected", "Node is outside the edited scene or missing")
	var property_name := ""
	if node.get_class() == "TextureRect":
		property_name = "texture"
	elif node.get_class() == "Button":
		property_name = "icon"
	else:
		return _failure("rejected", "Only native TextureRect and Button nodes are supported")
	if node.get_script() != null:
		return _failure("rejected", "Scripted target nodes are not supported")
	var width := _bounded_dimension(proof.get("width", 0))
	var height := _bounded_dimension(proof.get("height", 0))
	if width < 1 or height < 1 or width > MAX_DIMENSION or height > MAX_DIMENSION or width * height > MAX_PIXELS:
		return _failure("rejected", "PNG dimensions exceed the documented bounds")
	var imported_path := str(proof.get("imported_path", ""))
	var expected_import := "res://.godot/imported/%s-%s.ctex" % [texture_path.get_file(), texture_path.md5_text()]
	if imported_path != expected_import:
		return _failure("rejected", "Unexpected texture import path")
	var files = proof.get("files")
	var expected_paths := [texture_path, texture_path + ".import", imported_path.trim_suffix(".ctex") + ".md5", imported_path]
	if not files is Array or files.size() != expected_paths.size():
		return _failure("rejected", "Import file validation is incomplete")
	var source_image := Image.new()
	for index in range(files.size()):
		var checked := _read_checked(files[index], expected_paths[index], _file_limit(index))
		if checked.has("error"):
			return _failure("import_pending", checked.error)
		if index == 0:
			var bytes: PackedByteArray = checked.bytes
			if bytes.size() < 33 or bytes.slice(0, 8) != PackedByteArray([137, 80, 78, 71, 13, 10, 26, 10]):
				return _failure("rejected", "Invalid PNG signature")
			if _u32be(bytes, 16) != width or _u32be(bytes, 20) != height:
				return _failure("rejected", "PNG header dimensions changed")
			if source_image.load_png_from_buffer(bytes) != OK or source_image.is_empty():
				return _failure("rejected", "PNG decode failed")
			if source_image.get_width() != width or source_image.get_height() != height:
				return _failure("rejected", "PNG decoded dimensions changed")
		elif index == 3:
			var bytes: PackedByteArray = checked.bytes
			if not _valid_ctex(bytes, width, height):
				return _failure("rejected", "Invalid or unsupported imported texture")
	if EditorInterface.get_resource_filesystem().is_scanning():
		return _failure("import_pending", "Editor import or scan is still in progress; retry after completion")
	# Direct native image loader: no ResourceLoader.load(), scripts, scenes or
	# generic resource deserialization. The path came from validated PNG import.
	var candidate := CompressedTexture2D.new()
	if candidate.load(imported_path) != OK or not _valid_texture(candidate, width, height):
		return _failure("import_failed", "Native imported Texture2D load failed")
	var imported_image := candidate.get_image()
	if imported_image == null or imported_image.is_empty():
		return _failure("import_failed", "Native texture pixel readback failed")
	var imported_digest := _image_digest(imported_image)
	if imported_digest.is_empty():
		return _failure("import_failed", "Native texture pixel readback is unsupported")
	var source_digest := _image_digest(source_image)
	# Reuse a current native cache entry, preserving all existing scene references.
	# Never take_over_path: that strips the old resource's path and breaks saving.
	var cached := ResourceLoader.get_cached_ref(texture_path)
	var texture: Texture2D = candidate
	if cached != null:
		var cached_texture := cached as CompressedTexture2D
		if cached_texture == null or cached_texture.get_script() != null or not _valid_texture(cached_texture, width, height):
			return _failure("import_pending", "Cached texture is incompatible; refresh the editor import and retry")
		if cached_texture.resource_path != texture_path or _image_digest(cached_texture.get_image()) != imported_digest:
			return _failure("import_pending", "Cached pixels are stale; refresh the editor import and retry")
		texture = cached_texture
	else:
		candidate.resource_path = texture_path
		if candidate.resource_path != texture_path:
			return _failure("import_failed", "Unable to retain the imported PNG resource path")
	for index in range(files.size()):
		var checked := _read_checked(files[index], expected_paths[index], _file_limit(index))
		if checked.has("error"):
			return _failure("import_pending", "Import changed during native load; retry after import completes")
	if EditorInterface.get_edited_scene_root() != root or not is_instance_valid(node) or node.get_script() != null:
		return _failure("rejected", "Edited scene or target changed during validation")
	var previous = node.get(property_name)
	var result := {
		"assigned": true, "status": "assigned", "changed": previous != texture,
		"node_path": str(root.get_path_to(node)), "node_type": node.get_class(),
		"property": property_name, "resource_type": texture.get_class(),
		"resource_path": texture.resource_path, "resource_instance_id": str(texture.get_instance_id()),
		"width": width, "height": height,
		"source_sha256": str(proof.get("source_sha256", "")),
		"native_rgba8_sha256": imported_digest,
		"source_native_rgba8_matches_import": source_digest == imported_digest,
		"undo_registered": false,
	}
	if previous == texture:
		result.status = "unchanged"
		return result
	# Verify assignment before publishing an undo action. Failed readback restores
	# the exact previous reference and does not add a false success to history.
	node.set(property_name, texture)
	if not is_instance_valid(node):
		var failed := _failure("assignment_failed", "Target was removed during assignment")
		failed["rollback_verified"] = false
		return failed
	if node.get(property_name) != texture or texture.resource_path != texture_path or not _valid_texture(texture, width, height):
		node.set(property_name, previous)
		var failed := _failure("assignment_failed", "Texture assignment readback failed")
		failed["rollback_verified"] = node.get(property_name) == previous
		return failed
	var undo := plugin.get_undo_redo()
	undo.create_action("DCC-MCP: Assign UI texture", UndoRedo.MERGE_DISABLE, node)
	undo.add_do_property(node, property_name, texture)
	undo.add_undo_property(node, property_name, previous)
	# Already applied and checked above; commit without performing it a second time.
	undo.commit_action(false)
	result.undo_registered = true
	return result


static func _bounded_dimension(value) -> int:
	if typeof(value) not in [TYPE_INT, TYPE_FLOAT]: return 0
	var number := float(value)
	if not is_finite(number) or number != floor(number) or number < 1 or number > MAX_DIMENSION: return 0
	return int(number)


static func _valid_texture(texture: Texture2D, width: int, height: int) -> bool:
	return texture != null and texture.get_width() == width and texture.get_height() == height


static func _image_digest(image: Image) -> String:
	if image == null or image.is_empty(): return ""
	var copy := image.duplicate() as Image
	if copy.is_compressed() and copy.decompress() != OK: return ""
	copy.convert(Image.FORMAT_RGBA8)
	return _sha256(copy.get_data())


static func _sha256(bytes: PackedByteArray) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(bytes)
	return context.finish().hex_encode()


static func _u32be(bytes: PackedByteArray, offset: int) -> int:
	return (int(bytes[offset]) << 24) | (int(bytes[offset + 1]) << 16) | (int(bytes[offset + 2]) << 8) | int(bytes[offset + 3])


static func _valid_ctex(bytes: PackedByteArray, width: int, height: int) -> bool:
	if bytes.size() < 56 or bytes.slice(0, 4).get_string_from_ascii() != "GST2": return false
	if bytes.decode_u32(4) != 1 or bytes.decode_u32(8) != width or bytes.decode_u32(12) != height: return false
	if bytes.decode_u32(36) not in [1, 2] or bytes.decode_u16(40) != width or bytes.decode_u16(42) != height: return false
	if bytes.decode_u32(44) != 0 or bytes.decode_u32(48) > 5 or bytes.decode_u32(52) != bytes.size() - 56: return false
	# Check the embedded image header before either native image decoder allocates.
	var payload := bytes.slice(56)
	if bytes.decode_u32(36) == 1:
		if payload.size() < 33 or payload.slice(0, 8) != PackedByteArray([137, 80, 78, 71, 13, 10, 26, 10]): return false
		if _u32be(payload, 8) != 13 or payload.slice(12, 16).get_string_from_ascii() != "IHDR": return false
		if _u32be(payload, 16) != width or _u32be(payload, 20) != height: return false
	else:
		if payload.size() < 25 or payload.slice(0, 4).get_string_from_ascii() != "RIFF" or payload.slice(8, 16).get_string_from_ascii() != "WEBPVP8L": return false
		if payload.decode_u32(4) != payload.size() - 8 or payload[20] != 0x2f: return false
		var chunk_size := payload.decode_u32(16)
		var bits := payload.decode_u32(21)
		if chunk_size < 5 or 20 + chunk_size + (chunk_size & 1) != payload.size() or (bits >> 29) != 0: return false
		if (bits & 0x3fff) + 1 != width or ((bits >> 14) & 0x3fff) + 1 != height: return false
	var image := Image.new()
	var error := image.load_png_from_buffer(bytes.slice(56)) if bytes.decode_u32(36) == 1 else image.load_webp_from_buffer(bytes.slice(56))
	return error == OK and image.get_width() == width and image.get_height() == height


static func _file_limit(index: int) -> int:
	if index == 0: return MAX_PNG_BYTES
	if index == 3: return MAX_IMPORT_BYTES
	return MAX_METADATA_BYTES


static func _read_checked(proof, expected_path: String, limit: int) -> Dictionary:
	if not proof is Dictionary or proof.get("path", "") != expected_path or not _valid_resource_path(expected_path):
		return {"error": "Invalid import file validation"}
	var directory := DirAccess.open("res://")
	if directory == null: return {"error": "Project directory is unavailable"}
	var path := "res://"
	var parts := expected_path.trim_prefix("res://").split("/")
	for index in range(parts.size()):
		path = path.path_join(parts[index])
		if directory.is_link(path): return {"error": "Symlinks and reparse points are not supported"}
		if index < parts.size() - 1 and not DirAccess.dir_exists_absolute(path):
			return {"error": "Project directory is unavailable"}
	if DirAccess.dir_exists_absolute(path) or not FileAccess.file_exists(path):
		return {"error": "Imported file is missing or not a regular file"}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null: return {"error": "Imported file could not be opened"}
	var size := file.get_length()
	if size < 1 or size > limit or size != int(proof.get("size", -1)):
		return {"error": "Imported file size changed or exceeded its limit"}
	var bytes := file.get_buffer(size)
	file.close()
	if bytes.size() != size or _sha256(bytes) != proof.get("sha256", ""):
		return {"error": "Imported file content changed; finish import and retry"}
	return {"bytes": bytes}


static func _valid_resource_path(path: String) -> bool:
	if path.length() < 7 or path.length() > 500 or not path.begins_with("res://"): return false
	var relative := path.trim_prefix("res://")
	if ":" in relative or "\\" in relative: return false
	for character in relative:
		if character.unicode_at(0) < 32: return false
	for part in relative.split("/"):
		if part in ["", ".", ".."]: return false
	return true


static func _valid_node_path(path: String) -> bool:
	if path == ".": return true
	if path.length() < 1 or path.length() > 500 or path.begins_with("/") or path.begins_with("%") or ":" in path or "\\" in path: return false
	for character in path:
		if character.unicode_at(0) < 32: return false
	for part in path.split("/"):
		if part in ["", ".", ".."] or part.begins_with("%"): return false
	return true


static func _failure(status: String, message: String) -> Dictionary:
	return {"assigned": false, "status": status, "reason": message}
