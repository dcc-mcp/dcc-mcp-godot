extends Node3D

signal audio_cue(kind: String)

const FireEffect = preload("dynamic_fire.gd")
const SpellProjectile = preload("spell_projectile.gd")
const CombatEffect = preload("combat_effect.gd")
const GATHER_TIME := 0.28
const CONTRACT_TIME := 0.68
const RELEASE_TIME := 0.90
const CAST_DURATION := 1.85
const CAMERA_FOV := 49.0

@export var mage_scene: PackedScene
@export var auto_cast := true
@export var tint := Color("ff873f")
@export var cast_animation := "Cast"
@export var hand_bone := "RightCastSocket"
@export var camera_feedback_enabled := true
@export var sound_enabled := true
@export_range(-40.0, 12.0, 0.5) var sound_gain_db := -4.0
@export var charge_sound: AudioStream
@export var release_sound: AudioStream
@export var impact_sound: AudioStream

var cast_count := 0
var release_count := 0
var impact_count := 0
var character_source := "procedural_articulated"
var _timer := 2.0
var _cast_player: AnimationPlayer
var _imported_player: AnimationPlayer
var _imported_cast := ""
var _imported_idle := ""
var _cast_hand: Node3D
var _arm: Node3D
var _elbow: Node3D
var _charge: Node3D
var _projectiles: Node3D
var _target := Vector3(3.0, 1.45, 0.0)
var _status: Label
var _effects: Node3D
var _aura: Node3D
var _queued_casts: Array[Dictionary] = []
var _combo := ""
var _combo_delay := 0.0
var _shot_tint := Color.WHITE
var _shot_scale := 1.0
var _shot_speed := 7.0
var _shot_strength := 1.0
var _charging := false
var _release_age := 1.0
var _target_mesh: MeshInstance3D
var _target_material: StandardMaterial3D
var _hit_age := 1.0
var _hit_tint := Color.WHITE
var _hit_strength := 1.0
var _camera: Camera3D
var _camera_home := Vector3(-1.87, 2.5725, 8.755)
var _charge_ring: Node3D
var _charge_core: MeshInstance3D
var _charge_radius := 0.0
var _charge_opacity := 0.0
var _audio: Dictionary = {}
var _audio_events := {"charge": 0, "release": 0, "impact": 0}


func _ready() -> void:
	name = "SpellcastingDemo"
	_build_arena()
	_build_mage()
	_build_cast_animation()
	_build_audio()
	_projectiles = Node3D.new()
	_projectiles.name = "Projectiles"
	add_child(_projectiles)
	_effects = Node3D.new()
	_effects.name = "GroundEffects"
	add_child(_effects)
	_charge = FireEffect.create(tint, 24)
	_charge.name = "Charge"
	_charge.scale = Vector3.ONE * 0.22
	_cast_hand.add_child(_charge)
	FireEffect.set_emitting(_charge, false)
	_charge.visible = false
	_build_charge_shapes()
	_build_overlay()
	if not InputMap.has_action("cast"):
		InputMap.add_action("cast")
		var key := InputEventKey.new()
		key.physical_keycode = KEY_SPACE
		InputMap.action_add_event("cast", key)


func _process(delta: float) -> void:
	_timer += delta
	if not _queued_casts.is_empty() and not _cast_player.is_playing():
		_combo_delay -= delta
		if _combo_delay <= 0.0: _start_cast(_queued_casts.pop_front())
	if auto_cast and _timer >= 3.4:
		cast_spell()
	_update_feedback(delta)
	if _status != null:
		var caption := _combo.replace("_", " ").to_upper() if not _combo.is_empty() else "SINGLE CAST"
		_status.text = "%s   /   %s   /   CAST %02d   /   IMPACT %02d" % [caption, _cast_phase().to_upper(), release_count, impact_count]


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("cast"):
		cast_spell()
	if event is InputEventKey and event.pressed and not event.echo:
		match event.physical_keycode:
			KEY_1: tint = Color("ff873f")
			KEY_2: tint = Color("54dbff")
			KEY_3: tint = Color("ba7bff")
			KEY_Q: cast_combo("ember_chain")
			KEY_E: cast_combo("arcane_surge")


func cast_spell() -> bool:
	if _cast_player == null or _cast_player.is_playing() or not _combo.is_empty():
		return false
	_start_cast({"tint": tint})
	return true


