extends SceneTree


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var packed := load("res://vfx_fire.tscn") as PackedScene
	if packed == null:
		_fail("MCP-generated fire scene is missing")
		return
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	var fire := scene.get_node_or_null("FireVFX") as MeshInstance3D
	if fire == null or not fire.mesh is CylinderMesh or not fire.material_override is ShaderMaterial:
		_fail("Fire must have a CylinderMesh and ShaderMaterial")
		return
	var mesh := fire.mesh as CylinderMesh
	if mesh.cap_top or mesh.cap_bottom or mesh.rings < 16:
		_fail("Fire mesh needs open ends and enough height subdivisions for deformation")
		return
	var material := fire.material_override as ShaderMaterial
	if material.shader == null or not material.shader.resource_path.ends_with("stylized_fire.gdshader"):
		_fail("Fire shader was not preserved by save/reload")
		return
	for parameter in ["emission_strength", "scroll_speed"]:
		var value = material.get_shader_parameter(parameter)
		if not (value is float or value is int) or value <= 0.0:
			_fail("Fire default was not preserved by save/reload: " + parameter)
			return
	if not material.get_shader_parameter("detail_scale") is Vector2:
		_fail("Fire detail_scale was not preserved by save/reload")
		return
	for parameter in ["noise_texture", "detail_texture"]:
		var texture = material.get_shader_parameter(parameter)
		if not texture is NoiseTexture2D or not texture.noise is FastNoiseLite or not texture.seamless:
			_fail("Fire needs a seamless procedural noise resource: " + parameter)
			return
	var ramp = material.get_shader_parameter("color_ramp")
	if not ramp is GradientTexture1D or ramp.gradient == null or ramp.gradient.get_point_count() < 3:
		_fail("Fire color ramp was not preserved by save/reload")
		return
	print("FIRE_VFX_STRUCTURE_OK")
	if "--render" not in OS.get_cmdline_user_args():
		quit(0)
		return
	var camera := Camera3D.new()
	camera.position = fire.global_position + Vector3(2.5, 0.7, 3.2)
	camera.fov = 45.0
	scene.add_child(camera)
	camera.look_at(fire.global_position)
	camera.current = true
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color(0.008, 0.008, 0.012)
	scene.add_child(world)
	for frame in range(60):
		await process_frame
	await RenderingServer.frame_post_draw
	var visible := root.get_texture().get_image()
	if visible == null or visible.is_empty():
		_fail("Renderer produced no pixels; --render requires a graphics backend")
		return
	if not _save_capture(visible, "fire-visible.png"):
		return
	var lit := _lit_pixels(visible)
	if lit < 100 or lit > visible.get_width() * visible.get_height() * 0.8:
		_fail("Fire coverage is empty or fills the frame: %s" % lit)
		return
	await create_timer(0.35).timeout
	await RenderingServer.frame_post_draw
	var animated := root.get_texture().get_image()
	if not _save_capture(animated, "fire-animated.png"):
		return
	var changed := 0
	for y in range(visible.get_height()):
		for x in range(visible.get_width()):
			var before := visible.get_pixel(x, y)
			var after := animated.get_pixel(x, y)
			if absf(before.r - after.r) + absf(before.g - after.g) + absf(before.b - after.b) > 0.05:
				changed += 1
	if changed < 25:
		_fail("Fire did not animate between rendered frames")
		return
	material.set_shader_parameter("dissolve", 1.0)
	await process_frame
	await RenderingServer.frame_post_draw
	var dissolved := root.get_texture().get_image()
	if not _save_capture(dissolved, "fire-dissolved.png"):
		return
	if _lit_pixels(dissolved) > 0:
		_fail("Fire must disappear completely at dissolve=1")
		return
	print("FIRE_VFX_RENDER_OK lit_pixels=%s changed_pixels=%s" % [lit, changed])
	quit(0)


func _save_capture(image: Image, filename: String) -> bool:
	var output := "res://captures/vfx"
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--output-dir="):
			output = argument.trim_prefix("--output-dir=")
	var error := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	if error != OK or image.save_png(output.path_join(filename)) != OK:
		_fail("Could not save fire rendering evidence: " + filename)
		return false
	return true


func _lit_pixels(image: Image) -> int:
	var count := 0
	for y in range(image.get_height()):
		for x in range(image.get_width()):
			var color := image.get_pixel(x, y)
			if maxf(color.r, maxf(color.g, color.b)) > 0.1:
				count += 1
	return count


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
