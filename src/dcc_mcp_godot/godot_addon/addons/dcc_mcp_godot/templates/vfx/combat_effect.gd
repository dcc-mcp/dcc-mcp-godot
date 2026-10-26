extends Node3D
## Cosmetic XZ-plane effects, in metres. Combat rules stay with the caller.

signal finished

const RING_SHADER = preload("combat_ring.gdshader")
const STOP_FADE := 0.25
const PULSE_DURATION := 0.78

@export_enum("slash", "impact", "aura") var kind: String = "aura"
@export var tint: Color = Color("55d9ff")
## Nominal radius; an aura pulse reaches at most 1.35 times this footprint.
@export_range(0.1, 20.0, 0.1) var radius: float = 1.5
@export_range(0.05, 10.0, 0.05) var duration: float = 0.6
@export var autoplay: bool = true
@export var auto_free: bool = false

var _playing := false
var _stopping := false
var _age := 0.0
var _stop_age := 0.0
var _stop_opacity := 0.0
var _stop_accent := 0.0
var _stop_scale := 1.0
var _visual_scale := 1.0
var _pulse_age := -1.0
var _pulse_speed := 1.0
var _pulse_start_scale := 1.0
var _phase := 0.0
var _material: ShaderMaterial
var _light: OmniLight3D
var _motes: GPUParticles3D
var _mote_material: StandardMaterial3D


func _ready() -> void:
	_build_visuals()
	visible = false
	set_process(false)
	if autoplay: play()


func play() -> bool:
	if not is_inside_tree() or is_queued_for_deletion() or not _valid_configuration():
		return false
	if _material == null: _build_visuals()
	_playing = true
	_stopping = false
	_age = 0.0
	_stop_age = 0.0
	_pulse_age = -1.0
	_phase = 0.0
	visible = true
	_set_visual_scale(0.18 if kind == "aura" else 1.0)
	_material.set_shader_parameter("effect_kind", ["slash", "impact", "aura"].find(kind))
	_material.set_shader_parameter("tint", tint)
	_material.set_shader_parameter("progress", 0.0)
	_material.set_shader_parameter("elapsed", 0.0)
	_material.set_shader_parameter("opacity", 0.0)
	_material.set_shader_parameter("accent", 0.0)
	_light.light_color = tint
	_light.light_energy = 0.0
	var motion := _motes.process_material as ParticleProcessMaterial
	motion.emission_ring_radius = radius * 0.90
	motion.emission_ring_inner_radius = radius * 0.70
	motion.color = tint
	_motes.visibility_aabb = AABB(Vector3(-radius, -0.1, -radius) * 1.2, Vector3(radius * 2.4, 2.0, radius * 2.4))
	_mote_material.albedo_color.a = 0.0
	_motes.visible = kind == "aura"
	_motes.emitting = kind == "aura"
	if _motes.emitting: _motes.restart()
	set_process(true)
	return true


func stop() -> void:
	if not _playing or _stopping: return
	_stopping = true
	_stop_age = 0.0
	_stop_opacity = float(_material.get_shader_parameter("opacity"))
	_stop_accent = float(_material.get_shader_parameter("accent"))
	_stop_scale = _visual_scale
	_motes.emitting = false


func pulse(playback_speed: float = 1.0) -> bool:
	if not _playing or _stopping or kind != "aura" or _pulse_age >= 0.0 or not is_finite(playback_speed) or playback_speed <= 0.0:
		return false
	_pulse_age = 0.0
	_pulse_speed = playback_speed
	_pulse_start_scale = _visual_scale
	return true


func get_state() -> Dictionary:
	return {"playing": _playing, "phase": _phase, "kind": kind, "stopping": _stopping,
		"visual_scale": _visual_scale, "footprint_radius": radius * _visual_scale,
		"pulse_phase": _pulse_age / PULSE_DURATION if _pulse_age >= 0.0 else -1.0}


