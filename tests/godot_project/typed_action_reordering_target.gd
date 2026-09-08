extends Node

var speed: float = 1.0:
	set(value):
		speed = value
		if value != 1.0 and get_parent() != null:
			get_parent().move_child(self, get_parent().get_child_count() - 1)
