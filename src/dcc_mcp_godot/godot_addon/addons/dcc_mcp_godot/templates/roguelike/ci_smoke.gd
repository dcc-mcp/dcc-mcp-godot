extends SceneTree


func _initialize() -> void:
	var packed = load("res://roguelike/main.tscn")
	if packed == null:
		push_error("Unable to load roguelike main scene")
		quit(1)
		return
	var game = packed.instantiate()
	root.add_child(game)
	game.spawn_enemy_for_test()
	game.fire_projectile_for_test()
	for _step in range(20):
		game.simulate_step(0.05)
	var state: Dictionary = game.get_game_state()
	if state.get("elapsed", 0.0) < 0.9 or state.get("level", 0) < 1:
		push_error("Roguelike simulation contract failed: %s" % JSON.stringify(state))
		quit(1)
		return
	print("ROGUELIKE_SMOKE_OK ", JSON.stringify(state))
	quit(0)