func cast_combo(combo: String) -> bool:
	if _cast_player == null or _cast_player.is_playing() or not _combo.is_empty(): return false
	match combo:
		"ember_chain":
			_queued_casts.assign([
				{"tint": Color("ff9e4f"), "scale": 0.70, "speed": 13.0, "strength": 0.65, "tempo": 1.45},
				{"tint": Color("ff6438"), "scale": 1.35, "speed": 11.0, "strength": 1.5, "tempo": 0.92}])
		"arcane_surge":
			_queued_casts.assign([
				{"tint": Color("7bcfff"), "scale": 0.85, "speed": 12.0, "strength": 0.8, "tempo": 1.25},
				{"tint": Color("bf8aff"), "scale": 1.2, "speed": 10.5, "strength": 1.3, "tempo": 0.92}])
			_aura = CombatEffect.new()
			_aura.kind = "aura"
			_aura.tint = Color("a788ff")
			_aura.radius = 1.45
			_aura.auto_free = true
			_aura.position = Vector3(-3.0, 0.02, 0.0)
			_effects.add_child(_aura)
		_: return false
	_combo = combo
	_start_cast(_queued_casts.pop_front())
	return true


func _start_cast(shot: Dictionary) -> void:
	_timer = 0.0
	cast_count += 1
	_shot_tint = shot.get("tint", tint)
	_shot_scale = shot.get("scale", 1.0)
	_shot_speed = shot.get("speed", 13.5)
	_shot_strength = shot.get("strength", 1.0)
	_cast_player.speed_scale = shot.get("tempo", 1.0)
	if not is_instance_valid(_aura):
		_aura = CombatEffect.new()
		_aura.kind = "aura"
		_aura.tint = _shot_tint
		_aura.radius = 1.15
		_aura.auto_free = true
		_aura.position = Vector3(-3.0, 0.02, 0.0)
		_effects.add_child(_aura)
	if _imported_player != null: _imported_player.stop()
	_cast_player.play("Cast")


func begin_charge() -> void:
	_charge_ring.tint = _shot_tint
	_charge_ring.play()
	_play_cue("charge", _cast_hand.global_position, _cast_player.speed_scale)
	# Rebuild only this small effect so element changes affect the next cast.
	_charge.queue_free()
	_charge = FireEffect.create(_shot_tint, 20)
	_charge.name = "Charge"
	_charge.scale = Vector3.ONE * 0.22
	_cast_hand.add_child(_charge)
	for child in _charge.get_children():
		if child is GPUParticles3D:
			child.local_coords = true
			var motion := child.process_material as ParticleProcessMaterial
			motion.gravity = Vector3.ZERO
			motion.spread = 180.0
			motion.initial_velocity_min = 0.0
			motion.initial_velocity_max = 0.18
	_charging = true
	_charge.visible = true


func pulse_ground() -> void:
	if is_instance_valid(_aura): _aura.pulse(_cast_player.speed_scale)


func release_spell() -> void:
	_charge_ring.stop()
	FireEffect.set_emitting(_charge, false)
	_charging = false
	_release_age = 0.0
	var projectile := SpellProjectile.new()
	projectile.name = "Spell_%03d" % release_count
	projectile.tint = _shot_tint
	projectile.speed = _shot_speed
	projectile.visual_scale = _shot_scale
	projectile.impact_strength = _shot_strength
	projectile.lifetime = 4.0
	projectile.impact_on_arrival = false
	_projectiles.add_child(projectile)
	projectile.global_position = _cast_hand.global_position
	projectile.impacted.connect(_on_impact.bind(_shot_tint, _shot_strength))
	projectile.launch(_target)
	release_count += 1
	_play_cue("release", _cast_hand.global_position, _cast_player.speed_scale)


func finish_cast() -> void:
	_charge_ring.stop()
	FireEffect.set_emitting(_charge, false)
	_charging = false


func _on_cast_finished(_animation: StringName) -> void:
	if _imported_player != null and not _imported_idle.is_empty():
		_imported_player.play(_imported_idle)
	if not _queued_casts.is_empty():
		_combo_delay = 0.12
	else:
		_combo = ""
		if is_instance_valid(_aura): _aura.stop()
		_aura = null


func _on_impact(point: Vector3, color: Color, strength: float) -> void:
	impact_count += 1
	_play_cue("impact", point, 1.0 / sqrt(strength))
	_hit_age = 0.0
	_hit_tint = color
	_hit_strength = strength
	var impact := CombatEffect.new()
	impact.kind = "impact"
	impact.tint = color
	impact.radius = 1.25 + strength * 0.65
	impact.duration = 0.85
	impact.auto_free = true
	impact.position = Vector3(point.x, 0.025, point.z)
	_effects.add_child(impact)


