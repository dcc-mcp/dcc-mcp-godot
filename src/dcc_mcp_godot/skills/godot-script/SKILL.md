---
name: godot-script
description: >-
  Domain skill — List project GDScript files and global class metadata. Read a bounded project GDScript file. Create a GDScript file from source or a safe template. Replace source or perform an exact search/replace edit. Attach a project script to a scene node. List scripts currently open in the script editor. Compile-check GDScript source or a project script. Search bounded text files under res://.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot script list_scripts read_script create_script edit_script attach_script get_open_scripts validate_script search_in_files"
    tags: "godot,script,game-development"
    tools: tools.yaml
---

# Godot Script

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.
