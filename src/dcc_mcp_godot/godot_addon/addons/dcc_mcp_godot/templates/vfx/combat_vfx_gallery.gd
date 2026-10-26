extends Node3D
## Fire, attack, spell and aura presets in one native gallery.

const EFFECT = preload("combat_effect.gd")
const PROJECTILE = preload("spell_projectile.gd")
const MESH_FIRE = preload("mesh_fire.tscn")
const PARTICLE_FIRE = preload("particle_fire.tscn")
const FIRE = preload("dynamic_fire.gd")

@export var auto_play := true

var event_count := 0
var _elapsed := 0.0
var _aura_anchor: Node3D
var _slash: Node3D
var _impact: Node3D
var _projectiles: Node3D
var _timeline: AnimationPlayer


func _ready() -> void:
	_build_stage()
	var mesh_fire := MESH_FIRE.instantiate() as Node3D
	mesh_fire.name = "MeshFire"
	mesh_fire.position = Vector3(-3.6, 0.0, -6.7)
	add_child(mesh_fire)
	var particle_fire := PARTICLE_FIRE.instantiate() as Node3D
	particle_fire.name = "ParticleFire"
	particle_fire.position = Vector3(3.2, 0.0, -6.7)
	add_child(particle_fire)
	_slash = _effect("Melee", "slash", Color("ffb64f"), 1.7, 0.55, Vector3(-3.6, 0.65, 1.9), false)
	_impact = _effect("Impact", "impact", Color("ff7339"), 1.9, 0.8, Vector3(3.2, 0.03, 1.9), false)
	_aura_anchor = Node3D.new()
	_aura_anchor.name = "AuraAnchor"
	_aura_anchor.position = Vector3(-3.6, 0.03, -2.4)
	add_child(_aura_anchor)
	var attached := EFFECT.new()
	attached.name = "AttachedAura"
	attached.kind = "aura"
	attached.tint = Color("55d9ff")
	attached.radius = 1.65
	_aura_anchor.add_child(attached)
	_effect("WorldAura", "aura", Color("ff9a35"), 1.65, 0.6, Vector3(3.2, 0.03, -2.4), true)
	_projectiles = Node3D.new()
	_projectiles.name = "Projectiles"
	add_child(_projectiles)
	_build_timeline()
	if auto_play: _timeline.play("Showcase")


func _process(delta: float) -> void:
	_elapsed += delta
	_aura_anchor.position.x = -3.6 + sin(_elapsed * 0.8) * 0.35


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.physical_keycode == KEY_SPACE:
		play_cycle()


func play_cycle() -> void:
	get_node("MeshFire").show()
	FIRE.set_emitting(get_node("ParticleFire"), true)
	for node in [_aura_anchor.get_node("AttachedAura"), get_node("WorldAura")]:
		if not node.get_state().playing: node.play()
	set_process(true)
	_timeline.stop()
	_timeline.play("Showcase")


func strike() -> void:
	_slash.play()
	event_count += 1


func release_projectile() -> void:
	var shot := PROJECTILE.new()
	shot.speed = 8.0
	shot.lifetime = 2.8
	shot.tint = Color("ff7339")
	_projectiles.add_child(shot)
	shot.global_position = Vector3(-2.5, 0.75, 1.9)
	shot.launch(Vector3(3.2, 0.75, 1.9))
	event_count += 1


func pulse_impact() -> void:
	_impact.play()
	event_count += 1


func stop_effects() -> void:
	_timeline.stop()
	get_node("MeshFire").hide()
	FIRE.set_emitting(get_node("ParticleFire"), false)
	for node in [_slash, _impact, _aura_anchor.get_node("AttachedAura"), get_node("WorldAura")]:
		node.stop()
	for shot in _projectiles.get_children(): shot.queue_free()
	set_process(false)


func _effect(node_name: String, kind: String, color: Color, radius: float, duration: float, at: Vector3, autoplay: bool) -> Node3D:
	var effect := EFFECT.new()
	effect.name = node_name
	effect.kind = kind
	effect.tint = color
	effect.radius = radius
	effect.duration = duration
	effect.autoplay = autoplay
	effect.position = at
	add_child(effect)
	return effect


