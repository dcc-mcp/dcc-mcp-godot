extends SceneTree

var _render := false
var _output := "res://captures/spell-vfx"


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var scene_path := "res://spell_vfx/spellcasting_demo.tscn"
	for argument in OS.get_cmdline_user_args():
		if argument == "--render": _render = true
		if argument.begins_with("--scene="): scene_path = argument.trim_prefix("--scene=")
		if argument.begins_with("--output-dir="): _output = argument.trim_prefix("--output-dir=")
	if not _check_saved_effects(): return
	var packed := load(scene_path) as PackedScene
	if packed == null:
		_fail("Spell demonstration could not be loaded")
		return
	if not await _check_looping_imported_cast(packed): return
	var demo := packed.instantiate() as Node3D
	demo.set("auto_cast", false)
	root.add_child(demo)
	await process_frame
	var timeline := demo.get_node_or_null("CastTimeline") as AnimationPlayer
	if timeline == null or not timeline.has_animation("Cast"):
		_fail("Cast timeline is missing")
		return
	var animation := timeline.get_animation("Cast")
	var release_time: float = demo.get_state().release_time
	var release_key := false
	for track in range(animation.get_track_count()):
		if animation.track_get_type(track) != Animation.TYPE_METHOD: continue
		for key in range(animation.track_get_key_count(track)):
			var value: Dictionary = animation.track_get_key_value(track, key)
			if value.get("method") == "release_spell" and is_equal_approx(animation.track_get_key_time(track, key), release_time):
				release_key = true
	if not release_key:
		_fail("Cast must release through its declared animation phase event")
		return
	await create_timer(0.35).timeout
	var initial_hand: Array = demo.get_state().hand_position
	var imported_skeleton: Skeleton3D
	var hand_index := -1
	var initial_hand_pose := Transform3D.IDENTITY
	if demo.get_state().mage_kind == "imported_skeletal":
		for skeleton in demo.find_children("*", "Skeleton3D", true, false):
			var index: int = skeleton.find_bone(str(demo.hand_bone))
			if index >= 0:
				imported_skeleton = skeleton
				hand_index = index
				initial_hand_pose = skeleton.get_bone_global_pose(index)
				break
		if imported_skeleton == null:
			_fail("Imported skeletal mage has no casting hand bone")
			return
	if not demo.cast_spell():
		_fail("First cast did not start")
		return
	await create_timer(0.4).timeout
	if demo.release_count != 0:
		_fail("Projectile was released before the animation release key")
		return
	if initial_hand == demo.get_state().hand_position:
		_fail("Casting animation did not articulate the hand")
		return
	if imported_skeleton != null and initial_hand_pose.is_equal_approx(imported_skeleton.get_bone_global_pose(hand_index)):
		_fail("Imported Cast animation did not animate the skeleton")
		return
	var gathered_radius: float = demo.get_state().charge_radius
	await create_timer(0.40).timeout
	if demo.release_count != 0 or demo.get_state().phase != "contract" or demo.get_state().charge_radius >= gathered_radius:
		_fail("Charge must visibly contract before the release event")
		return
	demo.camera_feedback_enabled = false
	await process_frame
	await process_frame
	if not is_equal_approx(demo.get_node("Camera").fov, 49.0):
		_fail("Camera feedback must be fully disableable")
		return
	demo.camera_feedback_enabled = true
	var before: Image
	if _render:
		before = await _capture("spell-charge.png")
		if before == null: return
	if not await _wait_count(demo, "release_count", 1, 2.0): return
	await create_timer(0.10).timeout
	var flight_state: Dictionary = demo.get_state()
	if flight_state.active_projectiles.is_empty() or demo.impact_count != 0:
		_fail("Released projectile did not enter a separate flight phase")
		return
	var first_position: Array = flight_state.active_projectiles[0].position
	var flight: Image
	if _render:
		flight = await _capture("spell-flight.png")
		if flight == null: return
	await create_timer(0.05).timeout
	var moved_state: Dictionary = demo.get_state()
	if moved_state.active_projectiles.is_empty() or first_position == moved_state.active_projectiles[0].position:
		_fail("Projectile position did not advance during native processing")
		return
	if not await _wait_count(demo, "impact_count", 1, 3.0): return
	var contact_state: Dictionary = demo.get_state()
	if contact_state.active_projectiles.is_empty() or contact_state.active_projectiles[0].impact_kind != "collision":
		_fail("Target feedback must follow a physics contact")
		return
	await create_timer(0.1).timeout
	if _render:
		var impact := await _capture("spell-impact.png")
		if impact == null: return
		var charge_to_flight := _changed_pixels(before, flight)
		var flight_to_impact := _changed_pixels(flight, impact)
		if charge_to_flight < 40 or flight_to_impact < 40:
			_fail("Rendered charge, flight and impact did not produce distinct frames")
			return
		print("SPELL_VFX_RENDER_OK charge_to_flight=%s flight_to_impact=%s" % [charge_to_flight, flight_to_impact])
	await create_timer(4.2).timeout
	var completed: Dictionary = demo.get_state()
	if completed.release_count != 1 or completed.impact_count != 1 or not completed.active_projectiles.is_empty():
		_fail("One cast must produce one impact and clean up all projectiles: %s" % completed)
		return
	if not demo.cast_spell():
		_fail("A completed cast could not be repeated")
		return
	if not await _wait_count(demo, "impact_count", 2, 3.0): return
	var cleanup_deadline := Time.get_ticks_msec() + 2000
	while not demo.get_state().active_projectiles.is_empty():
		if Time.get_ticks_msec() > cleanup_deadline:
			_fail("Repeated cast leaked a projectile")
			return
		await process_frame
	if demo.release_count != 2 or demo.impact_count != 2:
		_fail("Repeated cast released or impacted more than once")
		return
	var projectile_script := load(demo.get_script().resource_path.get_base_dir().path_join("spell_projectile.gd")) as Script
	var missed: Node3D = projectile_script.new()
	missed.set("speed", 0.1)
	missed.set("lifetime", 0.35)
	demo.add_child(missed)
	missed.global_position = Vector3(0, 100, 0)
	var missed_impacts := [0]
	missed.connect("impacted", func(_position: Vector3): missed_impacts[0] += 1)
	missed.launch(Vector3(100, 100, 0))
	await create_timer(0.75).timeout
	if is_instance_valid(missed) or missed_impacts[0] != 0:
		_fail("Missed projectile must expire within its bound without a false impact")
		return
	if demo.cast_combo("unknown"):
		_fail("Unknown combo was accepted")
		return
	for combo in ["ember_chain", "arcane_surge"]:
		var expected: int = demo.release_count + 2
		if not demo.cast_combo(combo) or demo.cast_spell() or demo.cast_combo(combo):
			_fail("Combo must start once and reject overlapping casts")
			return
		if not await _wait_count(demo, "impact_count", expected, 6.0): return
		var combo_deadline := Time.get_ticks_msec() + 4500
		while not demo.get_state().active_projectiles.is_empty() or demo.get_state().active_ground_effects > 0 or not demo.get_state().combo.is_empty():
			if Time.get_ticks_msec() > combo_deadline:
				_fail("Combo did not finish or clean up its ground effects and projectiles")
				return
			await process_frame
		if demo.release_count != expected or demo.impact_count != expected:
			_fail("Combo must release and impact exactly twice")
			return
	var target_body := demo.get_node("TargetCrystal/HitBody") as StaticBody3D
	target_body.collision_layer = 0
	await physics_frame
	if not demo.cast_spell():
		_fail("Empty-destination cast did not start")
		return
	if not await _wait_count(demo, "release_count", 7, 3.0): return
	var miss_deadline := Time.get_ticks_msec() + 4000
	while demo.get_state().casting or not demo.get_state().active_projectiles.is_empty() or demo.get_state().active_ground_effects > 0:
		if demo.impact_count != 6:
			_fail("An empty destination must not trigger impact feedback")
			return
		if Time.get_ticks_msec() > miss_deadline:
			_fail("Empty-destination cast did not clean up")
			return
		await process_frame
	if demo.impact_count != 6 or not is_equal_approx(demo.get_node("Camera").fov, 49.0):
		_fail("Miss must finish without impact feedback or a lingering camera punch")
		return
	target_body.collision_layer = 1
	if demo.get_state().audio_events != {"charge": 7, "release": 7, "impact": 6}:
		_fail("Audio cues must follow animation and actual contact, including the missed cast")
		return
	for player_name in ["ChargeSound", "ReleaseSound", "ImpactSound"]:
		var sound := demo.get_node(player_name) as AudioStreamPlayer3D
		if not is_equal_approx(sound.volume_db, demo.sound_gain_db):
			_fail("Native cues must use the configured scene gain")
			return
		if not sound.stream is AudioStreamWAV or sound.stream.data.is_empty() or sound.stream.loop_mode != AudioStreamWAV.LOOP_DISABLED:
			_fail("Default audio must contain finite native PCM data")
			return
		var pcm: PackedByteArray = sound.stream.data
		var peak := 0
		for index in range(0, pcm.size(), 2): peak = maxi(peak, absi(pcm.decode_s16(index)))
		if sound.stream.mix_rate != 44100 or peak < 1000 or peak > 24000 or pcm.decode_s16(0) != 0 or pcm.decode_s16(pcm.size() - 2) != 0:
			_fail("Default cues need audible energy, peak headroom and click-free endpoints")
			return
	demo.sound_enabled = false
	demo._play_cue("impact", Vector3.ZERO, 1.0)
	if demo.get_state().audio_events.impact != 6:
		_fail("Disabled audio must not emit a cue")
		return
	print("SPELL_VFX_SMOKE_OK character=%s releases=7 impacts=6 cleanup=true missed_cleanup=true contact_only=true combos=2" % completed.mage_kind)
	demo.queue_free()
	await process_frame
	quit(0)


