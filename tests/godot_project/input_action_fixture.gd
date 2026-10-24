extends SceneTree

const ACTIONS := ["dcc_input_mix", "dcc_replace", "dcc_new", "dcc_unsaved", "dcc_save_failure", "dcc_implicit", "dcc_default"]

func _initialize() -> void:
	var mode := OS.get_cmdline_user_args()[0]
	if mode == "setup":
		var mouse := InputEventMouseButton.new()
		mouse.button_index = MOUSE_BUTTON_RIGHT
		mouse.device = -1
		var button := InputEventJoypadButton.new()
		button.button_index = JOY_BUTTON_A
		button.device = 2
		var motion := InputEventJoypadMotion.new()
		motion.axis = JOY_AXIS_LEFT_X
		motion.axis_value = -1.0
		motion.device = 3
		var physical := InputEventKey.new()
		physical.physical_keycode = KEY_SPACE
		var modified := InputEventKey.new()
		modified.keycode = KEY_SPACE
		modified.shift_pressed = true
		var device_key := InputEventKey.new()
		device_key.keycode = KEY_SPACE
		device_key.device = 7
		var label_key := InputEventKey.new()
		label_key.key_label = KEY_SPACE
		var events: Array[InputEvent] = [mouse, button, motion, physical, modified, device_key, label_key]
		for action in ["dcc_input_mix", "dcc_replace"]:
			ProjectSettings.set_setting("input/" + action, {"events": events.duplicate(), "deadzone": 0.25, "fixture_marker": "keep"})
		ProjectSettings.set_setting("input/dcc_implicit", {"events": [null, physical]})
		ProjectSettings.set_setting("application/config/description", "unrelated sentinel")
		assert(ProjectSettings.save() == OK)
	elif mode == "host_validation":
		var capabilities = load("res://addons/dcc_mcp_godot/capabilities.gd").new(null)
		var before := FileAccess.get_file_as_bytes("res://project.godot")
		var checks := 0
		for params in [{"deadzone": NAN}, {"deadzone": INF}, {"keycode": INF}, {"keycode": 1e100}, {"keycode": true}, {"persist": 1}, {"replace_events": "true"}, {"action": "bad/name"}, {"action": "bad\u0001name"}]:
			var request := {"action": "dcc_invalid_host", "persist": true}
			request.merge(params, true)
			var result: Dictionary = capabilities.execute("set_input_action", request)
			assert(result.has("__error__"), str(request))
			assert(not ProjectSettings.has_setting("input/dcc_invalid_host"))
			assert(not InputMap.has_action("dcc_invalid_host"))
			assert(before == FileAccess.get_file_as_bytes("res://project.godot"))
			checks += 4
		var old_setting: Dictionary = ProjectSettings.get_setting("input/dcc_input_mix")
		var old_events := InputMap.action_get_events("dcc_input_mix")
		var old_deadzone := InputMap.action_get_deadzone("dcc_input_mix")
		for persist in [false, true]:
			for change in [{"deadzone": 2.0}, {"keycode": 0}]:
				var request := {"action": "dcc_input_mix", "persist": persist, "replace_events": true}
				request.merge(change)
				assert(capabilities.execute("set_input_action", request).has("__error__"))
				assert(ProjectSettings.get_setting("input/dcc_input_mix") == old_setting)
				assert(InputMap.action_get_events("dcc_input_mix") == old_events and InputMap.action_get_deadzone("dcc_input_mix") == old_deadzone)
				assert(before == FileAccess.get_file_as_bytes("res://project.godot"))
				checks += 4
		for keycode in [KEY_ESCAPE, KEY_KP_9]:
			assert(capabilities.execute("set_input_action", {"action": "dcc_special", "keycode": keycode, "replace_events": true}).get("updated") == true)
			assert(InputMap.action_get_events("dcc_special")[0].keycode == keycode)
			assert(before == FileAccess.get_file_as_bytes("res://project.godot"))
			checks += 3
		InputMap.erase_action("dcc_special")
		_write("host_validation", {"checks": checks, "passed": true})
		quit(0)
		return
	var report := {"engine": Engine.get_version_info(), "actions": {}, "description": ProjectSettings.get_setting("application/config/description")}
	for action in ACTIONS:
		var row := {"in_input_map": InputMap.has_action(action), "in_project_settings": ProjectSettings.has_setting("input/" + action)}
		if row.in_project_settings:
			var value: Dictionary = ProjectSettings.get_setting("input/" + action)
			row.deadzone = value.get("deadzone", 0.2)
			row.fixture_marker = value.get("fixture_marker")
			row.events = []
			for event in value.events:
				if event == null:
					row.events.append(null)
					continue
				var data := {"class": event.get_class()}
				for property in event.get_property_list():
					if property.usage & PROPERTY_USAGE_STORAGE:
						data[property.name] = event.get(property.name)
				row.events.append(data)
		if row.in_input_map:
			row.input_deadzone = InputMap.action_get_deadzone(action)
			row.input_event_count = InputMap.action_get_events(action).size()
		report.actions[action] = row
	_write(mode, report)
	quit(0)

func _write(name: String, value: Dictionary) -> void:
	var file := FileAccess.open("res://" + name + ".json", FileAccess.WRITE)
	assert(file != null)
	file.store_string(JSON.stringify(value))
	file.close()