func _build_timeline() -> void:
	_timeline = AnimationPlayer.new()
	_timeline.name = "Timeline"
	add_child(_timeline)
	var clip := Animation.new()
	clip.length = 2.8
	clip.loop_mode = Animation.LOOP_LINEAR
	var events := clip.add_track(Animation.TYPE_METHOD)
	clip.track_set_path(events, NodePath("."))
	clip.track_insert_key(events, 0.15, {"method": "strike", "args": []})
	clip.track_insert_key(events, 0.35, {"method": "release_projectile", "args": []})
	clip.track_insert_key(events, 1.08, {"method": "pulse_impact", "args": []})
	var library := AnimationLibrary.new()
	library.add_animation("Showcase", clip)
	_timeline.add_animation_library("", library)


func _build_stage() -> void:
	var world := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.001, 0.002, 0.006)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("8c9fb8")
	environment.ambient_light_energy = 0.45
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	environment.glow_enabled = true
	world.environment = environment
	add_child(world)
	var floor := BoxMesh.new()
	floor.size = Vector3(14, 0.16, 14.5)
	_mesh("Stage", floor, Vector3(0, -0.14, -2.2), Color("161d29"))
	for at in [Vector3(-3.6, 0, 1.9), Vector3(3.2, 0, 1.9), Vector3(-3.6, 0, -2.4), Vector3(3.2, 0, -2.4), Vector3(-3.6, 0, -6.7), Vector3(3.2, 0, -6.7)]:
		var disk := CylinderMesh.new()
		disk.top_radius = 2.05
		disk.bottom_radius = 2.05
		disk.height = 0.04
		disk.radial_segments = 96
		_mesh("EffectPad", disk, at - Vector3.UP * 0.025, Color("202b3b"))
	var body := CapsuleMesh.new()
	body.radius = 0.21
	body.height = 1.1
	_mesh("TrainingDummy", body, Vector3(-3.6, 0.7, 2.0), Color("63778d"))
	var head := SphereMesh.new()
	head.radius = 0.18
	head.height = 0.36
	_mesh("DummyHead", head, Vector3(-3.6, 1.4, 2.0), Color("a5b6ca"))
	_label("MELEE / SWEEP", Vector3(-3.6, 0.06, 4.0))
	_label("SPELL / IMPACT", Vector3(3.2, 0.06, 4.0))
	_label("AURA / FOLLOW", Vector3(-3.6, 0.06, -0.35))
	_label("RITUAL / WORLD", Vector3(3.2, 0.06, -0.35))
	_label("FIRE / MESH", Vector3(-3.6, 0.06, -4.7))
	_label("FIRE / PARTICLES", Vector3(3.2, 0.06, -4.7))
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-55, -20, 0)
	key.light_color = Color("acbfd9")
	key.light_energy = 1.1
	key.shadow_enabled = true
	add_child(key)
	var camera := Camera3D.new()
	camera.position = Vector3(0, 15.5, 15.4)
	camera.fov = 43.0
	add_child(camera)
	camera.look_at(Vector3(0, 0.0, -2.3))
	camera.current = true
	var overlay := CanvasLayer.new()
	add_child(overlay)
	var title := Label.new()
	title.text = "COMBAT / EFFECT LIBRARY"
	title.position = Vector2(30, 24)
	title.add_theme_font_size_override("font_size", 25)
	overlay.add_child(title)
	var hint := Label.new()
	hint.text = "SPACE  REPLAY"
	hint.position = Vector2(30, 58)
	hint.modulate = Color("96b0cd")
	overlay.add_child(hint)


func _mesh(node_name: String, mesh: Mesh, at: Vector3, color: Color) -> void:
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.position = at
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.74
	node.material_override = material
	add_child(node)


func _label(text: String, at: Vector3) -> void:
	var label := Label3D.new()
	label.text = text
	label.position = at
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.font_size = 36
	label.pixel_size = 0.009
	label.modulate = Color("9bb2cc")
	label.outline_size = 3
	add_child(label)