func _build_audio() -> void:
	var streams := {"charge": charge_sound, "release": release_sound, "impact": impact_sound}
	for kind in streams:
		var player := AudioStreamPlayer3D.new()
		player.name = str(kind).capitalize() + "Sound"
		player.stream = streams[kind] if streams[kind] != null else _make_sound(kind)
		player.volume_db = sound_gain_db
		player.unit_size = 8.0
		player.max_distance = 30.0
		add_child(player)
		_audio[kind] = player


func _make_sound(kind: String) -> AudioStreamWAV:
	var rate := 44100
	var duration: float = {"charge": 0.90, "release": 0.55, "impact": 1.10}[kind]
	var count := int(duration * rate)
	var samples := PackedFloat32Array()
	samples.resize(count)
	var bytes := PackedByteArray()
	bytes.resize(count * 2)
	var random := RandomNumberGenerator.new()
	random.seed = 1701
	var phase := 0.0
	var air := 0.0
	var rumble := 0.0
	var peak := 0.0
	for sample in range(count):
		var progress := float(sample) / float(count - 1)
		var seconds := float(sample) / rate
		var white := random.randf_range(-1.0, 1.0)
		var cutoff := lerpf(450.0, 2400.0, progress) if kind == "charge" else lerpf(4200.0, 280.0, progress)
		air = lerpf(air, white, 1.0 - exp(-TAU * cutoff / rate))
		rumble = lerpf(rumble, white, 1.0 - exp(-TAU * 110.0 / rate))
		var value := 0.0
		if kind == "charge":
			phase += TAU * lerpf(64.0, 108.0, progress) / rate
			var swell := smoothstep(0.0, 0.25, progress) * (0.25 + 0.75 * progress)
			var turbulence := 0.82 + 0.18 * sin(TAU * 11.0 * seconds)
			value = (air * 1.4 + rumble * 3.0 + sin(phase + air * 2.0) * 0.16) * swell * turbulence
		elif kind == "release":
			phase += TAU * lerpf(135.0, 38.0, sqrt(progress)) / rate
			var rush := smoothstep(0.0, 0.035, progress) * exp(-progress * 5.0)
			value = (air * 2.4 + rumble * 2.0 + sin(phase) * 0.22) * rush
		else:
			phase += TAU * (42.0 + 70.0 * exp(-seconds * 22.0)) / rate
			var body := sin(phase) * exp(-seconds * 6.0) * 0.65
			var crack := white * exp(-seconds * 95.0) * 0.7
			var debris := (air * 1.4 + rumble * 2.4) * exp(-seconds * 4.5)
			value = (body + crack + debris) * smoothstep(0.0, 0.004, seconds)
		# Short deterministic reflections thicken the tail without a looping bus effect.
		for delay in [0.047, 0.113]:
			var previous := sample - int(delay * rate)
			if previous >= 0: value += samples[previous] * 0.16
		value *= smoothstep(0.0, 0.003, seconds) * (1.0 - smoothstep(0.88, 1.0, progress))
		samples[sample] = value
		peak = maxf(peak, absf(value))
	for sample in range(count):
		bytes.encode_s16(sample * 2, int(samples[sample] * 0.72 / maxf(peak, 0.001) * 32767.0))
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = rate
	stream.data = bytes
	return stream


func _play_cue(kind: String, point: Vector3, pitch: float) -> void:
	if not sound_enabled: return
	var player: AudioStreamPlayer3D = _audio[kind]
	player.volume_db = clampf(sound_gain_db, -40.0, 12.0)
	player.global_position = point
	player.pitch_scale = clampf(pitch, 0.5, 2.0)
	player.play()
	_audio_events[kind] += 1
	audio_cue.emit(kind)


