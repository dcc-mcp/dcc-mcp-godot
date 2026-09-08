extends Node

var armed := false
var reads := 0
var speed: float = 1.0:
	get:
		if armed:
			reads += 1
			if reads == 2:
				var parent := get_parent()
				var replacement: Node = get_script().new()
				replacement.speed = speed
				replacement.name = name
				parent.remove_child(self)
				parent.add_child(replacement)
		return speed
