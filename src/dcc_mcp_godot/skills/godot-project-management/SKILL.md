---
name: godot-project-management
description: >-
  Domain skill — Return project metadata, version, viewport, and autoloads. Return a filtered recursive project file tree. Search project files by glob or name fragment. Read project settings by prefix or key. Set and persist one project setting. Convert a Godot resource UID to res:// path. Convert a res:// resource path to a Godot UID.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot project-management get_project_info get_filesystem_tree search_files get_project_settings set_project_setting uid_to_project_path project_path_to_uid"
    tags: "godot,project-management,game-development"
    tools: tools.yaml
---

# Godot Project Management

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.