func _update_feedback(delta: float) -> void:
	_release_age += delta
	_hit_age += delta
	var compression := 0.0
	var core_radius := 0.0
	if _charging:
		var time := _cast_player.current_animation_position
		var gathering := smoothstep(GATHER_TIME, CONTRACT_TIME, time)
		compression = smoothstep(CONTRACT_TIME, RELEASE_TIME, time)
		_charge_radius = lerpf(0.62, 0.10, compression) * _shot_scale
		_charge_opacity = smoothstep(0.08, GATHER_TIME, time)
		core_radius = lerpf(0.05, 0.17, gathering) * lerpf(1.0, 0.62, compression)
		_charge.scale = Vector3.ONE * lerpf(0.08, 0.27, gathering) * lerpf(1.0, 0.40, compression) * _shot_scale
		_charge.get_node("Light").light_energy = lerpf(0.1, 2.4, gathering) + compression
	elif _charge != null:
		var residue := 1.0 - smoothstep(0.0, 0.22, _release_age)
		_charge_opacity = residue * residue
		_charge_radius = lerpf(0.10, 0.30, 1.0 - residue) * _shot_scale
		core_radius = 0.10 * residue
		_charge.visible = _charge_opacity > 0.001
		_charge.get_node("Light").visible = _charge.visible
		_charge.scale = Vector3.ONE * lerpf(0.11, 0.06, 1.0 - residue) * _shot_scale
		_charge.get_node("Light").light_energy = _charge_opacity * 2.5
	_set_charge_opacity(_charge_opacity)
	_charge_ring.global_position = _cast_hand.global_position
	var aim := _target - _cast_hand.global_position
	if aim.is_finite() and aim.length_squared() > 0.000001:
		_charge_ring.look_at(_target, Vector3.UP if absf(aim.normalized().y) < 0.99 else Vector3.RIGHT)
		_charge_ring.rotate_object_local(Vector3.RIGHT, PI * 0.5)
	_charge_ring.scale = Vector3.ONE * _charge_radius
	_charge_core.global_position = _cast_hand.global_position
	_charge_core.scale = Vector3.ONE * core_radius * _shot_scale
	var core_material := _charge_core.material_override as StandardMaterial3D
	var hot := _shot_tint.lerp(Color(1.0, 0.95, 0.85), 0.7)
	core_material.albedo_color = Color(hot.r * 2.5, hot.g * 2.5, hot.b * 2.5, _charge_opacity * 0.85)
	var flash := exp(-_hit_age * 18.0)
	_target_material.emission = Color("81c5d2").lerp(_hit_tint, flash)
	_target_material.emission_energy_multiplier = 0.35 + flash * 4.0 * _hit_strength
	_target_mesh.position = _target + Vector3.RIGHT * sin(_hit_age * 25.0) * exp(-_hit_age * 9.0) * 0.23 * _hit_strength
	var camera_hit := exp(-_hit_age * 13.0) * _hit_strength if camera_feedback_enabled else 0.0
	_camera.fov = CAMERA_FOV - compression * 1.5 + camera_hit * 2.2 if camera_feedback_enabled else CAMERA_FOV
	_camera.position = _camera_home + Vector3(-0.055, 0.035, 0.0) * camera_hit


func _set_charge_opacity(opacity: float) -> void:
	var flames := _charge.get_node("Flames") as GPUParticles3D
	var material := flames.draw_pass_1.surface_get_material(0) as ShaderMaterial
	material.set_shader_parameter("tint", Color(_shot_tint.r, _shot_tint.g, _shot_tint.b, opacity))
	var sparks := _charge.get_node("Sparks") as GPUParticles3D
	(sparks.draw_pass_1.surface_get_material(0) as StandardMaterial3D).albedo_color.a = opacity


func _cast_phase() -> String:
	if _cast_player.is_playing() and _cast_player.current_animation_position < GATHER_TIME: return "windup"
	if _charging:
		var time := _cast_player.current_animation_position
		if time < GATHER_TIME: return "windup"
		if time < CONTRACT_TIME: return "gather"
		return "contract"
	if _hit_age < 0.12: return "impact"
	if _hit_age < 0.52: return "expand"
	if _release_age < 0.45: return "release"
	if _cast_player.is_playing(): return "recover"
	return "idle"


func _build_charge_shapes() -> void:
	_charge_ring = CombatEffect.new()
	_charge_ring.name = "GatherSigil"
	_charge_ring.kind = "aura"
	_charge_ring.radius = 1.0
	_charge_ring.autoplay = false
	add_child(_charge_ring)
	var ring_material := StandardMaterial3D.new()
	ring_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	ring_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	ring_material.albedo_color.a = 0.0
	_charge_core = _sphere(self, "GatherCore", 1.0, Vector3.ZERO, ring_material.duplicate())
	for shape in [_charge_ring, _charge_core]:
		shape.scale = Vector3.ONE * 0.001
	_charge_core.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF


