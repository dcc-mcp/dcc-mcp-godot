extends SceneTree

var _render := false
var _output := "res://captures/combat-vfx"
var _failed := false
var _effect_script: Script
var _projectile_script: Script


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var scene_path := "res://combat_vfx/combat_vfx_gallery.tscn"
	for argument in OS.get_cmdline_user_args():
		if argument == "--render": _render = true
		if argument.begins_with("--scene="): scene_path = argument.trim_prefix("--scene=")
		if argument.begins_with("--output-dir="): _output = argument.trim_prefix("--output-dir=")
	if not _check_saved_effects(): return
	_effect_script = load(scene_path.get_base_dir().path_join("combat_effect.gd")) as Script
	_projectile_script = load(scene_path.get_base_dir().path_join("spell_projectile.gd")) as Script
	var scene := load(scene_path) as PackedScene
	if not _check(scene != null and _effect_script != null and _projectile_script != null, "Combat templates did not load"): return
	var gallery := scene.instantiate() as Node3D
	gallery.set("auto_play", false)
	root.add_child(gallery)
	await process_frame
	if not await _check_presets(gallery, scene_path.get_base_dir()): return
	if not await _check_one_shots(gallery): return
	if not await _check_aura(gallery): return
	if not _check_aura_pulse(gallery): return
	if not await _check_projectile(gallery): return
	var timeline := gallery.get_node_or_null("Timeline") as AnimationPlayer
	if not _check(timeline != null and timeline.has_animation("Showcase"), "Gallery animation timeline is missing"): return
	var clip := timeline.get_animation("Showcase")
	var methods: Array[String] = []
	for track in range(clip.get_track_count()):
		if clip.track_get_type(track) != Animation.TYPE_METHOD: continue
		for key in range(clip.track_get_key_count(track)):
			methods.append(str(clip.method_track_get_name(track, key)))
	if not _check(methods.has("strike") and methods.has("pulse_impact") and methods.has("release_projectile"), "Attack and spell phases need animation method events"): return
	gallery.play_cycle()
	await create_timer(0.30).timeout
	if not _check(gallery.event_count == 1, "Slash event did not fire at its animation key"): return
	var active: Image
	if _render:
		active = await _capture("combat-active.png")
		if active == null: return
	await create_timer(0.95).timeout
	if not _check(gallery.event_count == 3, "Projectile and impact events did not fire exactly once"): return
	var impact: Image
	if _render:
		impact = await _capture("combat-impact.png")
		if impact == null: return
	gallery.stop_effects()
	await create_timer(0.55).timeout
	if _render:
		var stopped := await _capture("combat-stopped.png")
		if stopped == null: return
		var animation_changes := _changed_pixels(active, impact)
		var faded_pixels := _changed_pixels(active, stopped)
		var light_pixels := _faded_light_pixels(active, stopped)
		if not _check(animation_changes > 40 and faded_pixels > 80 and light_pixels > 40, "Rendered attacks, circle emission and alpha fade were not visible"): return
		print("COMBAT_VFX_RENDER_OK animation_changes=%d faded_pixels=%d light_pixels=%d" % [animation_changes, faded_pixels, light_pixels])
	print("COMBAT_VFX_SMOKE_OK repeats=true aura_stop=true aura_pulse=true materials_isolated=true projectile_exclusion=true world_flight=true cleanup=true")
	gallery.queue_free()
	await process_frame
	quit(0)


func _new_effect(parent: Node3D, kind: String, duration: float, auto_free: bool = false) -> Node3D:
	var effect: Node3D = _effect_script.new()
	effect.set("kind", kind)
	effect.set("duration", duration)
	effect.set("autoplay", false)
	effect.set("auto_free", auto_free)
	parent.add_child(effect)
	return effect