func _check_looping_imported_cast(demo_scene: PackedScene) -> bool:
	var character := Node3D.new()
	var skeleton := Skeleton3D.new()
	skeleton.name = "Skeleton3D"
	skeleton.add_bone("RightCastSocket")
	skeleton.set_bone_rest(0, Transform3D(Basis.IDENTITY, Vector3(0, 1, 0)))
	character.add_child(skeleton)
	skeleton.owner = character
	var player := AnimationPlayer.new()
	character.add_child(player)
	player.owner = character
	var source := Animation.new()
	source.length = 1.6
	source.loop_mode = Animation.LOOP_LINEAR
	var track := source.add_track(Animation.TYPE_POSITION_3D)
	source.track_set_path(track, NodePath("Skeleton3D:RightCastSocket"))
	source.track_insert_key(track, 0.0, Vector3(0, 1, 0))
	source.track_insert_key(track, 1.6, Vector3(0, 1, 0))
	var library := AnimationLibrary.new()
	library.add_animation("Cast", source)
	player.add_animation_library("", library)
	var fixture := PackedScene.new()
	var packed_error := fixture.pack(character)
	character.free()
	if packed_error != OK:
		_fail("Could not pack the looping imported-cast fixture")
		return false
	var demo := demo_scene.instantiate() as Node3D
	demo.set("mage_scene", fixture)
	demo.set("auto_cast", false)
	demo.set("camera_feedback_enabled", false)
	root.add_child(demo)
	var timeline := demo.get_node("CastTimeline") as AnimationPlayer
	var valid: bool = demo.get_state().mage_kind == "imported_skeletal" and timeline.get_animation("Cast").loop_mode == Animation.LOOP_NONE
	for cycle in range(2):
		if not valid or not demo.cast_spell():
			valid = false
			break
		timeline.speed_scale = 8.0
		var deadline := Time.get_ticks_msec() + 2000
		while timeline.is_playing() and Time.get_ticks_msec() < deadline:
			await process_frame
		await process_frame
		valid = not demo.get_state().casting and demo.release_count == cycle + 1
	valid = valid and source.loop_mode == Animation.LOOP_LINEAR
	demo.queue_free()
	await process_frame
	if not valid:
		_fail("Looping imported Cast must become a repeatable one-shot without mutating its source")
	return valid