func get_state() -> Dictionary:
	var active: Array[Dictionary] = []
	if _projectiles != null:
		for projectile in _projectiles.get_children():
			if projectile.has_method("get_state"):
				var state: Dictionary = projectile.get_state()
				state["position"] = [projectile.global_position.x, projectile.global_position.y, projectile.global_position.z]
				active.append(state)
	return {"cast_count": cast_count, "release_count": release_count, "impact_count": impact_count,
		"active_projectiles": active, "mage_kind": character_source,
		"hand_position": [_cast_hand.global_position.x, _cast_hand.global_position.y, _cast_hand.global_position.z],
		"casting": _cast_player != null and _cast_player.is_playing(),
		"combo": _combo, "queued_casts": _queued_casts.size(), "active_ground_effects": _effects.get_child_count(),
		"phase": _cast_phase(), "cast_time": _cast_player.current_animation_position if not _cast_player.current_animation.is_empty() else 0.0,
		"charge_radius": _charge_radius, "charge_opacity": _charge_opacity,
		"release_time": RELEASE_TIME, "camera_feedback_enabled": camera_feedback_enabled,
		"audio_events": _audio_events.duplicate(), "sound_enabled": sound_enabled}


func _build_cast_animation() -> void:
	_cast_player = AnimationPlayer.new()
	_cast_player.name = "CastTimeline"
	add_child(_cast_player)
	var library := AnimationLibrary.new()
	var animation := Animation.new()
	if _imported_player != null:
		animation = _imported_player.get_animation(_imported_cast).duplicate(true)
		_rebase_bone_tracks(animation)
	animation.loop_mode = Animation.LOOP_NONE
	animation.length = CAST_DURATION
	var track := animation.add_track(Animation.TYPE_METHOD)
	animation.track_set_path(track, NodePath("."))
	animation.track_insert_key(track, 0.08, {"method": "begin_charge", "args": []})
	animation.track_insert_key(track, CONTRACT_TIME, {"method": "pulse_ground", "args": []})
	animation.track_insert_key(track, RELEASE_TIME, {"method": "release_spell", "args": []})
	animation.track_insert_key(track, CAST_DURATION - 0.05, {"method": "finish_cast", "args": []})
	if _arm != null:
		_value_track(animation, str(get_path_to(_arm)) + ":rotation:z", [0.0, 0.28, 0.78, RELEASE_TIME, 1.0, CAST_DURATION], [0.12, 0.85, 1.12, 1.82, 1.48, 0.12])
		_value_track(animation, str(get_path_to(_elbow)) + ":rotation:z", [0.0, 0.28, 0.78, RELEASE_TIME, 1.0, CAST_DURATION], [0.1, 0.95, 1.10, 0.0, 0.22, 0.1])
	library.add_animation("Cast", animation)
	_cast_player.add_animation_library("", library)
	_cast_player.animation_finished.connect(_on_cast_finished)


func _rebase_bone_tracks(animation: Animation) -> void:
	var source_root := _imported_player.get_node(_imported_player.root_node)
	for track in range(animation.get_track_count()):
		var original := animation.track_get_path(track)
		var target_node := source_root.get_node_or_null(NodePath(original.get_concatenated_names()))
		if target_node == null: continue
		var path := str(get_path_to(target_node))
		if original.get_subname_count() > 0: path += ":" + str(original.get_concatenated_subnames())
		animation.track_set_path(track, NodePath(path))
		var keys: Array[Dictionary] = []
		for key in range(animation.track_get_key_count(track)):
			var time := animation.track_get_key_time(track, key)
			var mapped := time * RELEASE_TIME / 0.65 if time <= 0.65 else RELEASE_TIME + (time - 0.65) * (CAST_DURATION - RELEASE_TIME) / 0.95
			keys.append({"time": mapped, "value": animation.track_get_key_value(track, key), "transition": animation.track_get_key_transition(track, key)})
		# Rebase paths and phase time only; preserve the animator's poses and interpolation.
		for key in range(animation.track_get_key_count(track) - 1, -1, -1): animation.track_remove_key(track, key)
		for key in keys: animation.track_insert_key(track, key.time, key.value, key.transition)


func _value_track(animation: Animation, path: String, times: Array, values: Array) -> void:
	var track := animation.add_track(Animation.TYPE_VALUE)
	animation.track_set_path(track, NodePath(path))
	animation.track_set_interpolation_type(track, Animation.INTERPOLATION_CUBIC)
	for index in range(times.size()):
		animation.track_insert_key(track, times[index], values[index])


func _build_mage() -> void:
	if mage_scene != null:
		var candidate := mage_scene.instantiate() as Node3D
		if candidate != null and _configure_imported_mage(candidate):
			# Asset root transforms carry import orientation, scale, and feet offsets.
			var placement := Node3D.new()
			placement.name = "Mage"
			placement.position = Vector3(-3.0, 0.0, 0.0)
			placement.rotation.y = -PI / 2.0
			placement.scale = Vector3.ONE * 1.45
			placement.add_child(candidate)
			add_child(placement)
			character_source = "imported_skeletal"
			if not _imported_idle.is_empty(): _imported_player.play(_imported_idle)
			return
		if candidate != null: candidate.free()
		_imported_player = null
		push_warning("Mage needs a Skeleton3D, %s bone, and %s animation; using articulated procedural wizard." % [hand_bone, cast_animation])
	_build_procedural_mage()