func _check_presets(parent: Node3D, directory: String) -> bool:
	for name in ["attack_slash", "spell_impact", "magic_aura", "fire_projectile", "mesh_fire", "particle_fire"]:
		var packed := load(directory.path_join(name + ".tscn")) as PackedScene
		if not _check(packed != null, "Portable preset failed to load: " + name): return false
		var first := packed.instantiate() as Node3D
		var second := packed.instantiate() as Node3D
		parent.add_child(first)
		parent.add_child(second)
		if name == "mesh_fire":
			var mesh := first.get_node("FireVFX") as MeshInstance3D
			var material := mesh.material_override as ShaderMaterial
			var sibling := second.get_node("FireVFX").material_override as ShaderMaterial
			if not _check(mesh.mesh is CylinderMesh and material != sibling, "Mesh fire must own its material"): return false
			for parameter in ["noise_texture", "detail_texture"]:
				if not _check(material.get_shader_parameter(parameter) is NoiseTexture2D, "Mesh fire lost procedural noise"): return false
			if not _check(material.get_shader_parameter("color_ramp") is GradientTexture1D and not material.shader.resource_path.begins_with("res://addons/"), "Mesh fire must retain portable shader/ramp dependencies"): return false
			material.set_shader_parameter("dissolve", 0.8)
			if not _check(is_zero_approx(sibling.get_shader_parameter("dissolve")), "Changing one fire changed another instance"): return false
		elif name == "particle_fire":
			for child_name in ["Flames", "Sparks"]:
				var particles := first.get_node_or_null(child_name) as GPUParticles3D
				if not _check(particles != null and particles.draw_pass_1 != null and particles.process_material != null, "Particle fire must build visible particles"): return false
			var material := first.get_node("Flames").material_override as ShaderMaterial
			if not _check(first.get_node_or_null("Light") is OmniLight3D and material.get_shader_parameter("fire_texture") is Texture2D and material.get_shader_parameter("heat_ramp") is GradientTexture1D and not material.shader.resource_path.begins_with("res://addons/"), "Particle fire dependencies were not retained"): return false
		first.queue_free()
		second.queue_free()
		await process_frame
		if not _check(not is_instance_valid(first) and not is_instance_valid(second), "Preset instances did not clean up"): return false
	return true


func _check_one_shots(parent: Node3D) -> bool:
	for kind in ["slash", "impact"]:
		var effect := _new_effect(parent, kind, 0.16)
		var completions := [0]
		effect.connect("finished", func(): completions[0] += 1)
		var child_count := effect.get_child_count()
		for cycle in range(2):
			if not _check(effect.play(), "One-shot did not start"): return false
			await create_timer(0.28).timeout
			var state: Dictionary = effect.get_state()
			if not _check(completions[0] == cycle + 1 and not state.playing and not effect.is_processing(), "One-shot must finish once and stop processing"): return false
			if not _check(effect.get_child_count() == child_count, "Replaying a one-shot accumulated visual children"): return false
		effect.stop()
		await process_frame
		if not _check(completions[0] == 2, "Stopping a finished one-shot emitted another finish"): return false
		effect.queue_free()
	var transient := _new_effect(parent, "impact", 0.12, true)
	transient.play()
	await create_timer(0.28).timeout
	return _check(not is_instance_valid(transient), "auto_free did not remove a completed one-shot")


