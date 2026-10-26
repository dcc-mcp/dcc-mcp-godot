@tool
extends Node3D
## Original particle fire builder. Returned nodes have no script dependency.

const FIRE_SHADER = preload("dynamic_fire.gdshader")
static var _fallback_texture: Texture2D
static var _heat_ramp: GradientTexture1D
static var _spark_texture: Texture2D

@export var tint: Color = Color("ff6018")
@export_range(8, 256, 1) var amount: int = 48
@export var fire_texture: Texture2D


func _ready() -> void:
	if Engine.is_editor_hint(): return
	var contents := create(tint, amount, fire_texture)
	for child in contents.get_children():
		contents.remove_child(child)
		add_child(child)
	contents.free()


static func create(tint: Color, amount: int = 48, texture: Texture2D = null) -> Node3D:
	var effect := Node3D.new()
	effect.name = "DynamicFire"
	var flames := GPUParticles3D.new()
	flames.name = "Flames"
	flames.amount = clampi(amount, 1, 512)
	flames.lifetime = 0.95
	flames.preprocess = 0.65
	flames.local_coords = false
	flames.randomness = 0.24
	flames.visibility_aabb = AABB(Vector3(-3.0, -2.0, -3.0), Vector3(6.0, 7.0, 6.0))
	flames.draw_order = GPUParticles3D.DRAW_ORDER_VIEW_DEPTH
	var motion := ParticleProcessMaterial.new()
	motion.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	motion.emission_sphere_radius = 0.15
	motion.direction = Vector3.UP
	motion.spread = 23.0
	motion.initial_velocity_min = 0.95
	motion.initial_velocity_max = 1.7
	motion.gravity = Vector3(0.0, 0.45, 0.0)
	motion.scale_min = 0.40
	motion.scale_max = 0.78
	motion.angle_min = -180.0
	motion.angle_max = 180.0
	motion.angular_velocity_min = -40.0
	motion.angular_velocity_max = 40.0
	motion.scale_curve = _curve_texture(PackedVector2Array([
		Vector2(0.0, 0.28), Vector2(0.18, 0.85), Vector2(0.55, 1.0), Vector2(1.0, 0.30)
	]))
	flames.process_material = motion
	var material := ShaderMaterial.new()
	material.shader = FIRE_SHADER
	# Explicit values survive headless saving without querying GPU shader defaults.
	material.set_shader_parameter("fire_texture", texture if texture != null else _get_fallback_texture())
	material.set_shader_parameter("heat_ramp", _get_heat_ramp())
	material.set_shader_parameter("tint", tint)
	material.set_shader_parameter("intensity", 2.8)
	material.set_shader_parameter("texture_scale", 1.65)
	material.set_shader_parameter("scroll_speed", 0.22)
	material.set_shader_parameter("edge_softness", 0.13)
	material.set_shader_parameter("density", 0.62)
	material.set_shader_parameter("dissolve", 0.0)
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE
	quad.material = material
	flames.draw_pass_1 = quad
	flames.material_override = material
	effect.add_child(flames)
	effect.add_child(_create_sparks(tint, maxi(6, flames.amount / 3)))
	var light := OmniLight3D.new()
	light.name = "Light"
	light.light_color = tint
	light.light_energy = 1.5
	light.omni_range = 3.0
	light.shadow_enabled = false
	light.position.y = 0.45
	effect.add_child(light)
	return effect


static func set_emitting(effect: Node3D, enabled: bool) -> void:
	for child in effect.get_children():
		if child is GPUParticles3D:
			child.emitting = enabled
			if enabled:
				child.restart()
		elif child is Light3D:
			child.visible = enabled


