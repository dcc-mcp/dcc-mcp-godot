"""Generate the declarative Godot capability skills from a compact catalog."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_godot" / "skills"

# Public capability vocabulary. Implementations are original and live in this package.
CATEGORIES = {
    "project-management": [
        ("get_project_info", "Return project metadata, version, viewport, and autoloads."),
        ("get_filesystem_tree", "Return a filtered recursive project file tree."),
        ("search_files", "Search project files by glob or name fragment."),
        ("get_project_settings", "Read project settings by prefix or key."),
        ("set_project_setting", "Set and persist one project setting."),
        ("uid_to_project_path", "Convert a Godot resource UID to res:// path."),
        ("project_path_to_uid", "Convert a res:// resource path to a Godot UID."),
    ],
    "scene-management": [
        ("get_scene_tree", "Return the edited scene hierarchy."),
        ("get_scene_file_content", "Read a bounded .tscn file as text."),
        ("create_scene", "Create and optionally open a new scene."),
        ("open_scene", "Open a scene in the editor."),
        ("delete_scene", "Delete a project scene file."),
        ("add_scene_instance", "Instance a PackedScene below an edited-scene node."),
        ("play_scene", "Run the main, current, or specified scene."),
        ("stop_scene", "Stop the running project."),
        ("save_scene", "Save the edited scene, optionally to a new path."),
    ],
    "node": [
        ("add_node", "Add a typed node with initial properties."),
        ("delete_node", "Delete a node with undo support."),
        ("duplicate_node", "Duplicate a node and its owned children."),
        ("move_node", "Reparent a node while preserving ownership."),
        ("update_property", "Set an existing node property."),
        ("get_node_properties", "Return stored and editable node properties."),
        ("add_resource", "Create and assign a Resource to a node property."),
        ("set_anchor_preset", "Apply a Control anchor preset."),
        ("rename_node", "Rename an edited-scene node."),
        ("connect_signal", "Connect a signal between scene nodes."),
        ("disconnect_signal", "Disconnect a signal connection."),
        ("get_node_groups", "Return groups for a node."),
        ("set_node_groups", "Replace group membership for a node."),
        ("find_nodes_in_group", "Find edited-scene nodes in a group."),
    ],
    "script": [
        ("list_scripts", "List project GDScript files and global class metadata."),
        ("read_script", "Read a bounded project GDScript file."),
        ("create_script", "Create a GDScript file from source or a safe template."),
        ("edit_script", "Replace source or perform an exact search/replace edit."),
        ("attach_script", "Attach a project script to a scene node."),
        ("get_open_scripts", "List scripts currently open in the script editor."),
        ("validate_script", "Compile-check GDScript source or a project script."),
        ("search_in_files", "Search bounded text files under res://."),
    ],
    "editor": [
        ("get_editor_errors", "Return errors captured by the DCC-MCP editor plugin."),
        ("get_editor_screenshot", "Capture the selected editor viewport to a PNG."),
        (
            "get_game_screenshot",
            "Capture game pixels on the runtime thread and encode the PNG in the adapter.",
        ),
        (
            "execute_editor_script",
            "Run one @tool method with an observational budget and optional caller-driven chunks.",
        ),
        ("clear_output", "Clear errors captured by the DCC-MCP editor plugin."),
        ("get_signals", "Return node signals and their connections."),
        ("reload_plugin", "Reload the DCC-MCP editor plugin."),
        ("reload_project", "Rescan project files and reload changed scripts."),
        ("get_output_log", "Return recent DCC-MCP editor and runtime messages."),
    ],
    "input": [
        ("simulate_key", "Send a keyboard event to the running game."),
        ("simulate_mouse_click", "Send a mouse button event to the running game."),
        ("simulate_mouse_move", "Send mouse motion to the running game."),
        ("simulate_action", "Press or release a Godot input action in the running game."),
        ("simulate_sequence", "Queue a sequence of runtime input events."),
        ("get_input_actions", "List InputMap actions and deadzones."),
        ("set_input_action", "Create or replace an InputMap action."),
    ],
    "runtime": [
        ("get_runtime_status", "Return game-peer connection and play status."),
        (
            "execute_typed_action",
            "Execute one strict project-manifest action for bounded playtest control.",
        ),
        ("get_game_scene_tree", "Return one bounded page of the running game hierarchy."),
        ("get_game_node_properties", "Return one bounded property page from a game node."),
        ("set_game_node_property", "Set a property on a running-game node."),
        (
            "execute_game_script",
            "Compatibility-only broad public-method call; this is not an allowlist and is not a "
            "playtest or RL action path.",
        ),
        ("capture_frames", "Capture numbered runtime screenshots."),
        ("monitor_properties", "Sample runtime node properties over several frames."),
        ("start_recording", "Start recording injected input events."),
        ("stop_recording", "Stop recording and return recorded input events."),
        ("replay_recording", "Replay previously recorded input events."),
        ("find_nodes_by_script", "Find runtime nodes using a script path."),
        ("get_autoload", "Return a runtime autoload node snapshot."),
        ("batch_get_properties", "Read several runtime node properties."),
        ("find_ui_elements", "Find visible runtime Control nodes in one bounded traversal page."),
        ("click_button_by_text", "Activate a visible runtime button by text."),
        ("wait_for_node", "Check whether a runtime node exists."),
        ("find_nearby_nodes", "Find runtime 2D or 3D nodes near a position."),
        ("navigate_to", "Set a NavigationAgent target position."),
        ("move_to", "Move a runtime Node2D or Node3D toward a target."),
    ],
    "animation": [
        ("list_animations", "List AnimationPlayer libraries and animations."),
        ("create_animation", "Create an animation in an AnimationPlayer."),
        ("add_animation_track", "Add a typed animation track."),
        ("set_animation_keyframe", "Insert an animation key with optional easing."),
        ("get_animation_info", "Return animation tracks and keys."),
        ("remove_animation", "Remove an animation from a library."),
    ],
    "animation-tree": [
        ("create_animation_tree", "Create and configure an AnimationTree node."),
        ("get_animation_tree_structure", "Return AnimationTree parameters and tree type."),
        ("set_tree_parameter", "Set an AnimationTree parameter."),
        ("add_state_machine_state", "Add a state-machine animation node."),
        ("remove_state_machine_state", "Remove a state-machine node."),
        ("add_state_machine_transition", "Add a state-machine transition."),
        ("remove_state_machine_transition", "Remove a state-machine transition."),
        ("set_blend_tree_node", "Add or replace an AnimationNode in a blend tree."),
    ],
    "scene-3d": [
        ("add_mesh_instance", "Add a primitive MeshInstance3D."),
        ("setup_camera_3d", "Add or configure a Camera3D."),
        ("setup_lighting", "Add or configure a 3D light."),
        ("setup_environment", "Add or configure a WorldEnvironment."),
        ("add_gridmap", "Add and configure a GridMap."),
        ("set_material_3d", "Create or update a StandardMaterial3D override."),
    ],
    "physics": [
        ("setup_physics_body", "Configure physics-body properties."),
        ("setup_collision", "Add and configure a collision shape."),
        ("set_physics_layers", "Set collision layer and mask."),
        ("get_physics_layers", "Read collision layer and mask."),
        ("get_collision_info", "Return collision child and shape details."),
        ("add_raycast", "Add a RayCast2D or RayCast3D."),
    ],
    "particle": [
        ("create_particles", "Add GPUParticles2D or GPUParticles3D."),
        ("set_particle_material", "Configure a ParticleProcessMaterial."),
        ("set_particle_color_gradient", "Set particle color gradient points."),
        ("apply_particle_preset", "Apply a deterministic particle preset."),
        ("get_particle_info", "Return particle system properties."),
    ],
    "navigation": [
        ("setup_navigation_region", "Add or configure a navigation region."),
        ("setup_navigation_agent", "Add or configure a navigation agent."),
        ("bake_navigation_mesh", "Bake a NavigationMesh in the editor."),
        ("set_navigation_layers", "Set navigation layers on a node."),
        ("get_navigation_info", "Return navigation node configuration."),
        ("query_navigation_path", "Query a 2D or 3D navigation path."),
    ],
    "audio": [
        ("add_audio_player", "Add an audio stream player node."),
        ("add_audio_bus", "Add an audio bus."),
        ("add_audio_bus_effect", "Add an AudioEffect to a bus."),
        ("set_audio_bus", "Configure volume, mute, solo, or bypass."),
        ("get_audio_bus_layout", "Return buses and effects."),
        ("get_audio_info", "Return audio-node configuration."),
    ],
    "tilemap": [
        ("tilemap_set_cell", "Set one TileMapLayer cell."),
        ("tilemap_fill_rect", "Fill a rectangle of TileMapLayer cells."),
        ("tilemap_get_cell", "Read one TileMapLayer cell."),
        ("tilemap_clear", "Clear TileMapLayer cells."),
        ("tilemap_get_info", "Return TileMapLayer and TileSet information."),
        ("tilemap_get_used_cells", "Return used TileMapLayer coordinates."),
    ],
    "theme-ui": [
        ("create_theme", "Create and save a Theme resource."),
        ("set_theme_color", "Set a Theme color item."),
        ("set_theme_constant", "Set a Theme constant item."),
        ("set_theme_font_size", "Set a Theme font-size item."),
        ("set_theme_stylebox", "Create and set a StyleBoxFlat item."),
        ("get_theme_info", "Return Theme item lists for a type."),
    ],
    "shader": [
        ("create_shader", "Create a bounded .gdshader resource."),
        ("read_shader", "Read a project shader file."),
        ("edit_shader", "Replace or search/replace shader source."),
        (
            "assign_shader_material",
            "Assign a ShaderMaterial to a CanvasItem or GeometryInstance3D.",
        ),
        ("set_shader_param", "Set one ShaderMaterial parameter."),
        ("get_shader_params", "Return shader parameters on a node material."),
    ],
    "resource": [
        ("read_resource", "Load and serialize a resource property summary."),
        ("edit_resource", "Set properties and save a project resource."),
        ("create_resource", "Instantiate and save a typed Resource."),
        ("get_resource_preview", "Generate or return a cached resource preview."),
        ("add_autoload", "Register a project autoload singleton."),
        ("remove_autoload", "Remove a project autoload singleton."),
    ],
    "batch-refactor": [
        ("find_nodes_by_type", "Find edited-scene nodes by class."),
        ("find_signal_connections", "Return scene signal connections."),
        ("batch_set_property", "Set a property on matching edited-scene nodes."),
        ("find_node_references", "Search project text for a node path or name."),
        ("get_scene_dependencies", "Return dependencies for a scene resource."),
        ("cross_scene_set_property", "Update matching nodes across project scenes."),
        ("find_script_references", "Find project references to a script or resource."),
        ("detect_circular_dependencies", "Detect circular PackedScene dependencies."),
    ],
    "analysis": [
        ("analyze_scene_complexity", "Count nodes and high-cost scene features."),
        ("analyze_signal_flow", "Map edited-scene signal flow."),
        ("find_unused_resources", "Find project resources with no text references."),
        ("get_project_statistics", "Return project file, scene, script, and resource counts."),
    ],
    "testing-qa": [
        ("run_test_scenario", "Run a sequence of runtime actions and assertions."),
        ("assert_node_state", "Assert runtime node existence and properties."),
        ("assert_screen_text", "Assert visible runtime text."),
        ("compare_screenshots", "Compare two PNGs using bounded pixel sampling."),
        ("run_stress_test", "Sample runtime performance for a bounded frame count."),
        ("get_test_report", "Return the latest runtime test report."),
    ],
    "profiling": [
        ("get_performance_monitors", "Return runtime Performance monitor values."),
        ("get_editor_performance", "Return editor process memory and frame summary."),
    ],
    "export": [
        ("list_export_presets", "List project export presets without secrets."),
        ("export_project", "Export a project using a named preset and safe project path."),
        ("get_export_info", "Return export configuration and template availability."),
    ],
}

READ_ONLY_PREFIXES = (
    "get_",
    "list_",
    "read_",
    "search_",
    "find_",
    "analyze_",
    "assert_",
    "compare_",
    "detect_",
    "uid_",
    "project_path_",
    "wait_",
)

DESTRUCTIVE = {
    "delete_scene",
    "delete_node",
    "edit_script",
    "execute_editor_script",
    "execute_game_script",
    "execute_typed_action",
    "cross_scene_set_property",
    "edit_shader",
    "edit_resource",
    "remove_autoload",
    "export_project",
}

STRING = {"type": "string", "maxLength": 500}
PATH = {"type": "string", "pattern": "^res://", "maxLength": 500}
NODE_PATH = {"type": "string", "maxLength": 500}
PROPERTIES = {"type": "object"}
VALUE = {}
VECTOR = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 4}

IDENTITY = {
    "type": "string",
    "minLength": 1,
    "maxLength": 128,
    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
}
DIGEST = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
INPUT_ACTION_TARGET = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action"],
    "properties": {"action": IDENTITY},
}
PROPERTY_TARGET = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "node_path",
        "node_type",
        "script_path",
        "script_sha256",
        "property",
    ],
    "properties": {
        "node_path": {
            "type": "string",
            "pattern": "^/root/[A-Za-z0-9_./:-]+$",
            "maxLength": 500,
        },
        "node_type": IDENTITY,
        "script_path": {
            "type": "string",
            "pattern": "^res://[A-Za-z0-9_./-]+[.]gd$",
            "maxLength": 500,
        },
        "script_sha256": DIGEST,
        "property": IDENTITY,
    },
}
INPUT_ACTION_REQUEST = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "kind", "target", "arguments"],
    "properties": {
        "id": IDENTITY,
        "kind": {"const": "input_action"},
        "target": INPUT_ACTION_TARGET,
        "arguments": {
            "type": "object",
            "additionalProperties": False,
            "required": ["pressed", "strength"],
            "properties": {
                "pressed": {"type": "boolean"},
                "strength": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        },
    },
}
PROPERTY_REQUEST = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "kind", "target", "arguments"],
    "properties": {
        "id": IDENTITY,
        "kind": {"const": "set_property"},
        "target": PROPERTY_TARGET,
        "arguments": {
            "type": "object",
            "additionalProperties": False,
            "required": ["value"],
            "properties": {"value": {"type": ["boolean", "integer", "number", "string"]}},
        },
    },
}
TYPED_ACTION_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "project_id",
        "session_id",
        "runtime_id",
        "authority_id",
        "manifest_id",
        "manifest_digest",
        "action",
    ],
    "properties": {
        "project_id": IDENTITY,
        "session_id": IDENTITY,
        "runtime_id": IDENTITY,
        "authority_id": IDENTITY,
        "manifest_id": IDENTITY,
        "manifest_digest": DIGEST,
        "action": {"oneOf": [INPUT_ACTION_REQUEST, PROPERTY_REQUEST]},
    },
}
COMPATIBILITY_METHOD_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["node_path", "method", "arguments"],
    "properties": {
        "node_path": NODE_PATH,
        "method": {
            "type": "string",
            "pattern": "^[A-Za-z][A-Za-z0-9_]{0,127}$",
        },
        "arguments": {"type": "array", "maxItems": 8},
    },
}
TYPED_ACTION_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "status",
        "schema_version",
        "manifest_id",
        "manifest_digest",
        "action_id",
        "kind",
        "target",
        "readback",
        "budget",
    ],
    "properties": {
        "status": {"const": "applied"},
        "schema_version": {"const": 1},
        "manifest_id": IDENTITY,
        "manifest_digest": DIGEST,
        "action_id": IDENTITY,
        "kind": {"enum": ["input_action", "set_property"]},
        "target": {"oneOf": [INPUT_ACTION_TARGET, PROPERTY_TARGET]},
        "readback": {
            "oneOf": [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "action", "pressed", "strength"],
                    "properties": {
                        "kind": {"const": "input_action"},
                        "action": IDENTITY,
                        "pressed": {"type": "boolean"},
                        "strength": {"type": "number"},
                    },
                },
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "kind",
                        "node_path",
                        "node_type",
                        "property",
                        "value",
                        "script_sha256",
                    ],
                    "properties": {
                        "kind": {"const": "property"},
                        "node_path": {"type": "string"},
                        "node_type": IDENTITY,
                        "property": IDENTITY,
                        "value": {"type": ["boolean", "integer", "number", "string"]},
                        "script_sha256": DIGEST,
                    },
                },
            ]
        },
        "budget": {
            "type": "object",
            "additionalProperties": False,
            "required": ["used", "remaining", "limit"],
            "properties": {
                "used": {"type": "integer", "minimum": 1},
                "remaining": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1},
            },
        },
    },
}

CATEGORY_PROPERTIES = {
    "project-management": {
        "path": PATH,
        "query": STRING,
        "extension": STRING,
        "extensions": {"type": "array", "items": STRING},
        "key": STRING,
        "prefix": STRING,
        "value": VALUE,
        "uid": STRING,
    },
    "scene-management": {
        "path": PATH,
        "scene_path": PATH,
        "root_type": STRING,
        "root_name": STRING,
        "parent_path": NODE_PATH,
        "name": STRING,
        "mode": {"type": "string", "enum": ["main", "current", "custom"]},
        "open": {"type": "boolean"},
        "overwrite": {"type": "boolean"},
    },
    "node": {
        "node_path": NODE_PATH,
        "parent_path": NODE_PATH,
        "source_path": NODE_PATH,
        "target_path": NODE_PATH,
        "type": STRING,
        "name": STRING,
        "property": STRING,
        "value": VALUE,
        "properties": PROPERTIES,
        "resource_type": STRING,
        "signal": STRING,
        "method": STRING,
        "groups": {"type": "array", "items": STRING},
        "group": STRING,
    },
    "script": {
        "path": PATH,
        "script_path": PATH,
        "node_path": NODE_PATH,
        "source": {"type": "string", "maxLength": 1000000},
        "search": {"type": "string", "maxLength": 100000},
        "replace": {"type": "string", "maxLength": 100000},
        "query": STRING,
        "extensions": {"type": "array", "items": STRING},
        "base_type": STRING,
        "overwrite": {"type": "boolean"},
        "replace_all": {"type": "boolean"},
    },
    "editor": {
        "path": PATH,
        "node_path": NODE_PATH,
        "mode": {"type": "string", "enum": ["2d", "3d"]},
        "viewport": {"type": "integer", "minimum": 0, "maximum": 3},
        "method": STRING,
        "arguments": VALUE,
        "include_base64": {"type": "boolean"},
        "budget_ms": {"type": "integer", "minimum": 1, "maximum": 50},
        "chunked": {"type": "boolean"},
    },
    "input": {
        "action": STRING,
        "pressed": {"type": "boolean"},
        "strength": {"type": "number"},
        "keycode": {"type": "integer"},
        "position": VECTOR,
        "relative": VECTOR,
        "button": {"type": "integer"},
        "events": {"type": "array", "items": {"type": "object"}, "maxItems": 100},
        "deadzone": {"type": "number", "minimum": 0, "maximum": 1},
        "replace_events": {"type": "boolean"},
    },
    "runtime": {
        "node_path": NODE_PATH,
        "path": PATH,
        "property": STRING,
        "properties": {"type": "array", "items": STRING},
        "value": VALUE,
        "method": STRING,
        "arguments": {"type": "array", "maxItems": 8},
        "targets": {"type": "array", "items": {"type": "object"}, "maxItems": 500},
        "events": {"type": "array", "items": {"type": "object"}, "maxItems": 100},
        "steps": {"type": "array", "items": {"type": "object"}, "maxItems": 100},
        "text": STRING,
        "target": VECTOR,
        "radius": {"type": "number", "minimum": 0},
        "equals": PROPERTIES,
        "cursor": STRING,
        "budget_ms": {"type": "integer", "minimum": 1, "maximum": 50},
        "start_index": {"type": "integer", "minimum": 0, "maximum": 10000},
        "max_nodes": {"type": "integer", "minimum": 1, "maximum": 128},
        "max_properties": {"type": "integer", "minimum": 1, "maximum": 128},
    },
    "animation": {
        "node_path": NODE_PATH,
        "animation": STRING,
        "name": STRING,
        "library": STRING,
        "length": {"type": "number", "exclusiveMinimum": 0},
        "track": {"type": "integer", "minimum": 0},
        "track_type": STRING,
        "property_path": NODE_PATH,
        "time": {"type": "number", "minimum": 0},
        "value": VALUE,
        "transition": {"type": "number"},
    },
    "animation-tree": {
        "node_path": NODE_PATH,
        "parent_path": NODE_PATH,
        "name": STRING,
        "tree_type": {"type": "string", "enum": ["state_machine", "blend_tree"]},
        "parameter": STRING,
        "value": VALUE,
        "state": STRING,
        "animation": STRING,
        "from": STRING,
        "to": STRING,
        "type": STRING,
        "position": VECTOR,
    },
    "scene-3d": {
        "node_path": NODE_PATH,
        "parent_path": NODE_PATH,
        "name": STRING,
        "primitive": STRING,
        "light_type": STRING,
        "properties": PROPERTIES,
        "mesh_properties": PROPERTIES,
    },
    "physics": {
        "node_path": NODE_PATH,
        "parent_path": NODE_PATH,
        "name": STRING,
        "is_3d": {"type": "boolean"},
        "shape": STRING,
        "properties": PROPERTIES,
        "shape_properties": PROPERTIES,
        "layer": {"type": "integer", "minimum": 0},
        "mask": {"type": "integer", "minimum": 0},
    },
    "particle": {
        "node_path": NODE_PATH,
        "parent_path": NODE_PATH,
        "name": STRING,
        "is_3d": {"type": "boolean"},
        "properties": PROPERTIES,
        "preset": {"type": "string", "enum": ["fire", "smoke", "sparks"]},
        "colors": {"type": "array", "items": STRING},
        "offsets": {"type": "array", "items": {"type": "number"}},
    },
    "navigation": {
        "node_path": NODE_PATH,
        "parent_path": NODE_PATH,
        "name": STRING,
        "is_3d": {"type": "boolean"},
        "properties": PROPERTIES,
        "layers": {"type": "integer", "minimum": 0},
        "from": VECTOR,
        "to": VECTOR,
        "optimize": {"type": "boolean"},
    },
    "audio": {
        "node_path": NODE_PATH,
        "parent_path": NODE_PATH,
        "name": STRING,
        "type": STRING,
        "stream_path": PATH,
        "bus": STRING,
        "effect_type": STRING,
        "properties": PROPERTIES,
        "volume_db": {"type": "number"},
        "mute": {"type": "boolean"},
        "solo": {"type": "boolean"},
        "bypass": {"type": "boolean"},
    },
    "tilemap": {
        "node_path": NODE_PATH,
        "cell": VECTOR,
        "position": VECTOR,
        "size": VECTOR,
        "source_id": {"type": "integer"},
        "atlas_coords": VECTOR,
        "alternative": {"type": "integer", "minimum": 0},
    },
    "theme-ui": {
        "path": PATH,
        "type": STRING,
        "item": STRING,
        "value": VALUE,
        "properties": PROPERTIES,
    },
    "shader": {
        "path": PATH,
        "shader_path": PATH,
        "node_path": NODE_PATH,
        "shader_type": STRING,
        "source": {"type": "string", "maxLength": 1000000},
        "search": {"type": "string", "maxLength": 100000},
        "replace": {"type": "string", "maxLength": 100000},
        "parameter": STRING,
        "value": VALUE,
    },
    "resource": {
        "path": PATH,
        "type": STRING,
        "properties": PROPERTIES,
        "name": STRING,
    },
    "batch-refactor": {
        "path": PATH,
        "type": STRING,
        "property": STRING,
        "value": VALUE,
        "query": STRING,
        "pattern": STRING,
        "reference": STRING,
        "extensions": {"type": "array", "items": STRING},
    },
    "analysis": {},
    "testing-qa": {
        "node_path": NODE_PATH,
        "steps": {"type": "array", "items": {"type": "object"}, "maxItems": 100},
        "equals": PROPERTIES,
        "text": STRING,
        "first": PATH,
        "second": PATH,
        "threshold": {"type": "number", "minimum": 0, "maximum": 1},
        "frames": {"type": "integer", "minimum": 1, "maximum": 120},
    },
    "profiling": {},
    "export": {
        "preset": STRING,
        "path": {"type": "string", "maxLength": 500},
        "debug": {"type": "boolean"},
    },
}

SCRIPT = """from dcc_mcp_core.skill import skill_entry

