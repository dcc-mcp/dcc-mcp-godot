extends SceneTree

func _initialize() -> void:
	call_deferred("verify")

func find_type(n: Node, klass: String):
	if n.is_class(klass): return n
	for c in n.get_children():
		var found = find_type(c,klass)
		if found != null: return found
	return null

func verify() -> void:
	var cabinet = load("res://main.tscn").instantiate()
	root.add_child(cabinet)
	for i in range(5): await process_frame
	var model = cabinet.model
	var player: AnimationPlayer = find_type(model,"AnimationPlayer")
	var skeleton: Skeleton3D = find_type(model,"Skeleton3D")
	var mesh: MeshInstance3D
	var skinned := 0
	for item in model.find_children("*","MeshInstance3D",true,false):
		if item.skin != null and item.get_node_or_null(item.skeleton) == skeleton: skinned += 1
		if str(item.name).begins_with("Pleated L fore panel"): mesh=item
	assert(mesh != null)
	print("SKIN_BOUND:",skinned)
	var out := {"skin_bound_mesh_instances":skinned,"mesh":str(mesh.name),"clips":{}}
	var passed := skinned == 197
	for clip in ["Perch","Unfurl","Flight"]:
		player.play(clip)
		player.seek(0,true)
		player.advance(0)
		skeleton.force_update_all_bone_transforms()
		await process_frame
		var a := mesh.bake_mesh_from_current_skeleton_pose()
		player.seek(player.get_animation(clip).length*.31,true)
		player.advance(0)
		skeleton.force_update_all_bone_transforms()
		await process_frame
		var b := mesh.bake_mesh_from_current_skeleton_pose()
		if a == null or b == null:
			print("MOTHLIGHT_SKIN: bake unavailable for the current renderer")
			quit(2)
			return
		var va: PackedVector3Array = a.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var vb: PackedVector3Array = b.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var moved := 0
		var maximum := 0.0
		for i in range(va.size()):
			var delta := va[i].distance_to(vb[i])
			maximum = max(maximum,delta)
			if delta > 0.000001: moved += 1
		out.clips[clip] = {"vertices":va.size(),"moved_vertices":moved,"max_displacement_m":maximum}
		passed = passed and moved > 0
	out.passed = passed
	print("MOTHLIGHT_SKIN:",JSON.stringify(out))
	quit(0 if passed else 1)
