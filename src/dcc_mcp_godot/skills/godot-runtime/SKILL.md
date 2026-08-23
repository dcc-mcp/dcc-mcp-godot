---
name: godot-runtime
description: >-
  Domain skill — Return game-peer connection and play status. Return one bounded page of the running game hierarchy. Return one bounded property page from a game node. Set a property on a running-game node. Call an allowlisted method on a running-game node. Capture numbered runtime screenshots. Sample runtime node properties over several frames. Start recording injected input events. Stop recording and return recorded input events. Replay previously recorded input events. Find runtime nodes using a script path. Return a runtime autoload node snapshot. Read several runtime node properties. Find visible runtime Control nodes in one bounded traversal page. Activate a visible runtime button by text. Check whether a runtime node exists. Find runtime 2D or 3D nodes near a position. Set a NavigationAgent target position. Move a runtime Node2D or Node3D toward a target.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot runtime get_runtime_status get_game_scene_tree get_game_node_properties set_game_node_property execute_game_script capture_frames monitor_properties start_recording stop_recording replay_recording find_nodes_by_script get_autoload batch_get_properties find_ui_elements click_button_by_text wait_for_node find_nearby_nodes navigate_to move_to"
    tags: "godot,runtime,game-development"
    tools: tools.yaml
---

# Godot Runtime

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.
