extends Node3D
## Single-use world-space spell. All effects stay owned by this runtime node.

signal impacted(position: Vector3)

const FIRE = preload("dynamic_fire.gd")
const TRAIL_SHADER = preload("spell_trail.gdshader")
const MAX_LIFETIME := 30.0
const TAIL_TIME := 0.95
const MAX_TRAIL_SAMPLES := 32
const TRAIL_FADE := 0.28

@export_range(0.1, 100.0, 0.1) var speed: float = 8.0
@export_range(0.1, 30.0, 0.1) var lifetime: float = 4.0
@export var tint: Color = Color(1.0, 0.24, 0.035)
@export_flags_3d_physics var collision_mask: int = 1
@export_range(0.25, 3.0, 0.05) var visual_scale: float = 1.0
@export_range(0.2, 6.0, 0.1) var trail_length: float = 2.2
@export_range(0.25, 3.0, 0.05) var impact_strength: float = 1.0
@export_range(0.0, 0.4, 0.01) var acceleration_time: float = 0.12
@export var impact_on_arrival: bool = true

var _launched := false
var _did_impact := false
var _target := Vector3.ZERO
var _age := 0.0
var _cleanup_at := MAX_LIFETIME
var _tail_time := TAIL_TIME
var _impact_age := 0.0
var _impact_kind := ""
var _stop_age := -1.0
var _core: Node3D
var _burst: Node3D
var _head: MeshInstance3D
var _shock: MeshInstance3D
var _rays: MeshInstance3D
var _trail: MeshInstance3D
var _trail_mesh: ImmediateMesh
var _points := PackedVector3Array()
var _excluded_bodies: Array[RID] = []


func _ready() -> void:
	set_physics_process(false)


func launch(target: Vector3, excluded_bodies: Array[RID] = []) -> void:
	if _launched or not is_inside_tree() or not target.is_finite():
		return
	if not is_finite(speed) or speed <= 0.0 or not is_finite(lifetime) or lifetime <= 0.0:
		return
	if not is_finite(visual_scale) or not is_finite(trail_length) or not is_finite(impact_strength) or not is_finite(acceleration_time):
		return
	visual_scale = clampf(visual_scale, 0.25, 3.0)
	trail_length = clampf(trail_length, 0.2, 6.0)
	impact_strength = clampf(impact_strength, 0.25, 3.0)
	acceleration_time = clampf(acceleration_time, 0.0, 0.4)
	_launched = true
	_target = target
	_cleanup_at = clampf(lifetime, 0.1, MAX_LIFETIME)
	_tail_time = minf(TAIL_TIME, _cleanup_at * 0.25)
	_excluded_bodies = excluded_bodies.duplicate()
	var ancestor := get_parent()
	while ancestor != null:
		if ancestor is CollisionObject3D:
			_excluded_bodies.append(ancestor.get_rid())
		ancestor = ancestor.get_parent()
	var launch_transform := global_transform
	top_level = true
	global_transform = launch_transform
	_trail_mesh = ImmediateMesh.new()
	_trail = MeshInstance3D.new()
	_trail.name = "FlightRibbon"
	_trail.mesh = _trail_mesh
	_trail.material_override = _material(0, 1.8)
	_trail.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_trail)
	# World vertices remain stable when the projectile or its original parent moves.
	_trail.top_level = true
	_trail.global_transform = Transform3D.IDENTITY
	_points.append(global_position)
	_head = _sphere("HotCore", 1, 2.6)
	_head.scale = Vector3(0.13, 0.13, 0.22) * visual_scale
	if global_position.distance_squared_to(target) > 0.0001:
		_head.look_at(target, Vector3.UP if absf((target - global_position).normalized().y) < 0.99 else Vector3.RIGHT)
	_core = FIRE.create(tint, 14)
	_core.name = "SpellCore"
	_core.scale = Vector3.ONE * 0.48 * visual_scale
	add_child(_core)
	for child in _core.get_children():
		if child is GPUParticles3D:
			child.local_coords = true
			child.lifetime = 0.25
			child.preprocess = 0.25
			var motion := child.process_material as ParticleProcessMaterial
			motion.spread = 180.0
			motion.initial_velocity_min = 0.08
			motion.initial_velocity_max = 0.22
			motion.gravity = Vector3.ZERO
			child.restart()
	var light := _core.get_node("Light") as OmniLight3D
	light.position = Vector3.ZERO
	light.light_energy = 1.8
	light.omni_range = 2.5 * visual_scale
	set_physics_process(true)


