---
name: godot-input
description: >-
  Domain skill — Send a keyboard event to the running game. Send a mouse button event to the running game. Send mouse motion to the running game. Press or release a Godot input action in the running game. Queue a sequence of runtime input events. List editor InputMap or explicitly selected project input actions. Update an editor input action, or explicitly persist one project binding.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot input simulate_key simulate_mouse_click simulate_mouse_move simulate_action simulate_sequence get_input_actions set_input_action"
    tags: "godot,input,game-development"
    tools: tools.yaml
---

# Godot Input

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.

`set_input_action` defaults to `persist: false`: it edits only the editor process InputMap, does not save, and does not rebind a running game. Use `persist: true` to author one `input/<action>` project default. This mode reads the project's existing events, never copies editor shortcuts, and leaves the editor InputMap unchanged. `ProjectSettings.save()` saves the whole current project configuration, including other unsaved settings. Save failures restore the target in-memory setting and return an error; disk rollback is not guaranteed. Start/restart the game to load saved defaults. Use `get_input_actions` with `source: project` to inspect project settings; the default `source: editor` preserves the legacy view (excluding `ui_` actions). Project queries include built-in UI actions. Events are human-readable strings, not round-trip event payloads.

The setter authors one logical `keycode` only. Existing mouse, joypad, physical key, modifier and device bindings remain intact unless `replace_events: true` explicitly clears all events. Omitting `keycode` adds nothing; replacement without it clears the action. Omitting `deadzone` preserves it, or uses 0.5 for a new action; existing settings without it use the native 0.2 default. Null event entries are preserved (shown as empty placeholders by the getter). `events`, `button`, and simulation parameters are not accepted by this setter; they do not describe an implemented event-authoring API. Use simulation tools for the running game, not for project persistence.
