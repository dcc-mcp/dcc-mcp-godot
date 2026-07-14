extends Node2D

const ARENA_SIZE := Vector2(960.0, 540.0)
const PLAYER_SPEED := 260.0
const PLAYER_RADIUS := 16.0
const ENEMY_RADIUS := 12.0
const PROJECTILE_SPEED := 520.0

var player_position := ARENA_SIZE * 0.5
var health := 100.0
var experience := 0
var level := 1
var kills := 0
var elapsed := 0.0
var spawn_cooldown := 0.0
var fire_cooldown := 0.0
var enemies: Array[Dictionary] = []
var projectiles: Array[Dictionary] = []


func _ready() -> void:
	set_process(true)
	queue_redraw()


func _process(delta: float) -> void:
	var input := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
	player_position += input * PLAYER_SPEED * delta
	player_position = player_position.clamp(Vector2(PLAYER_RADIUS, PLAYER_RADIUS), ARENA_SIZE - Vector2(PLAYER_RADIUS, PLAYER_RADIUS))
	simulate_step(delta)
	queue_redraw()


func simulate_step(delta: float) -> void:
	if health <= 0.0:
		return
	elapsed += delta
	spawn_cooldown -= delta
	fire_cooldown -= delta
	if spawn_cooldown <= 0.0:
		_spawn_enemy()
		spawn_cooldown = maxf(0.25, 1.2 - elapsed * 0.01)
	if fire_cooldown <= 0.0 and not enemies.is_empty():
		_fire_at_nearest()
		fire_cooldown = maxf(0.15, 0.5 - float(level) * 0.02)
	_update_enemies(delta)
	_update_projectiles(delta)
	_resolve_hits()


func _spawn_enemy(position := Vector2.INF) -> void:
	if position == Vector2.INF:
		var side := randi() % 4
		match side:
			0: position = Vector2(randf_range(0.0, ARENA_SIZE.x), -ENEMY_RADIUS)
			1: position = Vector2(ARENA_SIZE.x + ENEMY_RADIUS, randf_range(0.0, ARENA_SIZE.y))
			2: position = Vector2(randf_range(0.0, ARENA_SIZE.x), ARENA_SIZE.y + ENEMY_RADIUS)
			_: position = Vector2(-ENEMY_RADIUS, randf_range(0.0, ARENA_SIZE.y))
	enemies.append({
		"position": position,
		"health": 1.0 + floorf(elapsed / 45.0),
		"speed": 65.0 + minf(90.0, elapsed * 0.8),
	})


func _fire_at_nearest() -> void:
	var target: Dictionary = enemies[0]
	var nearest := player_position.distance_squared_to(target["position"])
	for enemy in enemies:
		var distance := player_position.distance_squared_to(enemy["position"])
		if distance < nearest:
			nearest = distance
			target = enemy
	var direction: Vector2 = player_position.direction_to(target["position"])
	projectiles.append({"position": player_position, "velocity": direction * PROJECTILE_SPEED})


func _update_enemies(delta: float) -> void:
	for enemy in enemies:
		var position: Vector2 = enemy["position"]
		enemy["position"] = position.move_toward(player_position, float(enemy["speed"]) * delta)
		if enemy["position"].distance_to(player_position) <= PLAYER_RADIUS + ENEMY_RADIUS:
			health = maxf(0.0, health - 24.0 * delta)


func _update_projectiles(delta: float) -> void:
	for projectile in projectiles:
		projectile["position"] += projectile["velocity"] * delta
	for index in range(projectiles.size() - 1, -1, -1):
		var position: Vector2 = projectiles[index]["position"]
		if position.x < -32.0 or position.y < -32.0 or position.x > ARENA_SIZE.x + 32.0 or position.y > ARENA_SIZE.y + 32.0:
			projectiles.remove_at(index)


func _resolve_hits() -> void:
	for projectile_index in range(projectiles.size() - 1, -1, -1):
		var projectile_position: Vector2 = projectiles[projectile_index]["position"]
		var hit_index := -1
		for enemy_index in range(enemies.size()):
			if projectile_position.distance_to(enemies[enemy_index]["position"]) <= ENEMY_RADIUS + 5.0:
				hit_index = enemy_index
				break
		if hit_index < 0:
			continue
		projectiles.remove_at(projectile_index)
		enemies[hit_index]["health"] -= 1.0 + float(level - 1) * 0.25
		if enemies[hit_index]["health"] <= 0.0:
			enemies.remove_at(hit_index)
			kills += 1
			experience += 1
			var needed := level * 5
			if experience >= needed:
				experience -= needed
				level += 1
				health = minf(100.0, health + 15.0)


func spawn_enemy_for_test() -> void:
	_spawn_enemy(player_position + Vector2(120.0, 0.0))


func fire_projectile_for_test() -> void:
	if enemies.is_empty():
		spawn_enemy_for_test()
	_fire_at_nearest()


func get_game_state() -> Dictionary:
	return {
		"health": health,
		"level": level,
		"experience": experience,
		"kills": kills,
		"elapsed": elapsed,
		"enemies": enemies.size(),
		"projectiles": projectiles.size(),
	}


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, ARENA_SIZE), Color("101622"), true)
	draw_circle(player_position, PLAYER_RADIUS, Color("55d6be"))
	for enemy in enemies:
		draw_circle(enemy["position"], ENEMY_RADIUS, Color("ff5d73"))
	for projectile in projectiles:
		draw_circle(projectile["position"], 5.0, Color("ffd166"))
	var status := "HP %d   LV %d   XP %d/%d   KILLS %d" % [health, level, experience, level * 5, kills]
	draw_string(ThemeDB.fallback_font, Vector2(20.0, 30.0), status, HORIZONTAL_ALIGNMENT_LEFT, -1.0, 18, Color.WHITE)
	if health <= 0.0:
		draw_string(ThemeDB.fallback_font, ARENA_SIZE * 0.5 - Vector2(70.0, 0.0), "GAME OVER", HORIZONTAL_ALIGNMENT_LEFT, -1.0, 28, Color("ff5d73"))