func get_state() -> Dictionary:
	return {"launched": _launched, "impacted": _did_impact, "impact_kind": _impact_kind, "target": _target, "age": _age}


func _physics_process(delta: float) -> void:
	_age += delta
	if _age >= _cleanup_at:
		queue_free()
		return
	if _did_impact:
		_impact_age += delta
		_update_impact()
		_update_trail()
		return
	if _stop_age >= 0.0:
		_update_trail()
		return
	# Reserve a tail interval within the total lifetime, even for missed targets.
	if _age >= _cleanup_at - _tail_time:
		_impact_kind = "expired"
		_stop_flight()
		_head.visible = false
		_update_trail()
		return
	var origin := global_position
	var offset := _target - origin
	var distance := offset.length()
	var acceleration := 1.0 if acceleration_time <= 0.0 else lerpf(0.3, 1.0, clampf(_age / acceleration_time, 0.0, 1.0))
	var travel := minf(speed * acceleration * delta, distance)
	var next := origin + offset.normalized() * travel
	if travel > 0.00001:
		var query := PhysicsRayQueryParameters3D.create(origin, next, collision_mask)
		query.exclude = _excluded_bodies
		query.collide_with_areas = true
		var hit := get_world_3d().direct_space_state.intersect_ray(query)
		if not hit.is_empty():
			_impact(hit["position"], "collision")
			return
	global_position = next
	_sample_trail()
	_update_trail()
	if distance <= travel + 0.015:
		if impact_on_arrival:
			_impact(_target, "destination")
		else:
			_impact_kind = "missed"
			_stop_flight()
			_head.visible = false
			_cleanup_at = minf(_cleanup_at, _age + _tail_time)


func _sample_trail() -> void:
	if _points.is_empty() or _points[-1].distance_squared_to(global_position) > 0.000001:
		_points.append(global_position)
	while _points.size() > MAX_TRAIL_SAMPLES:
		_points.remove_at(0)
	# Keep a world-distance budget; clipping the oldest segment avoids tail popping.
	var length := 0.0
	for index in range(_points.size() - 1, 0, -1):
		var segment := _points[index].distance_to(_points[index - 1])
		if length + segment > trail_length:
			_points[index - 1] = _points[index].lerp(_points[index - 1], (trail_length - length) / segment)
			for unused in range(index - 1):
				_points.remove_at(0)
			break
		length += segment


func _update_trail() -> void:
	var fade := 1.0 if _stop_age < 0.0 else maxf(0.0, 1.0 - (_age - _stop_age) / TRAIL_FADE)
	_trail.visible = fade > 0.0
	(_trail.material_override as ShaderMaterial).set_shader_parameter("opacity", fade)
	_trail_mesh.clear_surfaces()
	var camera := get_viewport().get_camera_3d()
	if _points.size() < 2 or fade <= 0.0 or camera == null:
		return
	var total := 0.0
	for index in range(1, _points.size()):
		total += _points[index].distance_to(_points[index - 1])
	if total <= 0.0001:
		return
	var walked := 0.0
	_trail_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)
	for index in range(_points.size()):
		if index > 0:
			walked += _points[index].distance_to(_points[index - 1])
		var u := walked / total
		var tangent := (_points[mini(index + 1, _points.size() - 1)] - _points[maxi(index - 1, 0)]).normalized()
		var side := tangent.cross(camera.global_position - _points[index]).normalized()
		if side.length_squared() < 0.001:
			side = camera.global_basis.x
		var width := (0.008 + 0.19 * pow(u, 0.7)) * visual_scale * minf(1.0, total / 0.35)
		_trail_mesh.surface_set_uv(Vector2(u, 0.0))
		_trail_mesh.surface_add_vertex(_points[index] - side * width)
		_trail_mesh.surface_set_uv(Vector2(u, 1.0))
		_trail_mesh.surface_add_vertex(_points[index] + side * width)
	_trail_mesh.surface_end()


func _stop_flight() -> void:
	if _stop_age >= 0.0:
		return
	_stop_age = _age
	FIRE.set_emitting(_core, false)