func _process(delta: float) -> void:
	_age += delta
	_phase = clampf(_age / duration, 0.0, 1.0) if kind != "aura" else fmod(_age / 3.0, 1.0)
	var opacity := minf(_age / 0.12, 1.0)
	var accent := 0.0
	if _stopping:
		_stop_age += delta
		var retreat := smoothstep(0.0, STOP_FADE, _stop_age)
		opacity = _stop_opacity * (1.0 - retreat)
		accent = _stop_accent * (1.0 - retreat)
		if kind == "aura": _set_visual_scale(_stop_scale * lerpf(1.0, 0.2, retreat))
		if _stop_age >= STOP_FADE:
			_finish()
			return
	elif kind != "aura" and _age >= duration:
		_finish()
		return
	elif kind == "aura":
		if _pulse_age >= 0.0:
			_pulse_age += delta * _pulse_speed
			if _pulse_age < 0.22:
				_set_visual_scale(lerpf(_pulse_start_scale, 0.48, smoothstep(0.0, 0.22, _pulse_age)))
				accent = smoothstep(0.0, 0.22, _pulse_age) * 0.4
			elif _pulse_age < 0.36:
				var expansion := 1.0 - pow(1.0 - clampf((_pulse_age - 0.22) / 0.14, 0.0, 1.0), 3.0)
				_set_visual_scale(lerpf(0.48, 1.35, expansion))
				accent = lerpf(0.4, 1.0, expansion)
			else:
				var settle := smoothstep(0.36, PULSE_DURATION, _pulse_age)
				_set_visual_scale(lerpf(1.35, 1.0, settle))
				accent = 1.0 - settle
				if _pulse_age >= PULSE_DURATION: _pulse_age = -1.0
		else:
			var opening := 1.0 - pow(1.0 - clampf(_age / 0.22, 0.0, 1.0), 3.0)
			_set_visual_scale(lerpf(0.18, 1.06, opening) if _age < 0.22 else lerpf(1.06, 1.0, smoothstep(0.22, 0.4, _age)))
	_material.set_shader_parameter("progress", _phase)
	_material.set_shader_parameter("elapsed", _age)
	_material.set_shader_parameter("opacity", opacity)
	_material.set_shader_parameter("accent", accent)
	_mote_material.albedo_color.a = 0.8 * opacity
	_light.light_energy = opacity * (0.45 + accent * 0.65 if kind == "aura" else (1.0 - _phase) * 0.75)


func _set_visual_scale(value: float) -> void:
	_visual_scale = value
	get_node("Surface").scale = Vector3(radius * value, 1.0, radius * value)
	_motes.scale = Vector3.ONE * value
	_light.omni_range = radius * value * 2.0


func _finish() -> void:
	_playing = false
	_stopping = false
	_pulse_age = -1.0
	visible = false
	_motes.emitting = false
	_motes.visible = false
	_mote_material.albedo_color.a = 0.0
	set_process(false)
	finished.emit()
	if auto_free and not _playing: queue_free()


func _valid_configuration() -> bool:
	for channel in [tint.r, tint.g, tint.b, tint.a]:
		if not is_finite(channel) or channel < 0.0: return false
	return kind in ["slash", "impact", "aura"] and tint.a <= 1.0 and is_finite(radius) and radius >= 0.1 and radius <= 20.0 and is_finite(duration) and duration >= 0.05 and duration <= 10.0


func _build_visuals() -> void:
	_material = ShaderMaterial.new()
	_material.shader = RING_SHADER
	_material.resource_local_to_scene = true
	# Explicit uniforms keep dummy-renderer saves and native rendering consistent.
	_material.set_shader_parameter("effect_kind", 2)
	_material.set_shader_parameter("tint", tint)
	_material.set_shader_parameter("progress", 0.0)
	_material.set_shader_parameter("elapsed", 0.0)
	_material.set_shader_parameter("opacity", 0.0)
	_material.set_shader_parameter("accent", 0.0)
	var surface := MeshInstance3D.new()
	surface.name = "Surface"
	var plane := PlaneMesh.new()
	plane.size = Vector2(2.0, 2.0)
	surface.mesh = plane
	surface.material_override = _material
	surface.position.y = 0.025
	surface.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(surface)
	_light = OmniLight3D.new()
	_light.name = "Glow"
	_light.position.y = 0.35
	_light.shadow_enabled = false
	add_child(_light)
	_motes = GPUParticles3D.new()
	_motes.name = "Motes"
	_motes.amount = 20
	_motes.lifetime = 0.8
	_motes.local_coords = true
	_motes.emitting = false
	var motion := ParticleProcessMaterial.new()
	motion.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_RING
	motion.emission_ring_axis = Vector3.UP
	motion.emission_ring_height = 0.02
	motion.direction = Vector3.UP
	motion.spread = 12.0
	motion.initial_velocity_min = 0.25
	motion.initial_velocity_max = 0.55
	motion.gravity = Vector3.ZERO
	motion.scale_min = 0.55
	motion.scale_max = 1.0
	var curve := Curve.new()
	curve.add_point(Vector2(0.0, 0.0))
	curve.add_point(Vector2(0.18, 1.0))
	curve.add_point(Vector2(1.0, 0.0))
	var scale_curve := CurveTexture.new()
	scale_curve.curve = curve
	motion.scale_curve = scale_curve
	_motes.process_material = motion
	var glow := StandardMaterial3D.new()
	_mote_material = glow
	glow.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	glow.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glow.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	glow.vertex_color_use_as_albedo = true
	glow.albedo_color = Color(1.7, 1.7, 1.7, 0.8)
	var dot := QuadMesh.new()
	dot.size = Vector2(0.018, 0.04)
	dot.material = glow
	_motes.draw_pass_1 = dot
	add_child(_motes)
