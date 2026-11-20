extends SceneTree


func _initialize() -> void:
	var packed = load("res://roguelike/main.tscn")
	if packed == null:
		push_error("Unable to load roguelike main scene")
		quit(1)
		return
	var game = packed.instantiate()
	root.add_child(game)
	await process_frame
	var initial: Dictionary = game.get_game_state()
	_send_key(KEY_RIGHT, true)
	for _step in range(8):
		await process_frame
	_send_key(KEY_RIGHT, false)
	var moved: Dictionary = game.get_game_state()
	if moved.get("player_x", 0.0) <= initial.get("player_x", 0.0):
		push_error("Roguelike input contract failed to move the player: %s" % JSON.stringify(moved))
		quit(1)
		return
	game.spawn_enemy_for_test()
	game.fire_projectile_for_test()
	for _step in range(20):
		game.simulate_step(0.05)
	var combat: Dictionary = game.get_game_state()
	if combat.get("kills", 0) < 1:
		push_error("Roguelike combat contract failed: %s" % JSON.stringify(combat))
		quit(1)
		return
	game.set_process(false)
	game.auto_fire_enabled = false
	game.spawn_enemies_for_test(100)
	game.simulate_step(0.05)
	var failed: Dictionary = game.get_game_state()
	if not failed.get("game_over", false):
		push_error("Roguelike failure contract failed: %s" % JSON.stringify(failed))
		quit(1)
		return
	game.set_process(true)
	_send_key(KEY_SPACE, true)
	await process_frame
	await process_frame
	_send_key(KEY_SPACE, false)
	var restarted: Dictionary = game.get_game_state()
	if restarted.get("restart_count", 0) != 1 or restarted.get("game_over", true):
		push_error("Roguelike restart contract failed: %s" % JSON.stringify(restarted))
		quit(1)
		return
	print("ROGUELIKE_SMOKE_OK ", JSON.stringify({"initial": initial, "moved": moved, "combat": combat, "failed": failed, "restarted": restarted}))
	quit(0)


func _send_key(keycode: Key, pressed: bool) -> void:
	var event := InputEventKey.new()
	event.keycode = keycode
	event.physical_keycode = keycode
	event.pressed = pressed
	Input.parse_input_event(event)