func _impact(at: Vector3, kind: String) -> void:
	if _did_impact:
		return
	_did_impact = true
	_impact_kind = kind
	global_position = at
	_sample_trail()
	_stop_flight()
	_burst = FIRE.create(tint, 32)
	_burst.name = "ImpactBurst"
	add_child(_burst)
	for child in _burst.get_children():
		if child is GPUParticles3D:
			child.emitting = false
			child.preprocess = 0.0
			child.one_shot = true
			child.explosiveness = 1.0
			child.lifetime = 0.48 if child.name == "Flames" else 0.80
			var motion := child.process_material as ParticleProcessMaterial
			motion.direction = Vector3.UP
			motion.spread = 180.0
			motion.initial_velocity_min = 0.8 * impact_strength
			motion.initial_velocity_max = 2.8 * impact_strength
			motion.gravity = Vector3(0.0, -1.2, 0.0)
			motion.scale_min *= (1.2 if child.name == "Flames" else 0.6) * visual_scale
			motion.scale_max *= (1.45 if child.name == "Flames" else 0.6) * visual_scale
			motion.scale_curve = FIRE._curve_texture(PackedVector2Array([Vector2(0, 0.4), Vector2(0.22, 1), Vector2(1, 0)]))
			child.restart()
			child.emitting = true
	var burst_material := _burst.get_node("Flames").material_override as ShaderMaterial
	burst_material.set_shader_parameter("tint", Color(tint.r, tint.g, tint.b, tint.a * 0.6))
	burst_material.set_shader_parameter("intensity", 1.4)
	_shock = _sphere("ImpactEnvelope", 2, 1.7)
	_rays = MeshInstance3D.new()
	_rays.name = "ImpactRays"
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE * 2.0
	_rays.mesh = quad
	_rays.material_override = _material(3, 1.2)
	_rays.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_rays)
	_update_impact()
	_cleanup_at = minf(_cleanup_at, _age + _tail_time)
	impacted.emit(at)


func _update_impact() -> void:
	# A short hot flash gives way to the expanding colored envelope, then embers.
	var flash := 1.0 - smoothstep(0.035, 0.11, _impact_age)
	_head.visible = flash > 0.0
	_head.scale = Vector3.ONE * lerpf(0.16, 0.40, minf(_impact_age / 0.035, 1.0)) * visual_scale * sqrt(impact_strength)
	(_head.material_override as ShaderMaterial).set_shader_parameter("opacity", flash)
	var expansion := 1.0 - pow(1.0 - clampf(_impact_age / 0.38, 0.0, 1.0), 3.0)
	_shock.scale = Vector3.ONE * (0.18 + expansion * 2.15) * visual_scale * sqrt(impact_strength)
	(_shock.material_override as ShaderMaterial).set_shader_parameter("opacity", (1.0 - smoothstep(0.10, 0.46, _impact_age)) * 0.38)
	_rays.scale = Vector3.ONE * (0.5 + expansion * 2.6) * visual_scale
	(_rays.material_override as ShaderMaterial).set_shader_parameter("opacity", (1.0 - smoothstep(0.035, 0.20, _impact_age)) * 0.65)
	var camera := get_viewport().get_camera_3d()
	if camera != null and camera.global_position.distance_squared_to(global_position) > 0.001:
		var direction := (camera.global_position - global_position).normalized()
		_rays.look_at(camera.global_position, Vector3.UP if absf(direction.y) < 0.99 else Vector3.RIGHT)
	var light := _burst.get_node("Light") as OmniLight3D
	light.position = Vector3.ZERO
	light.light_energy = 3.8 * flash * impact_strength
	light.omni_range = 4.0 * visual_scale


func _material(mode: int, intensity: float) -> ShaderMaterial:
	var material := ShaderMaterial.new()
	material.shader = TRAIL_SHADER
	# Explicit values survive headless scene packing without null shader defaults.
	material.set_shader_parameter("tint", tint)
	material.set_shader_parameter("mode", mode)
	material.set_shader_parameter("intensity", intensity)
	material.set_shader_parameter("opacity", 1.0)
	return material


func _sphere(label: String, mode: int, intensity: float) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = label
	var sphere := SphereMesh.new()
	sphere.radius = 1.0
	sphere.height = 2.0
	sphere.radial_segments = 24
	sphere.rings = 12
	instance.mesh = sphere
	instance.material_override = _material(mode, intensity)
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(instance)
	return instance
