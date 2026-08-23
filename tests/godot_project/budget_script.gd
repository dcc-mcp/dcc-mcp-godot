@tool
extends RefCounted


func run(arguments: Dictionary) -> Dictionary:
	var cursor := int(arguments.get("cursor", 0))
	return {
		"done": cursor >= 1,
		"next_cursor": cursor + 1,
	}