func _check_saved_effects() -> bool:
	if not FileAccess.file_exists("res://vfx_particles.tscn"): return true
	var packed := load("res://vfx_particles.tscn") as PackedScene
	if packed == null:
		_fail("Saved VFX scene could not be reloaded")
		return false
	var instance := packed.instantiate()
	var fire := instance.get_node_or_null("DynamicFire")
	var projectile := instance.get_node_or_null("SpellProjectile")
	if fire == null or projectile == null:
		instance.free()
		_fail("Saved fire or inert projectile was lost")
		return false
	var flames := fire.get_node_or_null("Flames") as GPUParticles3D
	var sparks := fire.get_node_or_null("Sparks") as GPUParticles3D
	var light := fire.get_node_or_null("Light") as OmniLight3D
	var valid := flames != null and sparks != null and light != null
	if valid:
		valid = flames.amount == 48 and flames.draw_pass_1 != null and sparks.draw_pass_1 != null and flames.process_material is ParticleProcessMaterial
		if valid:
			var material := flames.draw_pass_1.surface_get_material(0) as ShaderMaterial
			valid = material != null and material.get_shader_parameter("fire_texture") is Texture2D and material.get_shader_parameter("heat_ramp") is GradientTexture1D
	instance.free()
	if not valid:
		_fail("Particle subresources did not survive save and reload")
	return valid


func _wait_count(demo: Node, property: String, expected: int, seconds: float) -> bool:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000)
	while int(demo.get(property)) < expected:
		if Time.get_ticks_msec() > deadline:
			_fail("Timed out waiting for %s = %s" % [property, expected])
			return false
		await process_frame
	return true


func _capture(filename: String) -> Image:
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	if image == null or image.is_empty():
		_fail("Rendering produced no pixels; --render needs a native graphics backend")
		return null
	var error := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(_output))
	if error != OK or image.save_png(_output.path_join(filename)) != OK:
		_fail("Could not write render evidence: %s" % filename)
		return null
	return image


func _changed_pixels(first: Image, second: Image) -> int:
	var count := 0
	for y in range(0, first.get_height(), 2):
		for x in range(0, first.get_width(), 2):
			var a := first.get_pixel(x, y)
			var b := second.get_pixel(x, y)
			if absf(a.r - b.r) + absf(a.g - b.g) + absf(a.b - b.b) > 0.09:
				count += 1
	return count


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