func _configure_imported_mage(candidate: Node3D) -> bool:
	var skeleton: Skeleton3D
	for child in candidate.find_children("*", "Skeleton3D", true, false):
		if child.find_bone(hand_bone) >= 0:
			skeleton = child
			break
	if skeleton == null: return false
	for child in candidate.find_children("*", "AnimationPlayer", true, false):
		for animation_name in child.get_animation_list():
			if str(animation_name).get_file() == cast_animation:
				_imported_player = child
				_imported_cast = animation_name
			if str(animation_name).get_file() == "Idle": _imported_idle = animation_name
	if _imported_player == null: return false
	var attachment := BoneAttachment3D.new()
	attachment.name = "CastSocket"
	attachment.bone_name = hand_bone
	skeleton.add_child(attachment)
	_cast_hand = Marker3D.new()
	_cast_hand.name = "CastOrigin"
	attachment.add_child(_cast_hand)
	return true


func _build_procedural_mage() -> void:
	var mage := Node3D.new()
	mage.name = "Mage"
	mage.position.x = -3.0
	add_child(mage)
	var cloth := _material(Color("27345d"), 0.15)
	var trim := _material(Color("c89d55"), 0.7)
	var skin := _material(Color("d2b38e"))
	var dark := _material(Color("101729"))
	var beard := _material(Color("b9ccd8"))
	_cylinder(mage, "Robe", 0.34, 0.67, 1.65, Vector3(0, 0.99, 0), cloth)
	_cylinder(mage, "Hem", 0.66, 0.68, 0.07, Vector3(0, 0.2, 0), trim)
	_cylinder(mage, "Belt", 0.44, 0.46, 0.09, Vector3(0, 1.35, 0), trim)
	_sphere(mage, "Head", 0.29, Vector3(0, 2.16, 0), skin)
	_sphere(mage, "Nose", 0.09, Vector3(0.29, 2.15, 0), skin)
	_cylinder(mage, "Beard", 0.2, 0.035, 0.48, Vector3(0.21, 1.87, 0), beard)
	for side in [-1.0, 1.0]:
		_sphere(mage, "Eye", 0.035, Vector3(0.255, 2.23, side * 0.11), dark)
		_sphere(mage, "Boot", 0.17, Vector3(0.1, 0.13, side * 0.28), dark)
	_cylinder(mage, "HatBrim", 0.65, 0.65, 0.07, Vector3(0, 2.41, 0), cloth)
	_cylinder(mage, "Hat", 0.015, 0.46, 0.95, Vector3(-0.08, 2.9, 0), cloth)
	_cylinder(mage, "HatBand", 0.42, 0.45, 0.12, Vector3(0, 2.5, 0), trim)
	_arm = Node3D.new()
	_arm.name = "CastArm"
	_arm.position = Vector3(0.0, 1.9, 0.43)
	_arm.rotation.z = 0.12
	mage.add_child(_arm)
	_cylinder(_arm, "Sleeve", 0.21, 0.15, 0.6, Vector3(0, -0.25, 0), cloth)
	_elbow = Node3D.new()
	_elbow.name = "Elbow"
	_elbow.position.y = -0.52
	_elbow.rotation.z = 0.1
	_arm.add_child(_elbow)
	_cylinder(_elbow, "Forearm", 0.15, 0.12, 0.49, Vector3(0, -0.23, 0), cloth)
	_sphere(_elbow, "Hand", 0.12, Vector3(0, -0.51, 0), skin)
	_cast_hand = Marker3D.new()
	_cast_hand.name = "CastOrigin"
	_cast_hand.position = Vector3(0, -0.63, 0)
	_elbow.add_child(_cast_hand)
	_cylinder(mage, "OtherSleeve", 0.19, 0.14, 0.7, Vector3(0, 1.54, -0.47), cloth)
	_sphere(mage, "OtherHand", 0.11, Vector3(0, 1.16, -0.47), skin)
	_cylinder(mage, "Staff", 0.045, 0.045, 2.25, Vector3(0.11, 1.15, -0.5), trim)
	_sphere(mage, "StaffCrystal", 0.16, Vector3(0.11, 2.38, -0.5), _material(Color("71bde9"), 0.0, 2.0))


