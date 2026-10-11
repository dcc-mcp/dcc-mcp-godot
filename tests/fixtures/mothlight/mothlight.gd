extends Node3D

var player: AnimationPlayer
var skeleton: Skeleton3D
var model: Node3D
var clip := "Perch"
var paused := false
var elapsed := 0.0
var frame := 0
var status: Label
var progress: ProgressBar
var buttons: Array[Button] = []
var capture_dir := ""
var demo := false
var test_mode := false
var tests: Dictionary = {}
const CREAM = Color("e9dec4")
const GOLD = Color("bc8c48")

func _ready() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg == "--demo": demo = true
		if arg == "--test": test_mode = true
		if arg.begins_with("--capture="): capture_dir = arg.trim_prefix("--capture=")
	model = load("res://mothlight.glb").instantiate()
	add_child(model)
	player = find_type(model, "AnimationPlayer")
	skeleton = find_type(model, "Skeleton3D")
	var world := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("091a22")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("8ca4a5")
	env.ambient_light_energy = 0.5
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	world.environment = env
	add_child(world)
	var cam := Camera3D.new()
	add_child(cam)
	cam.position = Vector3(2.8, 5.5, 4.3)
	cam.look_at(Vector3(0.3, 0, 0))
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = 5.2
	cam.current = true
	for spec in [[Vector3(-3,5,2),Color("ffddb0"),1.1],[Vector3(3,2,-3),Color("7ce2e0"),0.65]]:
		var light := DirectionalLight3D.new()
		add_child(light)
		light.position = spec[0]
		light.look_at(Vector3.ZERO)
		light.light_color = spec[1]
		light.light_energy = spec[2]
		light.shadow_enabled = true
	var floor_mesh := CylinderMesh.new()
	floor_mesh.top_radius = 1.8
	floor_mesh.bottom_radius = 1.8
	floor_mesh.height = 0.08
	var floor_node := MeshInstance3D.new()
	floor_node.mesh = floor_mesh
	floor_node.position.y = -0.43
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("122e37")
	material.metallic = 0.6
	material.roughness = 0.55
	floor_node.material_override = material
	add_child(floor_node)
	var brass := StandardMaterial3D.new()
	brass.albedo_color = Color("b99052")
	brass.metallic = 0.7
	brass.roughness = 0.4
	for radius in [1.62,1.72]:
		var torus := TorusMesh.new()
		torus.inner_radius = radius - 0.004
		torus.outer_radius = radius + 0.004
		var orbit := MeshInstance3D.new()
		orbit.mesh = torus
		orbit.position.y = -0.384
		orbit.material_override = brass
		add_child(orbit)
	build_ui()
	select_clip("Perch")
	if test_mode: call_deferred("run_tests")

func find_type(node: Node, klass: String):
	if node.is_class(klass): return node
	for child in node.get_children():
		var found = find_type(child, klass)
		if found != null: return found
	return null

func label_at(parent: Node, text: String, pos: Vector2, size: int, color := CREAM) -> Label:
	var label := Label.new()
	label.text = text
	label.position = pos
	label.add_theme_font_size_override("font_size",size)
	label.add_theme_color_override("font_color",color)
	parent.add_child(label)
	return label

func build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	layer.add_child(root)
	label_at(root,"FIELD NOTES     /     KINETIC SPECIMEN 001",Vector2(42,28),15,GOLD)
	label_at(root,"MOTHLIGHT",Vector2(40,55),49)
	label_at(root,"A small machine dreaming of flight.",Vector2(43,118),18,Color("9bb4b6"))
	label_at(root,"PAPER  ×  BRASS",Vector2(1006,39),15,GOLD)
	label_at(root,"MOTION CABINET",Vector2(1006,63),14)
	var panel := Panel.new()
	panel.position = Vector2(1000,218)
	panel.size = Vector2(238,366)
	var box := StyleBoxFlat.new()
	box.bg_color = Color("102830")
	box.border_color = Color("375258")
	box.set_border_width_all(1)
	box.set_corner_radius_all(10)
	panel.add_theme_stylebox_override("panel",box)
	root.add_child(panel)
	label_at(panel,"CHOOSE A MOTION",Vector2(18,18),13,GOLD)
	for i in range(3):
		var b := Button.new()
		var names := ["Perch","Unfurl","Flight"]
		b.text = "%d    %s" % [i+1,names[i].to_upper()]
		b.position = Vector2(18,56+i*61)
		b.size = Vector2(202,47)
		b.add_theme_font_size_override("font_size",16)
		b.pressed.connect(button_clip.bind(names[i]))
		panel.add_child(b)
		buttons.append(b)
	label_at(panel,"10 BONES  /  3 CLIPS",Vector2(18,260),13,GOLD)
	label_at(panel,"Original weighted geometry\nBlender → glTF → Godot",Vector2(18,289),13,Color("9bb4b6"))
	status = label_at(root,"",Vector2(43,698),17)
	label_at(root,"1 / 2 / 3  switch motion       SPACE  pause       R  reset",Vector2(43,750),14,Color("9bb4b6"))
	label_at(root,"A STUDY IN ARTICULATED LIGHT",Vector2(872,750),13,GOLD)
	progress = ProgressBar.new()
	progress.position = Vector2(43,731)
	progress.size = Vector2(1193,4)
	progress.show_percentage = false
	for key in ["background","fill"]:
		var style := StyleBoxFlat.new()
		style.bg_color = Color("ba914f") if key == "fill" else Color("213b42")
		style.set_content_margin_all(0)
		progress.add_theme_stylebox_override(key,style)
	root.add_child(progress)
	progress.size = Vector2(1193,4)

