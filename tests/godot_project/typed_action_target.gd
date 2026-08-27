extends Node

var speed: float = 1.0
var arbitrary_method_calls := 0


func arbitrary_public_method() -> void:
	arbitrary_method_calls += 1