func _build_arena() -> void:
	var world := WorldEnvironment.new()
	world.name = "Atmosphere"
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color("0a1022")
	sky_material.sky_horizon_color = Color("485365")
	sky_material.ground_bottom_color = Color("0b1020")
	sky_material.ground_horizon_color = Color("29374b")
	sky_material.sky_energy_multiplier = 0.55
	var sky := Sky.new()
	sky.sky_material = sky_material
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("7f9ac5")
	environment.ambient_light_energy = 0.30
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	environment.glow_enabled = true
	environment.fog_enabled = true
	environment.fog_light_color = Color("18243a")
	environment.fog_density = 0.004
	world.environment = environment
	add_child(world)
	var floor_mat := _material(Color("263142"), 0.12)
	floor_mat.roughness = 0.72
	var stone_noise := FastNoiseLite.new()
	stone_noise.seed = 421
	stone_noise.frequency = 0.7
	var stone := NoiseTexture2D.new()
	stone.noise = stone_noise
	stone.as_normal_map = true
	stone.bump_strength = 0.15
	floor_mat.normal_enabled = true
	floor_mat.normal_texture = stone
	floor_mat.uv1_scale = Vector3(5, 5, 1)
	var stone_color := NoiseTexture2D.new()
	stone_color.noise = stone_noise
	var stone_ramp := Gradient.new()
	stone_ramp.colors = PackedColorArray([Color("1a2432"), Color("586272")])
	stone_color.color_ramp = stone_ramp
	floor_mat.albedo_color = Color.WHITE
	floor_mat.albedo_texture = stone_color
	_cylinder(self, "Foundation", 10.1, 10.35, 0.35, Vector3(0, -0.64, 0), floor_mat)
	_cylinder(self, "LowerStep", 9.85, 10.1, 0.22, Vector3(0, -0.36, 0), floor_mat)
	_cylinder(self, "Arena", 9.5, 9.5, 0.25, Vector3(0, -0.125, 0), floor_mat)
	for radius in [8.8, 7.9, 5.9]:
		_ring(self, radius, Vector3(0, 0.005, 0), Color("253044"), 0.22)
	var bronze := _material(Color("807052"), 0.72)
	var seam_material := _material(Color("0c1421"))
	for index in range(32):
		var angle := TAU * float(index) / 32.0
		var seam := BoxMesh.new()
		seam.size = Vector3(0.018, 0.008, 3.5)
		var joint := _mesh(self, "StoneJoint", seam, Vector3(sin(angle) * 7.45, 0.005, cos(angle) * 7.45), seam_material)
		joint.rotation.y = angle
	for index in range(12):
		var angle := TAU * float(index) / 12.0
		var point := Vector3(cos(angle) * 8.6, 0.0, sin(angle) * 8.6)
		# The foreground opening keeps the gameplay camera and spell silhouette clear.
		if point.z > 3.0: continue
		_cylinder(self, "ColumnFoot", 0.65, 0.78, 0.28, point + Vector3.UP * 0.14, bronze)
		_cylinder(self, "Column", 0.35, 0.48, 4.8, point + Vector3.UP * 2.60, floor_mat)
		_cylinder(self, "Capital", 0.70, 0.55, 0.25, point + Vector3.UP * 4.93, bronze)
		_ring(self, 0.48, point + Vector3.UP * 1.0, Color("486b86"), 0.35)
		_ring(self, 0.39, point + Vector3.UP * 4.20, Color("486b86"), 0.35)
	_ring(self, 8.65, Vector3(0, 5.12, 0), Color("394966"), 0.15)
	var rim := OmniLight3D.new()
	rim.name = "RitualRim"
	rim.position = Vector3(-3.0, 3.8, -3.0)
	rim.light_color = Color("6ca8db")
	rim.light_energy = 2.1
	rim.omni_range = 8.0
	add_child(rim)
	for x in [-3.0, 3.0]:
		_ring(self, 1.25, Vector3(x, 0.015, 0), Color("38566b"), 0.35)
		_ring(self, 1.05, Vector3(x, 0.017, 0), Color("294053"), 0.2)
	_cylinder(self, "TargetPlinth", 0.62, 0.8, 0.33, Vector3(3, 0.13, 0), floor_mat)
	_cylinder(self, "TargetPillar", 0.17, 0.3, 1.0, Vector3(3, 0.72, 0), _material(Color("35465e"), 0.7))
	_target_material = _material(Color("81c5d2"), 0.1, 0.35)
	var crystal := SphereMesh.new()
	crystal.radius = 0.28
	crystal.height = 0.72
	crystal.radial_segments = 6
	crystal.rings = 4
	_target_mesh = _mesh(self, "TargetCrystal", crystal, _target, _target_material)
	var target_body := StaticBody3D.new()
	target_body.name = "HitBody"
	target_body.collision_layer = 1
	target_body.collision_mask = 0
	_target_mesh.add_child(target_body)
	var target_shape := CollisionShape3D.new()
	target_shape.name = "HitShape"
	var sphere := SphereShape3D.new()
	sphere.radius = 0.3
	target_shape.shape = sphere
	target_body.add_child(target_shape)
	for index in range(3):
		var point := Vector3(-4.8 + index * 4.8, 0.0, -4.4)
		_cylinder(self, "Brazier", 0.48, 0.65, 1.0, point + Vector3.UP * 0.45, floor_mat)
		_ring(self, 0.5, point + Vector3.UP * 0.97, Color("a79369"), 0.4)
		var fire := FireEffect.create(Color("c99a69"), 20)
		fire.name = "PedestalFire%d" % index
		fire.position = point + Vector3.UP * 1.0
		fire.scale = Vector3.ONE * 0.35
		add_child(fire)
		fire.get_node("Light").light_energy = 0.2
		var flames := fire.get_node("Flames") as GPUParticles3D
		var flame_material := flames.draw_pass_1.surface_get_material(0) as ShaderMaterial
		flame_material.set_shader_parameter("intensity", 0.7)
	var key := DirectionalLight3D.new()
	key.name = "Moonlight"
	key.rotation_degrees = Vector3(-48, -25, 0)
	key.light_color = Color("e1d7c7")
	key.light_energy = 0.85
	key.shadow_enabled = true
	add_child(key)
	var fill := OmniLight3D.new()
	fill.position = Vector3(-4, 4, 4)
	fill.light_color = Color("ffd3a4")
	fill.light_energy = 0.75
	fill.omni_range = 10.0
	add_child(fill)
	_camera = Camera3D.new()
	_camera.name = "Camera"
	_camera.position = _camera_home
	_camera.fov = CAMERA_FOV
	add_child(_camera)
	_camera.look_at(Vector3(0.2, 1.25, -0.1))
	_camera.current = true