func button_clip(name: String) -> void:
	print("INPUT_BUTTON:",name)
	select_clip(name)

func select_clip(name: String) -> void:
	clip = name
	paused = false
	if player == null: return
	player.play(name)
	player.seek(0,true)
	player.get_animation(name).loop_mode = Animation.LOOP_LINEAR if name != "Unfurl" else Animation.LOOP_NONE
	for i in range(buttons.size()): buttons[i].modulate = Color("f3bc67") if ["Perch","Unfurl","Flight"][i] == name else Color.WHITE
	print("MOTION_SELECTED:",name)

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		print("INPUT_KEY:",OS.get_keycode_string(event.keycode))
		match event.keycode:
			KEY_1: select_clip("Perch")
			KEY_2: select_clip("Unfurl")
			KEY_3: select_clip("Flight")
			KEY_R: select_clip(clip)
			KEY_SPACE:
				paused = not paused
				print("PAUSE_STATE:",paused)
				if paused: player.pause()
				else: player.play()

func _process(delta: float) -> void:
	elapsed += delta
	frame += 1
	if player != null:
		var length := player.get_animation(clip).length
		progress.value = player.current_animation_position / max(length,0.01) * 100
		status.text = "%s   /   %s     %.2f s" % [clip.to_upper(),"PAUSED" if paused else "PLAYING",player.current_animation_position]
	if demo:
		if frame == 100: select_clip("Unfurl")
		if frame == 225: select_clip("Flight")
		if frame == 330: select_clip("Perch")
	if capture_dir != "" and frame in [45,160,265]:
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(capture_dir.path_join("motion-%s.png" % clip.to_lower()))

func run_tests() -> void:
	var names := Array(player.get_animation_list())
	var expected := ["Flight","Perch","Unfurl"]
	var samples := {}
	var index := skeleton.find_bone("forewing.L")
	for name in expected:
		select_clip(name)
		player.advance(0)
		player.seek(0,true)
		var a := skeleton.get_bone_pose_rotation(index)
		player.seek(player.get_animation(name).length*0.31,true)
		player.advance(0)
		var b := skeleton.get_bone_pose_rotation(index)
		samples[name] = {"duration_s":player.get_animation(name).length,"tracks":player.get_animation(name).get_track_count(),"wing_pose_delta_radians":a.angle_to(b)}
	var bounds := AABB()
	var mesh_count := 0
	for node in model.find_children("*","MeshInstance3D",true,false):
		var box: AABB = node.global_transform * node.get_aabb()
		bounds = box if mesh_count == 0 else bounds.merge(box)
		mesh_count += 1
	var passed := skeleton.get_bone_count() == 10 and mesh_count == 197
	for name in expected: passed = passed and names.has(name) and samples[name]["wing_pose_delta_radians"] > 0.001
	select_clip("Flight")
	player.advance(0.3)
	player.pause()
	var before := player.current_animation_position
	await get_tree().process_frame
	var pause_ok := is_equal_approx(before,player.current_animation_position)
	player.play()
	player.advance(0.1)
	var resume_ok := player.current_animation_position > before
	passed = passed and pause_ok and resume_ok and progress.size.y <= 5
	tests = {"passed":passed,"progress_height_px":progress.size.y,"godot_version":Engine.get_version_info().string,"animations":names,"bones":skeleton.get_bone_count(),"mesh_instances":mesh_count,"clips":samples,"bbox_min_m":[bounds.position.x,bounds.position.y,bounds.position.z],"dimensions_m":[bounds.size.x,bounds.size.y,bounds.size.z],"pause":pause_ok,"resume":resume_ok}
	print("MOTHLIGHT_TEST:",JSON.stringify(tests))
	get_tree().quit(0 if passed else 1)