func _check_aura(parent: Node3D) -> bool:
	var anchor := Node3D.new()
	anchor.position = Vector3(1, 8, 2)
	parent.add_child(anchor)
	var first := _new_effect(anchor, "aura", 0.08)
	var second := _new_effect(anchor, "aura", 0.08)
	first.set("tint", Color("44ddff"))
	second.set("tint", Color("ffaa33"))
	first.play()
	second.play()
	var first_material := first.get_node("Surface").material_override as ShaderMaterial
	var second_material := second.get_node("Surface").material_override as ShaderMaterial
	if not _check(first_material != second_material and first_material.get_shader_parameter("tint") != second_material.get_shader_parameter("tint"), "Separate effects share mutable material state"): return false
	var second_tint: Color = second_material.get_shader_parameter("tint")
	first.set("tint", Color("88ff66"))
	var original_children := first.get_child_count()
	for attempt in range(3): first.play()
	if not _check(second_material.get_shader_parameter("tint") == second_tint and first.get_child_count() == original_children, "Replay changed a sibling material or accumulated children"): return false
	var start := first.global_position
	var motion := Vector3(2, 1, -3)
	anchor.position += motion
	if not _check(first.global_position.is_equal_approx(start + motion), "An attached aura did not follow its parent"): return false
	var completions := [0]
	first.connect("finished", func(): completions[0] += 1)
	await create_timer(0.25).timeout
	if not _check(first.get_state().playing and completions[0] == 0, "Persistent aura ended at one-shot duration"): return false
	var motes := first.get_node("Motes") as GPUParticles3D
	var mote_material := motes.draw_pass_1.surface_get_material(0) as StandardMaterial3D
	var playing_opacity: float = first_material.get_shader_parameter("opacity")
	var playing_alpha := mote_material.albedo_color.a
	var layers := [first.get_node("RuneOrbit"), first.get_node("InnerSeal")]
	var layer_opacities: Array[float] = []
	for layer in layers:
		var material := layer.material_override as ShaderMaterial
		if not _check(layer.visible and material != first_material and material.get_shader_parameter("tint") == first.tint, "Aura layers must retain isolated replay tint"): return false
		layer_opacities.append(float(material.get_shader_parameter("opacity")))
	if not _check(layers[1].position.y > layers[0].position.y and layer_opacities[0] > layer_opacities[1], "Aura layers must open at distinct heights and times"): return false
	first.stop()
	await create_timer(0.10).timeout
	if not _check(first_material.get_shader_parameter("opacity") < playing_opacity and mote_material.albedo_color.a < playing_alpha, "Aura stop must fade both its ring and already emitted motes"): return false
	for index in range(layers.size()):
		if not _check(float(layers[index].material_override.get_shader_parameter("opacity")) <= layer_opacities[index], "Stopping a partially opened aura must not brighten a later layer"): return false
	await create_timer(0.27).timeout
	if not _check(not first.get_state().playing and not first.visible and not first.is_processing() and completions[0] == 1, "Aura stop did not fade and finish once"): return false
	first.stop()
	await process_frame
	if not _check(completions[0] == 1, "Repeated aura stop emitted multiple completions"): return false
	first.set("kind", "impact")
	if not _check(first.play() and not motes.visible and not motes.emitting, "Reusing an aura as an impact exposed stale aura particles"): return false
	if not _check(not layers[0].visible and not layers[1].visible, "An impact must not expose retained aura layers"): return false
	await create_timer(0.18).timeout
	if not _check(completions[0] == 2, "Reused impact did not finish exactly once"): return false
	first.set("kind", "aura")
	if not _check(first.play() and motes.visible and motes.emitting, "Reusing an impact as an aura did not restore its particles"): return false
	await create_timer(0.18).timeout
	if not _check(first.get_state().playing and mote_material.albedo_color.a > 0.0 and first.get_child_count() == original_children, "Restarted aura failed to fade in or accumulated children"): return false
	first.stop()
	await create_timer(0.32).timeout
	if not _check(completions[0] == 3 and not first.is_processing(), "Reused aura did not stop cleanly"): return false
	anchor.queue_free()
	return true