from dcc_mcp_godot.capability_dispatch import dispatch


@skill_entry
def main(_action_name: str = "", **params):
    return dispatch(_action_name, params)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
"""

# These handlers only wait on the Godot websocket. The plugin still performs
# the bounded host operation on Godot's own runtime thread.
REMOTE_BRIDGE_ANY_AFFINITY = {
    ("runtime", "find_ui_elements"),
    ("runtime", "get_game_node_properties"),
    ("runtime", "get_game_scene_tree"),
    ("runtime", "get_runtime_status"),
}


def _tool_yaml(category: str, name: str, description: str) -> str:
    read_only = name.startswith(READ_ONLY_PREFIXES)
    destructive = name in DESTRUCTIVE
    affinity = "any" if (category, name) in REMOTE_BRIDGE_ANY_AFFINITY else "main"
    if name == "execute_typed_action":
        schema = TYPED_ACTION_INPUT_SCHEMA
        output_schema = json.dumps(TYPED_ACTION_OUTPUT_SCHEMA, separators=(",", ":"))
    elif name == "execute_game_script":
        schema = COMPATIBILITY_METHOD_INPUT_SCHEMA
        output_schema = "{type: object}"
    else:
        schema = {
            "type": "object",
            "properties": CATEGORY_PROPERTIES[category],
            "additionalProperties": True,
        }
        output_schema = "{type: object}"
    input_schema = json.dumps(schema, separators=(",", ":"))
    return f"""  - name: {name}
    description: {description} Parameters are validated again by the Godot host.
    input_schema: {input_schema}
    output_schema: {output_schema}
    read_only: {str(read_only).lower()}
    destructive: {str(destructive).lower()}
    idempotent: {str(read_only).lower()}
    execution: sync
    affinity: {affinity}
    enforce_thread_affinity: true
    timeout_hint_secs: 60
    source_file: scripts/dispatch.py