func _build_overlay() -> void:
	var layer := CanvasLayer.new()
	layer.name = "Caption"
	add_child(layer)
	var title := Label.new()
	title.position = Vector2(30, 25)
	title.text = "ARCANE / FIRE STUDY"
	title.add_theme_font_size_override("font_size", 22)
	title.modulate = Color("e1e8f4")
	layer.add_child(title)
	_status = Label.new()
	_status.position = Vector2(31, 58)
	_status.add_theme_font_size_override("font_size", 13)
	_status.modulate = Color("8198b7")
	layer.add_child(_status)
	var controls := Label.new()
	controls.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	controls.offset_left = 31
	controls.offset_top = -42
	controls.text = "SPACE  CAST     Q  EMBER CHAIN     E  ARCANE SURGE     1 / 2 / 3  ELEMENT"
	controls.add_theme_font_size_override("font_size", 14)
	controls.modulate = Color("a6b7cc")
	layer.add_child(controls)


func _material(color: Color, metallic: float = 0.0, emission: float = 0.0) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.metallic = metallic
	material.roughness = 0.56
	if emission > 0:
		material.emission_enabled = true
		material.emission = color
		material.emission_energy_multiplier = emission
	return material


func _cylinder(parent: Node3D, label: String, top: float, bottom: float, height: float, point: Vector3, material: Material) -> MeshInstance3D:
	var mesh := CylinderMesh.new()
	mesh.top_radius = top
	mesh.bottom_radius = bottom
	mesh.height = height
	mesh.radial_segments = 32
	return _mesh(parent, label, mesh, point, material)


func _sphere(parent: Node3D, label: String, radius: float, point: Vector3, material: Material) -> MeshInstance3D:
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2.0
	return _mesh(parent, label, mesh, point, material)


func _ring(parent: Node3D, radius: float, point: Vector3, color: Color, energy: float) -> void:
	var mesh := TorusMesh.new()
	mesh.inner_radius = radius - 0.018
	mesh.outer_radius = radius + 0.018
	mesh.rings = 96
	mesh.ring_segments = 6
	_mesh(parent, "Inlay", mesh, point, _material(color, 0.35, energy))


func _mesh(parent: Node3D, label: String, geometry: Mesh, point: Vector3, material: Material) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = label
	instance.mesh = geometry
	instance.material_override = material
	instance.position = point
	parent.add_child(instance)
	return instance