func _check_aura_pulse(parent: Node3D) -> bool:
	var aura := _new_effect(parent, "aura", 0.6)
	var completions := [0]
	aura.connect("finished", func(): completions[0] += 1)
	if not _check(not aura.pulse() and aura.play(), "Inactive aura pulse must be rejected"): return false
	aura.set_process(false)
	aura._process(0.22)
	if not _check(is_equal_approx(aura.get_state().visual_scale, 1.06), "Aura opening must expand before settling"): return false
	aura._process(0.18)
	if not _check(aura.pulse() and not aura.pulse(), "An aura must accept one pulse without overlapping restarts"): return false
	aura._process(0.22)
	if not _check(is_equal_approx(aura.get_state().visual_scale, 0.48), "Pulse must contract before release"): return false
	aura._process(0.14)
	if not _check(is_equal_approx(aura.get_state().visual_scale, 1.35), "Pulse must expand to its bounded maximum"): return false
	var peak: float = aura.get_state().visual_scale
	aura.stop()
	if not _check(not aura.pulse(), "Stopping aura cannot accept a pulse"): return false
	aura._process(0.125)
	if not _check(aura.get_state().visual_scale < peak and aura.get_state().visual_scale > peak * 0.2, "Stop must contract continuously from the active pulse scale"): return false
	var accent: float = aura.get_node("Surface").material_override.get_shader_parameter("accent")
	if not _check(accent > 0.0 and accent < 1.0, "Stop must fade the pulse highlight instead of snapping it off"): return false
	aura._process(0.125)
	if not _check(completions[0] == 1 and not aura.get_state().playing, "Pulse stop must complete exactly once"): return false
	aura.play()
	aura.set_process(false)
	aura._process(0.4)
	if not _check(not aura.pulse(0.0) and not aura.pulse(-1.0) and aura.pulse(2.0), "Pulse tempo must be positive and finite"): return false
	aura._process(0.11)
	if not _check(is_equal_approx(aura.get_state().visual_scale, 0.48), "Pulse contraction must follow animation tempo"): return false
	aura._process(0.28)
	if not _check(is_equal_approx(aura.get_state().visual_scale, 1.0) and aura.get_state().pulse_phase < 0.0, "Completed pulse must return to its nominal footprint"): return false
	aura.queue_free()
	return true


func _check_projectile(parent: Node3D) -> bool:
	var moving_parent := Node3D.new()
	moving_parent.position = Vector3(10, 20, 10)
	parent.add_child(moving_parent)
	var moving_shot: Node3D = _projectile_script.new()
	moving_shot.position = Vector3(1, 0, 0)
	moving_shot.set("speed", 2.0)
	moving_shot.set("lifetime", 0.35)
	moving_parent.add_child(moving_shot)
	var origin := moving_shot.global_position
	moving_shot.launch(origin + Vector3(10, 0, 0))
	if not _check(moving_shot.top_level and moving_shot.global_position.is_equal_approx(origin), "Launch did not preserve world transform when becoming top-level"): return false
	moving_parent.position += Vector3(100, 50, 100)
	await create_timer(0.10).timeout
	var travelled := moving_shot.global_position - origin
	if not _check(travelled.x > 0.05 and travelled.length() < 1.0 and absf(travelled.y) < 0.01, "Moving caster teleported its projectile or short lifetime prevented travel"): return false
	await create_timer(0.40).timeout
	if not _check(not is_instance_valid(moving_shot), "Missed projectile exceeded total lifetime"): return false
	moving_parent.queue_free()
	var caster := _box_body(parent, Vector3(1, 20, 0))
	var wall := _box_body(parent, Vector3(3, 20, 0))
	await physics_frame
	await physics_frame
	var shot: Node3D = _projectile_script.new()
	shot.set("speed", 8.0)
	shot.set("lifetime", 2.0)
	parent.add_child(shot)
	shot.global_position = Vector3(0, 20, 0)
	var impacts: Array[Vector3] = []
	shot.connect("impacted", func(at: Vector3): impacts.append(at))
	var excluded: Array[RID] = [caster.get_rid()]
	shot.launch(Vector3(6, 20, 0), excluded)
	var deadline := Time.get_ticks_msec() + 1200
	while impacts.is_empty() and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _check(impacts.size() == 1 and impacts[0].x > 2.5 and impacts[0].x < 3.0, "Caster exclusion must ignore caster but still hit the wall"): return false
	await create_timer(1.05).timeout
	if not _check(not is_instance_valid(shot) and impacts.size() == 1, "Hit projectile did not clean up or emitted duplicate impact"): return false
	caster.queue_free()
	wall.queue_free()
	return await _check_projectile_outcomes(parent)