"""


def generate() -> None:
    for category, tools in CATEGORIES.items():
        skill_name = f"godot-{category}"
        skill_dir = ROOT / skill_name
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "dispatch.py").write_text(SCRIPT, encoding="utf-8", newline="\n")
        descriptions = " ".join(description for _, description in tools)
        search_names = " ".join(name for name, _ in tools if name != "execute_game_script")
        runtime_guidance = ""
        if category == "runtime":
            runtime_guidance = (
                "\n\nFor playtest or future RL control, use `execute_typed_action` only. "
                "The host verifies the exact effect; rejected and cancelled actions do not "
                "consume authority. "
                "`execute_game_script` is compatibility-only broad public-method execution; "
                "it is not allowlisted and is never the typed action path. "
                "Polling reads accept `budget_ms` (1-50, default 40). A response with "
                "`budget_exceeded: true` is an incomplete page and must be resumed with its "
                "opaque `next_cursor`; never treat it as a complete snapshot."
            )
        if category == "editor":
            runtime_guidance = (
                "\n\nScreenshots copy pixels on the Godot thread and finalize PNG encoding in the "
                "adapter. Responses include measured `elapsed_ms`, `budget_ms`, and "
                "`budget_exceeded`; the budget is fail-closed for traversal work but cannot "
                "preempt user GDScript. Use `chunked=true` and caller-provided cursors for "
                "long editor scripts."
            )
        skill_md = f"""---
