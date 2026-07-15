---
name: godot-scene-management
description: >-
  Domain skill — Return the edited scene hierarchy. Read a bounded .tscn file as text. Create and optionally open a new scene. Open a scene in the editor. Delete a project scene file. Instance a PackedScene below an edited-scene node. Run the main, current, or specified scene. Stop the running project. Save the edited scene, optionally to a new path.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot scene-management get_scene_tree get_scene_file_content create_scene open_scene delete_scene add_scene_instance play_scene stop_scene save_scene"
    tags: "godot,scene-management,game-development"
    tools: tools.yaml
---

# Godot Scene Management

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.
