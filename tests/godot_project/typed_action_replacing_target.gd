extends Node

var replacement_enabled := true
var speed: float = 1.0:
	set(value):
		speed = value
		if replacement_enabled and not is_equal_approx(value, 1.0):
			var parent := get_parent()
			if parent == null:
				return
			var sibling_index := get_index()
			var replacement = get_script().new()
			replacement.replacement_enabled = false
			replacement.speed = value
			replacement.name = name
			parent.remove_child(self)
			parent.add_child(replacement)
			parent.move_child(replacement, sibling_index)
