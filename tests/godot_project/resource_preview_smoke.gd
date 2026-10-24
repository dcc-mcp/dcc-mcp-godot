@tool
extends EditorPlugin

const Capabilities = preload("res://addons/dcc_mcp_godot/capabilities.gd")
# Deliberate test seams for request routing, not a real WebSocket/MCP peer.
class BridgeProbe extends "res://addons/dcc_mcp_godot/plugin.gd":
	var sent: Array = []
	func _send_json(value: Dictionary) -> void:
		sent.append(value)
	func _write_bootstrap_status(_status: String, _reason: String = "") -> void:
		pass

class CommandsProbe extends RefCounted:
	var capability
	func capabilities():
		return capability
	func execute(_method: String, _params: Dictionary) -> Dictionary:
		return {"__deferred_resource_preview__": true}

var cap
var checks := 0
var failures: Array[String] = []
var serial := 10
var started := 0
var callback_image_measured := false
var windowed_preview_measured := false
var timeout_error := ""

func _enter_tree() -> void:
	started = Time.get_ticks_msec()
	set_process(true)
	_run.call_deferred()

func _process(_delta: float) -> void:
	if Time.get_ticks_msec() - started > 30000:
		failures.append("native fixture timed out")
		_finish()

func _check(value: bool, label: String) -> void:
	checks += 1
	if not value: failures.append(label)

func _begin(path: String = "res://texture.png") -> int:
	serial += 1
	cap._pending_resource_preview = {"token": serial, "path": path,
		"identity": cap._resource_preview_identity(path), "completed": false,
		"deadline_ms": Time.get_ticks_msec() + 10000}
	return serial

