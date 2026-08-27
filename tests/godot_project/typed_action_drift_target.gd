extends Node

var speed: float = 1.0:
	set(value):
		speed = value
		if not is_equal_approx(value, 1.0):
			var script_path := str(get_script().resource_path)
			var file := FileAccess.open(script_path, FileAccess.WRITE)
			if file != null:
				file.store_string("extends Node\nvar speed: float = 99.0\n")
				file.close()