func _check_projectile_outcomes(parent: Node3D) -> bool:
	var distances: Array[float] = []
	for ramp in [0.0, 0.4]:
		var shot: Node3D = _projectile_script.new()
		shot.set("collision_mask", 0)
		shot.set("speed", 10.0)
		shot.set("acceleration_time", ramp)
		parent.add_child(shot)
		shot.launch(Vector3(100, 0, 0))
		shot.set_physics_process(false)
		shot._physics_process(0.1)
		distances.append(shot.global_position.length())
		shot.queue_free()
	if not _check(is_equal_approx(distances[0], 1.0) and distances[1] > 0.0 and distances[1] < distances[0], "Zero acceleration must preserve constant speed; ramp must start slower"): return false
	for invalid in [NAN, INF]:
		var shot: Node3D = _projectile_script.new()
		shot.set("acceleration_time", invalid)
		parent.add_child(shot)
		shot.launch(Vector3.RIGHT)
		if not _check(not shot.get_state().launched and shot.get_child_count() == 0, "Non-finite acceleration must reject launch before building effects"): return false
		shot.queue_free()
	for outcome in ["destination", "missed", "expired"]:
		var shot: Node3D = _projectile_script.new()
		shot.set("collision_mask", 0)
		shot.set("lifetime", 1.0)
		shot.set("impact_on_arrival", outcome == "destination")
		parent.add_child(shot)
		var impacts := [0]
		shot.connect("impacted", func(_at: Vector3): impacts[0] += 1)
		shot.launch(Vector3.RIGHT * (100.0 if outcome == "expired" else 0.01))
		shot.set_physics_process(false)
		shot._physics_process(0.76 if outcome == "expired" else 0.1)
		shot._physics_process(0.02)
		var expected := 1 if outcome == "destination" else 0
		if not _check(shot.get_state().impact_kind == outcome and impacts[0] == expected and shot.has_node("ImpactBurst") == (expected == 1), "Arrival, miss and expiry must retain distinct signal/burst outcomes"): return false
		if not _check(not shot.get_node("HotCore").visible or outcome == "destination", "Missed or expired projectiles must hide their flight head"): return false
		shot._physics_process(1.0)
		await process_frame
		if not _check(not is_instance_valid(shot), "Every outcome must clean up within its total lifetime"): return false
	return true


func _box_body(parent: Node3D, at: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.position = at
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(0.4, 2, 2)
	collision.shape = shape
	body.add_child(collision)
	parent.add_child(body)
	return body


func _check_saved_effects() -> bool:
	if not FileAccess.file_exists("res://combat_effects.tscn"): return true
	var packed := load("res://combat_effects.tscn") as PackedScene
	if not _check(packed != null, "Saved combat scene could not load"): return false
	var instance := packed.instantiate()
	var valid := true
	for entry in [["Slash", "slash", 2.0, 0.4], ["Aura", "aura", 1.5, 0.6], ["Impact", "impact", 1.0, 0.3]]:
		var node := instance.get_node_or_null(entry[0])
		valid = valid and node != null
		if node != null:
			valid = valid and node.get("kind") == entry[1] and is_equal_approx(node.get("radius"), entry[2]) and is_equal_approx(node.get("duration"), entry[3]) and not node.get("autoplay") and not node.get("auto_free")
	instance.free()
	return _check(valid, "Combat exported properties did not survive save and reload")


func _capture(filename: String) -> Image:
	await RenderingServer.frame_post_draw
	var pixels := root.get_texture().get_image()
	if not _check(pixels != null and not pixels.is_empty(), "Native renderer returned no pixels"): return null
	var result := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(_output))
	if not _check(result == OK and pixels.save_png(_output.path_join(filename)) == OK, "Could not save combat render evidence"): return null
	return pixels


func _changed_pixels(first: Image, second: Image) -> int:
	var count := 0
	for y in range(0, first.get_height(), 2):
		for x in range(0, first.get_width(), 2):
			var a := first.get_pixel(x, y)
			var b := second.get_pixel(x, y)
			if absf(a.r - b.r) + absf(a.g - b.g) + absf(a.b - b.b) > 0.12: count += 1
	return count


func _faded_light_pixels(first: Image, second: Image) -> int:
	var count := 0
	for y in range(0, first.get_height(), 2):
		for x in range(0, first.get_width(), 2):
			var a := first.get_pixel(x, y)
			var b := second.get_pixel(x, y)
			if (a.r + a.g + a.b) - (b.r + b.g + b.b) > 0.20: count += 1
	return count


func _check(condition: bool, message: String) -> bool:
	if not condition and not _failed:
		_failed = true
		push_error(message)
		quit(1)
	return condition
