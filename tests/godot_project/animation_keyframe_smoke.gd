@tool
extends EditorPlugin

# Native capability values and Animation methods; only edited-scene lookup is substituted.
# This is not a transport/Core or rendered/audio playback acceptance test.
class Subject:
	extends "res://addons/dcc_mcp_godot/capabilities.gd"
	var fixture := Animation.new()

	func _animation(_params: Dictionary) -> Animation:
		return fixture


var _subject: Subject
var _checks := 0
var _failures: Array[String] = []
var _skipped: Array[String] = []


func _enter_tree() -> void:
	call_deferred("_run")


func _check(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)
		push_error("KEYFRAME ASSERTION: " + message)


func _set_key(track, value, extra: Dictionary = {}) -> Dictionary:
	var params := {"animation": "fixture", "track": track, "time": 0.25, "value": value}
	params.merge(extra, true)
	return _subject._set_animation_keyframe(params)


func _snapshot() -> Dictionary:
	return _subject._get_animation_info({}).duplicate(true)


func _reject(track, value, extra: Dictionary = {}) -> void:
	var before := _snapshot()
	var result := _set_key(track, value, extra)
	_check(result.has("__error__") and not result.get("inserted", false), "rejected request cannot claim insertion: " + str(result))
	_check(_snapshot() == before, "rejected request changed an existing key/transition")


