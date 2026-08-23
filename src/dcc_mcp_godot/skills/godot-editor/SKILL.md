---
name: godot-editor
description: >-
  Domain skill — Return errors captured by the DCC-MCP editor plugin. Capture the selected editor viewport to a PNG. Capture game pixels on the runtime thread and encode the PNG in the adapter. Run one @tool method with an observational budget and optional caller-driven chunks. Clear errors captured by the DCC-MCP editor plugin. Return node signals and their connections. Reload the DCC-MCP editor plugin. Rescan project files and reload changed scripts. Return recent DCC-MCP editor and runtime messages.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot editor get_editor_errors get_editor_screenshot get_game_screenshot execute_editor_script clear_output get_signals reload_plugin reload_project get_output_log"
    tags: "godot,editor,game-development"
    tools: tools.yaml
---

# Godot Editor

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.