func _run() -> void:
	if EditorInterface.get_resource_filesystem().is_scanning():
		get_tree().create_timer(0.1).timeout.connect(_run)
		return
	cap = Capabilities.new(self)
	_check(not EditorInterface.get_resource_previewer().has_method("get_resource_preview"), "baseline API fact")
	var actual: Dictionary = cap.execute("get_resource_preview", {"path": "res://texture.png"})
	if DisplayServer.get_name() == "headless":
		_check(actual.get("available") == false and actual.has("reason"), "real headless request unavailable")
		_check(not actual.has("preview_path"), "headless has no stale path")
		_check(cap._pending_resource_preview.is_empty(), "headless never queues")
		_check(not DirAccess.dir_exists_absolute("res://.dcc-mcp"), "headless has no write side effects")
	else:
		_check(actual.has("__deferred_resource_preview__"), "real windowed request defers")
		_check(cap.execute("get_resource_preview", {"path": "res://texture.png"}).has("__error__"), "same-path overlap is busy")
		var terminal: Variant = null
		while terminal == null:
			await get_tree().process_frame
			terminal = cap.poll_pending_resource_preview()
		_check(terminal.get("available") == true, "real preview worker produces an image")
		if terminal.get("available") == true:
			var native_image := Image.load_from_file(terminal.preview_path)
			_check(native_image != null and not native_image.is_empty(), "real preview worker PNG readable")
			if native_image != null and not native_image.is_empty():
				_check(native_image.get_width() == terminal.width and native_image.get_height() == terminal.height, "real worker dimensions match receipt")
				var pixel := native_image.get_pixel(native_image.get_width() >> 1, native_image.get_height() >> 1)
				_check(pixel.r > 0.9 and pixel.g < 0.1 and pixel.b < 0.1 and pixel.a > 0.9, "real worker preserves fixture red pixels")
				windowed_preview_measured = true
		# A second real request also exercises Godot's cached callback path.
		actual = cap.execute("get_resource_preview", {"path": "res://texture.png"})
		_check(actual.has("__deferred_resource_preview__"), "cached request defers without protocol change")
		terminal = null
		while terminal == null:
			await get_tree().process_frame
			terminal = cap.poll_pending_resource_preview()
		_check(terminal.get("available") == true, "cached worker result completes")
	for path in ["res://../bad.png", "res:///bad.png", "res://./texture.png", "res://missing.png", "res://linked.png"]:
		_check(cap.execute("get_resource_preview", {"path": path}).has("__error__"), "invalid/linked path " + path)
	var token := _begin()
	_check(cap.poll_pending_resource_preview() == null, "pending is not success")
	cap._resource_preview_ready("res://wrong.png", null, null, token)
	_check(not cap._pending_resource_preview.completed, "wrong path ignored")
	cap._resource_preview_ready("res://texture.png", null, null, token - 1)
	_check(not cap._pending_resource_preview.completed, "wrong token ignored")
	cap._resource_preview_ready("res://texture.png", null, null, token)
	_check(cap._pending_resource_preview.completed, "synchronous-style delivery accepted")
	actual = cap.poll_pending_resource_preview()
	_check(actual.get("available") == false and actual.has("reason"), "null preview unavailable")
	_check(cap._pending_resource_preview.is_empty(), "terminal clears slot")
	_check(cap.poll_pending_resource_preview() == null, "terminal delivered once")
	token = _begin()
	cap.cancel_pending_resource_preview()
	cap._resource_preview_ready("res://texture.png", null, null, token)
	_check(cap._pending_resource_preview.is_empty(), "cancel ignores late callback")
	var replacement := _begin()
	cap._resource_preview_ready("res://texture.png", null, null, token)
	_check(not cap._pending_resource_preview.completed, "same-path old callback cannot complete replacement")
	cap._resource_preview_ready("res://texture.png", null, null, replacement)
	_check(cap.poll_pending_resource_preview().get("available") == false, "new same-path request completes")
	token = _begin()
	cap._pending_resource_preview.deadline_ms = Time.get_ticks_msec() - 1
	cap._resource_preview_ready("res://texture.png", null, null, token)
	_check(not cap._pending_resource_preview.completed, "expired callback ignored")
	var timed_out: Dictionary = cap.poll_pending_resource_preview()
	timeout_error = str(timed_out.get("__error__", ""))
	_check("timed out" in timeout_error, "timeout is explicit failure")
	_check(cap._pending_resource_preview.is_empty(), "timeout clears slot")
	token = _begin()
	cap._resource_preview_ready("res://texture.png", null, null, token)
	cap._pending_resource_preview.deadline_ms = Time.get_ticks_msec() - 1
	_check(cap.poll_pending_resource_preview().has("__error__"), "completed result cannot publish after deadline")

	# Mutate actual fixture files, rather than only altering the saved stamp.
	var changed_path := "res://changed.tres"
	var changed := FileAccess.open(changed_path, FileAccess.WRITE)
	changed.store_string('[gd_resource type="Gradient" format=3]\n[resource]\n')
	changed.close()
	token = _begin(changed_path)
	changed = FileAccess.open(changed_path, FileAccess.READ_WRITE)
	changed.seek_end()
	changed.store_string('; changed source length\n')
	changed.close()
	cap._resource_preview_ready(changed_path, null, null, token)
	_check(cap.poll_pending_resource_preview().has("__error__"), "actual source modification rejected")
	token = _begin(changed_path)
	changed = FileAccess.open(changed_path + ".import", FileAccess.WRITE)
	changed.store_string('[remap]\nimporter="fixture"\n')
	changed.close()
	cap._resource_preview_ready(changed_path, null, null, token)
	_check(cap.poll_pending_resource_preview().has("__error__"), "actual import metadata change rejected")
	token = _begin(changed_path)
	DirAccess.remove_absolute(changed_path)
	cap._resource_preview_ready(changed_path, null, null, token)
	_check(cap.poll_pending_resource_preview().has("__error__"), "deleted source rejected")
	DirAccess.remove_absolute(changed_path + ".import")

	var identity: Dictionary = cap._resource_preview_identity("res://texture.png")
	_check(not identity.has("error"), "source and import identity readable")
	token = _begin()
	cap._pending_resource_preview.identity = {"stamps": []}
	cap._resource_preview_ready("res://texture.png", null, null, token)
	_check(cap.poll_pending_resource_preview().has("__error__"), "changed source/import rejects before null success")
	_check(not cap._resource_preview_safe_path("res://linked.png"), "source symlink rejected")
	_check(not cap._resource_preview_safe_path("res://output-link/cache.png"), "parent symlink rejected")
	_check(not cap._resource_preview_safe_path("res://a/../cache.png"), "parent traversal rejected")
	_check(not cap._resource_preview_safe_path("res://a\\cache.png"), "backslash output rejected")
	_check(EditorInterface.get_edited_scene_root() == null, "disk resource needs no open scene")

	# These are native imported texture + callback-consumer tests. Delivery is
	# synthetic: they are not proof that the headless preview worker can run.
	var texture: Texture2D = load("res://texture.png")
	_check(texture != null, "fixture imported as native Texture2D")
	var empty_texture := ImageTexture.new()
	token = _begin()
	cap._resource_preview_ready("res://texture.png", empty_texture, null, token)
	_check(cap.poll_pending_resource_preview().has("__error__"), "zero-sized texture rejected before readback")
	var oversized_texture := ImageTexture.create_from_image(Image.create(1025, 1, false, Image.FORMAT_RGBA8))
	token = _begin()
	cap._resource_preview_ready("res://texture.png", oversized_texture, null, token)
	_check(cap.poll_pending_resource_preview().has("__error__"), "oversized native texture rejected before readback")
	if texture != null and texture.get_image() != null:
		callback_image_measured = true
		token = _begin()
		cap._resource_preview_ready("res://texture.png", texture, null, token)
		actual = cap.poll_pending_resource_preview()
		_check(actual.get("available") == true, "callback consumer publishes PNG")
		_check(actual.get("width") == 2 and actual.get("height") == 2, "actual native dimensions")
		var output: String = actual.get("preview_path", "")
		_check(FileAccess.file_exists(output), "published PNG exists")
		var image := Image.load_from_file(output)
		_check(image != null and image.get_pixel(0, 0).r > 0.9, "PNG pixels read back")
		var before := FileAccess.get_sha256(output)
		token = _begin()
		var stage := "res://.dcc-mcp/previews/%s-%s.tmp.png" % ["res://texture.png".md5_text(), token]
		var file := FileAccess.open(stage, FileAccess.WRITE)
		file.store_string("owned prior file")
		file.close()
		cap._resource_preview_ready("res://texture.png", texture, null, token)
		_check(cap.poll_pending_resource_preview().has("__error__"), "occupied stage rejected")
		_check(FileAccess.get_sha256(output) == before, "failure preserves prior preview")
		_check(FileAccess.get_file_as_string(stage) == "owned prior file", "failure preserves unowned stage")
		DirAccess.remove_absolute(stage)
		DirAccess.remove_absolute(output)
		var directory := DirAccess.open("res://")
		var linked := directory.create_link(ProjectSettings.globalize_path("res://texture.png"), ProjectSettings.globalize_path(output))
		if linked == OK:
			token = _begin()
			cap._resource_preview_ready("res://texture.png", texture, null, token)
			_check(cap.poll_pending_resource_preview().has("__error__"), "final symlink rejected")
			DirAccess.remove_absolute(output)
		else:
			failures.append("fixture could not create output symlink")
	# Actual plugin methods with a command seam exercise slot/request routing.
	var routed := BridgeProbe.new()
	var commands := CommandsProbe.new()
	commands.capability = cap
	routed._commands = commands
	routed._pending_preview_request = {"id": "scene-id", "deadline_ms": Time.get_ticks_msec() + 10000}
	routed._execute_bridge_request({"id": "resource-id", "method": "capability.get_resource_preview", "params": {"path": "res://texture.png"}})
	_check(routed._pending_preview_request.id == "scene-id", "resource routing preserves scene request")
	_check(routed._pending_resource_preview_request.id == "resource-id", "resource routing owns its request")
	token = _begin()
	cap._resource_preview_ready("res://texture.png", null, null, token)
	routed._advance_pending_resource_preview()
	_check(routed.sent.size() == 1 and routed.sent[0].id == "resource-id", "terminal result uses original resource id")
	_check(routed.sent[0].result.available == false, "routed unavailable is not image evidence")
	_check(routed._pending_resource_preview_request.is_empty(), "routing clears only resource slot")
	_check(routed._pending_preview_request.id == "scene-id", "terminal resource leaves scene slot")
	token = _begin()
	routed._pending_resource_preview_request = {"id": "disconnect-id"}
	routed._next_reconnect_ms = Time.get_ticks_msec() + 10000
	routed._process(0.0)
	_check(cap._pending_resource_preview.is_empty(), "closed connection cancels before publish")
	_check(routed._pending_resource_preview_request.is_empty(), "closed connection clears request")
	cap._resource_preview_ready("res://texture.png", null, null, token)
	_check(cap._pending_resource_preview.is_empty(), "disconnect late callback ignored")
	token = _begin()
	routed._pending_resource_preview_request = {"id": "unload-id"}
	routed._exit_tree()
	_check(cap._pending_resource_preview.is_empty(), "unload cancels resource")
	_check(routed._pending_resource_preview_request.is_empty() and routed._pending_preview_request.is_empty(), "unload clears both routing slots")
	cap._resource_preview_ready("res://texture.png", null, null, token)
	_check(cap._pending_resource_preview.is_empty(), "unload late callback ignored")
	routed.free()
	cap.cancel_pending_resource_preview()
	_finish()

func _finish() -> void:
	set_process(false)
	var result := {"checks": checks, "failures": failures, "passed": failures.is_empty(),
		"engine": Engine.get_version_info().string,
		"callback_consumer_image_measured": callback_image_measured,
		"not_measured": [] if callback_image_measured else ["Native imported Texture2D image unavailable: PNG consumer checks were not run"],
		"windowed_preview_worker_measured": windowed_preview_measured,
		"timeout_error": timeout_error,
		"scope": "native callback-consumer state contracts include synthetic delivery; windowed worker has its own measured flag; not MCP acceptance"}
	var file := FileAccess.open("res://preview-result.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(result))
	file.close()
	print("RESOURCE_PREVIEW_CONTRACT_RESULT ", JSON.stringify(result))
	get_tree().quit(0 if failures.is_empty() else 1)