static func _create_sparks(tint: Color, amount: int) -> GPUParticles3D:
	var sparks := GPUParticles3D.new()
	sparks.name = "Sparks"
	sparks.amount = amount
	sparks.lifetime = 0.70
	sparks.preprocess = 0.35
	sparks.local_coords = false
	sparks.visibility_aabb = AABB(Vector3(-3.0, -2.0, -3.0), Vector3(6.0, 7.0, 6.0))
	var motion := ParticleProcessMaterial.new()
	motion.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	motion.emission_sphere_radius = 0.18
	motion.direction = Vector3.UP
	motion.spread = 45.0
	motion.initial_velocity_min = 1.1
	motion.initial_velocity_max = 2.6
	motion.gravity = Vector3(0.0, -0.5, 0.0)
	motion.scale_min = 0.55
	motion.scale_max = 1.25
	motion.scale_curve = _curve_texture(PackedVector2Array([Vector2(0.0, 0.8), Vector2(0.2, 1.0), Vector2(1.0, 0.0)]))
	var colors := Gradient.new()
	colors.offsets = PackedFloat32Array([0.0, 0.3, 1.0])
	colors.colors = PackedColorArray([Color(1.0, 0.97, 0.75), tint, Color(tint.r, tint.g, tint.b, 0.0)])
	var ramp := GradientTexture1D.new()
	ramp.gradient = colors
	motion.color_ramp = ramp
	sparks.process_material = motion
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	material.vertex_color_use_as_albedo = true
	material.albedo_color = Color(2.2, 2.2, 2.2, 1.0)
	material.albedo_texture = _get_spark_texture()
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	var quad := QuadMesh.new()
	quad.size = Vector2(0.022, 0.065)
	quad.material = material
	sparks.draw_pass_1 = quad
	return sparks


static func _curve_texture(points: PackedVector2Array) -> CurveTexture:
	var curve := Curve.new()
	for point in points:
		curve.add_point(point)
	var texture := CurveTexture.new()
	texture.curve = curve
	return texture


static func _get_heat_ramp() -> GradientTexture1D:
	if _heat_ramp == null:
		var gradient := Gradient.new()
		gradient.offsets = PackedFloat32Array([0.0, 0.35, 0.70, 1.0])
		gradient.colors = PackedColorArray([
			Color(0.16, 0.06, 0.02), Color(0.85, 0.30, 0.045),
			Color(1.0, 0.76, 0.28), Color(1.0, 0.98, 0.85)
		])
		_heat_ramp = GradientTexture1D.new()
		_heat_ramp.gradient = gradient
	return _heat_ramp


static func _get_fallback_texture() -> Texture2D:
	if _fallback_texture == null:
		# Generate our own repeatable, seamless field; no external asset/license dependency.
		var noise := FastNoiseLite.new()
		noise.seed = 43019
		noise.frequency = 0.023
		noise.fractal_octaves = 2
		var image := Image.create(128, 128, false, Image.FORMAT_RGBA8)
		for y in range(128):
			var fy := float(y) / 127.0
			var sy := smoothstep(0.0, 1.0, fy)
			for x in range(128):
				var fx := float(x) / 127.0
				var sx := smoothstep(0.0, 1.0, fx)
				var top := lerpf(noise.get_noise_2d(x, y), noise.get_noise_2d(x - 127, y), sx)
				var bottom := lerpf(noise.get_noise_2d(x, y - 127), noise.get_noise_2d(x - 127, y - 127), sx)
				var value := clampf(0.5 + lerpf(top, bottom, sy) * 0.9, 0.0, 1.0)
				image.set_pixel(x, y, Color(value, value, value, 1.0))
		_fallback_texture = ImageTexture.create_from_image(image)
	return _fallback_texture


static func _get_spark_texture() -> Texture2D:
	if _spark_texture == null:
		var image := Image.create(16, 32, false, Image.FORMAT_RGBA8)
		for y in range(32):
			for x in range(16):
				var p := Vector2(float(x) / 15.0, float(y) / 31.0) * 2.0 - Vector2.ONE
				var alpha := pow(maxf(0.0, 1.0 - p.length_squared()), 1.5)
				image.set_pixel(x, y, Color(1.0, 1.0, 1.0, alpha))
		_spark_texture = ImageTexture.create_from_image(image)
	return _spark_texture