func _run() -> void:
	var filesystem := EditorInterface.get_resource_filesystem()
	var deadline := Time.get_ticks_msec() + 15000
	while true:
		var folder := filesystem.get_filesystem_path("res://")
		var index := folder.find_file_index("step.wav") if folder != null else -1
		if not filesystem.is_scanning() and index >= 0 and folder.get_file_import_is_valid(index): break
		if Time.get_ticks_msec() > deadline:
			_check(false, "editor audio import did not become ready")
			_finish()
			return
		await get_tree().process_frame
	_subject = Subject.new(self)
	var shader := Shader.new()
	shader.code = "shader_type spatial; uniform vec3 rgb : source_color; uniform vec4 rgba : source_color; void fragment() { ALBEDO = rgb + rgba.rgb; }"
	var material := ShaderMaterial.new()
	material.shader = shader
	var color_uniforms := shader.get_shader_uniform_list()
	_check(color_uniforms.size() == 2, "native color uniform metadata unavailable")
	for uniform in color_uniforms:
		var rgb: bool = uniform.name == "rgb"
		var components := [0.25, 0.5, 0.75] if rgb else [0.25, 0.5, 0.75, 0.5]
		var converted := _subject._shader_uniform_value(uniform, components)
		_check(converted.has("value"), "source_color components must follow native RGB/RGBA hints")
		if not converted.has("value"): continue
		material.set_shader_parameter(uniform.name, converted.value)
		var expected := Color(0.25, 0.5, 0.75, 1.0 if rgb else 0.5)
		_check(material.get_shader_parameter(uniform.name).is_equal_approx(expected), "source_color readback lost RGB or alpha")
		var wrong := [0.25, 0.5, 0.75, 0.5] if rgb else [0.25, 0.5, 0.75]
		_check(_subject._shader_uniform_value(uniform, wrong).has("error"), "source_color accepted wrong component count")
		_check(material.get_shader_parameter(uniform.name).is_equal_approx(expected), "rejected color input mutated material")
	_subject.fixture.length = 2.0
	var position := _subject.fixture.add_track(Animation.TYPE_POSITION_3D)
	var scale := _subject.fixture.add_track(Animation.TYPE_SCALE_3D)
	var rotation := _subject.fixture.add_track(Animation.TYPE_ROTATION_3D)
	var audio := _subject.fixture.add_track(Animation.TYPE_AUDIO)
	var value_track := _subject.fixture.add_track(Animation.TYPE_VALUE)
	var method := _subject.fixture.add_track(Animation.TYPE_METHOD)
	var bezier := _subject.fixture.add_track(Animation.TYPE_BEZIER)
	var nested := _subject.fixture.add_track(Animation.TYPE_ANIMATION)
	# JSON.parse_string preserves the real wire boundary: components are not native vectors.
	var vector = JSON.parse_string("[1.25, -2.5, 3.75]")
	for track in [position, scale]:
		var result := _set_key(track, vector, {"transition": 0.5})
		_check(result.get("inserted", false) and result.get("key", -1) == 0, "JSON vector did not insert")
		_check(_subject.fixture.track_get_key_value(track, 0) == Vector3(1.25, -2.5, 3.75), "vector readback mismatch")
		_check(is_equal_approx(_subject.fixture.track_get_key_transition(track, 0), 0.5), "transition lost")
	_check(_set_key(rotation, [0, 0, 0, 1]).get("inserted", false), "unit quaternion rejected")
	_check(_set_key(rotation, [0, 0, 0, -1]).get("inserted", false), "negative unit quaternion rejected")
	_check(_subject.fixture.track_get_key_value(rotation, 0) == Quaternion(0, 0, 0, -1), "quaternion sign changed")
	_check(_subject.fixture.track_get_key_count(rotation) == 1, "same-time insertion duplicated key")
	_check(_set_key(position, [4, 5, 6], {"transition": 0.75}).get("inserted", false), "same-time replacement rejected")
	_check(_subject.fixture.track_get_key_count(position) == 1, "replacement appended duplicate")
	_check(_subject.fixture.track_get_key_value(position, 0) == Vector3(4, 5, 6), "replacement value missing")
	_check(is_equal_approx(_subject.fixture.track_get_key_transition(position, 0), 0.75), "replacement easing lost")
	_check(_set_key(position, [3.4028234663852886e38, -3.4028234663852886e38, 0]).get("inserted", false), "float32 maximum boundary rejected")
	_check(_subject.fixture.track_get_key_value(position, 0).is_finite(), "float32 boundary overflowed")
	_check(_set_key(rotation, [0, 0, 0.707106781, 0.707106781]).get("inserted", false), "rounded unit quaternion rejected")
	for bad in [[], [1, 2], [1, 2, 3, 4], [true, 2, 3], ["1", 2, 3], [null, 2, 3], [INF, 2, 3], [NAN, 2, 3], [1e100, 2, 3], null]:
		_reject(position, bad)
	for bad in [[0, 0, 0, 0], [0, 0, 0, 2], [0, 0, 0], [0, 0, 1e100, 1], [false, 0, 0, 1]]:
		_reject(rotation, bad)
	for bad in [true, "0", null, 0.5, -1, 99, INF, NAN, 1e100]:
		_reject(bad, [1, 2, 3])
	for bad in [-1, true, "0", null, INF, NAN]:
		_reject(position, [1, 2, 3], {"time": bad})
	for bad in [true, "1", null, INF, NAN, 1e100]:
		_reject(position, [1, 2, 3], {"transition": bad})
	# Preserve existing payload shapes for the four other advertised track kinds.
	for pair in [[value_track, {"custom": [1, 2]}], [method, {"method": "play", "args": []}], [bezier, [1, 0, 0, 0, 0]], [nested, "run"]]:
		_check(_set_key(pair[0], pair[1]).get("inserted", false), "legacy track payload changed")
	# Actual Godot returns -1 for this malformed method key. Its expected engine
	# diagnostic is retained; the adapter must fail and preserve the existing key.
	_reject(method, {"method": "play"})
	_reject(audio, {"stream_path": "res://cold.wav"})
	var stream := load("res://step.wav") as AudioStreamWAV
	_check(stream != null, "trusted fixture WAV did not load")
	var audio_result := _set_key(audio, {"stream_path": "res://step.wav", "start_offset": 0.01, "end_offset": 0.02})
	_check(audio_result.get("inserted", false), "cached audio did not insert: " + str(audio_result))
	_check(_subject.fixture.audio_track_get_key_stream(audio, 0) == stream, "audio key lost exact resource reference")
	_check(is_equal_approx(_subject.fixture.audio_track_get_key_start_offset(audio, 0), 0.01), "audio start trim mismatch")
	_check(is_equal_approx(_subject.fixture.audio_track_get_key_end_offset(audio, 0), 0.02), "audio end trim mismatch")
	for path in ["user://step.wav", "/tmp/step.wav", "res://../step.wav", "res://./step.wav", "res://a//step.wav", "res://step.wav:sub", "res://missing.wav", "res://script.gd", "res://a\\step.wav"]:
		_reject(audio, {"stream_path": path})
	for bad in [true, null, -1, INF, NAN, 1e100]:
		_reject(audio, {"stream_path": "res://step.wav", "start_offset": bad})
		_reject(audio, {"stream_path": "res://step.wav", "end_offset": bad})
	_reject(audio, {"stream_path": "res://step.wav", "stream": stream})
	_reject(audio, {"stream_path": 123})
	var wrong_type := Resource.new()
	wrong_type.take_over_path("res://wrong.wav")
	_reject(audio, {"stream_path": "res://wrong.wav"})
	var scripted := AudioStreamWAV.new()
	scripted.set_script(load("res://audio_fixture.gd"))
	scripted.take_over_path("res://scripted.wav")
	_reject(audio, {"stream_path": "res://scripted.wav"})
	if FileAccess.file_exists("res://linked.wav"):
		_reject(audio, {"stream_path": "res://linked.wav"})
	else:
		_skipped.append("symlink fixture unavailable on this platform")
	var before_save := _snapshot()
	_check(ResourceSaver.save(_subject.fixture, "res://roundtrip.tres") == OK, "animation save failed")
	_subject.fixture = ResourceLoader.load("res://roundtrip.tres", "Animation", ResourceLoader.CACHE_MODE_IGNORE) as Animation
	_check(_subject.fixture != null and _snapshot() == before_save, "save/reload changed typed keys")
	# Compressed transform tracks return a real native -1 even for a valid vector.
	_subject.fixture = Animation.new()
	_subject.fixture.length = 2.0
	var compressed := _subject.fixture.add_track(Animation.TYPE_POSITION_3D)
	_subject.fixture.position_track_insert_key(compressed, 0.0, Vector3.ZERO)
	_subject.fixture.position_track_insert_key(compressed, 2.0, Vector3.ONE)
	_subject.fixture.compress()
	_check(_subject.fixture.track_is_compressed(compressed), "compressed-track fixture is not compressed")
	_reject(compressed, [1, 2, 3])
	_finish()


func _finish() -> void:
	var receipt := {"passed": _failures.is_empty(), "checks": _checks, "failures": _failures, "skipped": _skipped, "engine": Engine.get_version_info().string, "scope": "native addon methods, not MCP transport or audiovisual playback"}
	var file := FileAccess.open("res://keyframe-result.json", FileAccess.WRITE)
	if file == null:
		get_tree().quit(1)
		return
	file.store_string(JSON.stringify(receipt, "  ") + "\n")
	file.close()
	print("KEYFRAME_RESULT " + JSON.stringify(receipt))
	_subject = null
	get_tree().quit(0 if _failures.is_empty() else 1)
