---
name: godot-project
description: >-
  Domain skill — Inspect a Godot 4 project or write a bounded GDScript file
  below res://. Use for project metadata and game script authoring. Not for
  open-scene node edits — use godot-scene. Not for generating a complete
  playable prototype — use godot-roguelike.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot project inspect metadata author GDScript res:// game development"
    tags: "godot,project,gdscript,game-development"
    tools: tools.yaml
    depends: "dcc-diagnostics"
---

# Godot Project

Inspect project state before authoring. `write_script` only accepts `.gd` paths below `res://`,
does not run the script, and requires `overwrite=true` before replacing a file.