name: {skill_name}
description: >-
  Domain skill — {descriptions}
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot {category} {search_names}"
    tags: "godot,{category},game-development"
    tools: tools.yaml
---

# Godot {category.replace("-", " ").title()}

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.{runtime_guidance}
"""
        if category == "export":
            skill_md = """---
name: godot-export
description: >-
  Domain skill — Inspect export presets and templates, package Godot projects
  for desktop, Web, and mobile targets, and validate packaged-only resource,
  font, signing, and hosting failures. Use for export planning and release
  preflight, not for editing gameplay or scene content.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.2.0"
    search-hint: "__EXPORT_SEARCH_HINT__"
    tags: "godot,export,game-development"
    tools: tools.yaml
    skill-reference-docs:
      - "references/*.md"
---

# Godot Export

Use these editor-integrated tools after opening the target Godot project. Start
with `get_export_info` and `list_export_presets`; do not mutate a preset or
attempt a release export until the requested target and matching template are
known. Paths passed to the tools must remain under `res://`.

Read [Cross-platform packaging](references/platform-packaging.md) before
planning a release build, changing platform presets, or diagnosing a failure
that appears only after export. In particular, editor success is not release
evidence: launch the exported artifact on the target runtime and verify fonts,
resources, storage, input, and startup diagnostics.
"""
            skill_md = skill_md.replace(
                "__EXPORT_SEARCH_HINT__",
                "Godot export package release Windows macOS Linux Web Android iOS fonts CJK "
                "resources presets templates",
            )
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8", newline="\n")
        tools_yaml = "tools:\n" + "".join(_tool_yaml(category, *tool) for tool in tools)
        (skill_dir / "tools.yaml").write_text(tools_yaml, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    generate()
