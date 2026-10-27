"""Generate the declarative Godot capability skills from a compact catalog."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1] / "src" / "dcc_mcp_godot" / "skills"

# Gameplay intent belongs in adapter guidance, not generic tool parameters or Core.
COLLISION_DESCRIPTIONS = {
    "scene-3d": "Choose explicit collision intent when creating or importing 3D objects.",
    "physics": "Implement solid, trigger, query-only, or none collision intent and verify it.",
    "testing-qa": "Gate collision acceptance on saved-scene physics and exploratory playtests.",
}
COLLISION_REFERENCE_ROUTE = """
Load `godot-physics` (`dcc-mcp-cli load-skill godot-physics --dcc-type godot`)
and read its `references/collision-intent.md` before accepting the scene.
Use `skill_refs__list` with `skill: godot-physics`, then `skill_refs__read`
with that skill and the returned path. The reference belongs to that skill;
do not resolve it relative to this skill or assume sibling filesystem access.
If it is unavailable, report the missing guidance and leave collision acceptance
unverified rather than silently skipping the gate.
"""
COLLISION_GUIDANCE = {
    "scene-3d": """

## Decide collision intent before creating objects

For every created or imported gameplay object, record `solid`, `trigger`,
`query-only`, or `none` and a reason based on gameplay semantics and reachability.
Do not add collision to every visible mesh, or assume a mesh already has it.
Reachable ground, walls, boulders, tree trunks, and solid chest parts normally
need blocking bodies; pickups and water need triggers or explicit queries;
soft foliage, particles, inaccessible backdrops, and UI normally need none.
Classify components separately when an object has both solid and interactive parts.
"""
    + COLLISION_REFERENCE_ROUTE,
    "physics": """

## Collision intent and acceptance

Read [Collision intent](references/collision-intent.md) before creating,
changing, or validating physics. Record `solid`, `trigger`, `query-only`, or
`none` with an explicit reason for each gameplay object or component.
`setup_physics_body` configures an existing node; it does not create a body.
`setup_collision` creates a shape under `parent_path`; it does not make a mesh
solid. Create the appropriate physics body or Area first using `godot-node`,
then inspect body type, enabled shape resource, transforms, layers, and masks.
The reference defines the save/reopen and real gameplay regression gate.
""",
    "testing-qa": """

## Collision regression gate

Require a reasoned `solid` / `trigger` / `query-only` / `none` inventory,
actual body/shape and layer/mask readback, visual alignment, save/reopen,
off-script exploration, and pickup height/line-of-sight checks. A screenshot,
node count, successful tool call, or one prescribed route cannot pass this gate.
Report passed, failed, and not measured checks separately; distinguish native
physics queries or direct script calls from real-input and rendered playtests.
"""
    + COLLISION_REFERENCE_ROUTE,
}

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
        (
            "get_scene_tree",
            "Return a scene hierarchy. Omit scene_path (or path) to read the edited "
            "scene; set it to read that .tscn/.scn from disk without opening it, "
            "except when it names the edited scene, which is reported with its "
            "unsaved editor changes. A disk read instantiates the scene, so @tool "
            "constructors may run.",
        ),
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
        (
            "assign_ui_texture",
            "Assign an imported, bounded project PNG to an existing native TextureRect.texture "
            "or Button.icon with undo and readback. Pending imports never report assignment.",
        ),
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
        (
            "validate_script",
            "Compile-check GDScript source or a project script. Reads path first; "
            "script_path is a deprecated alias kept for existing callers. An empty "
            "path with no source is rejected, never reported as valid.",
        ),
        ("search_in_files", "Search bounded text files under res://."),
    ],
    "editor": [
        ("get_editor_errors", "Return errors captured by the DCC-MCP editor plugin."),
        ("get_editor_screenshot", "Capture the selected editor viewport to a PNG."),
        (
            "render_scene_preview",
            "Render a scene offscreen to a PNG and report the rendering method and "
            "unique-color count you judge a frame by. Both are diagnostics, not proof. "
            "Requires a windowed host. "
            "The call is refused under --headless instead of returning a blank frame, and "
            "a requested rendering_method that is not the active one is an error, never a "
            "silent fallback. See docs/scene-preview.md for the per-platform support matrix.",
        ),
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
        ("get_input_actions", "List editor InputMap or explicitly selected project input actions."),
        (
            "set_input_action",
            "Update an editor input action, or explicitly persist one project binding.",
        ),
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
        ("set_animation_keyframe", "Insert a typed animation key with optional easing."),
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
    "vfx": [
        (
            "install_combat_vfx_library",
            "Install portable attack, spell, and aura scenes with a combat VFX gallery.",
        ),
        (
            "create_combat_vfx",
            "Add a configurable slash, impact, or persistent magic aura to a 3D scene.",
        ),
        (
            "create_dynamic_fire_vfx",
            "Create billowing 3D fire particles, sparks, and a colored light.",
        ),
        (
            "create_spell_projectile",
            "Create an inert fire projectile with travel, impact, and cleanup.",
        ),
        (
            "create_spellcasting_demo",
            "Install a portable mage casting demo in a new project folder.",
        ),
    ],
    "shader": [
        ("create_fire_vfx", "Create an animated, textured 3D fire with editable shader uniforms."),
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
        (
            "get_resource_preview",
            "Generate or return a cached resource preview in a windowed editor. "
            "Queues without waiting for the callback, with a 20-second polling deadline; "
            "headless and unsupported resources return available=false.",
        ),
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
        (
            "export_project",
            "Compatibility synchronous export; "
            "prefer start_export_job for observable long exports.",
        ),
        (
            "start_export_job",
            "Start or query an idempotently identified owned export child "
            "without blocking the editor.",
        ),
        (
            "get_export_job",
            "Read bounded export lifecycle state and complete log/output manifest receipts.",
        ),
        (
            "cancel_export_job",
            "Cancel only this adapter-owned export child and report actual cleanup state.",
        ),
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
    "render_",
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
    "start_export_job",
    "cancel_export_job",
}

STRING = {"type": "string", "maxLength": 500}
PATH = {"type": "string", "pattern": "^res://", "maxLength": 500}
NODE_PATH = {"type": "string", "maxLength": 500}
PROPERTIES = {"type": "object"}
VALUE = {}
VECTOR = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 4}

VFX_TINT = {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$", "default": "#ff6018"}
VFX_NODE = {
    "parent_path": {**NODE_PATH, "default": "."},
    "name": {"type": "string", "minLength": 1, "maxLength": 100},
    "tint": VFX_TINT,
}
VFX_PROPERTIES = {
    "install_combat_vfx_library": {
        "directory": {**PATH, "default": "res://combat_vfx"},
    },
    "create_combat_vfx": {
        **VFX_NODE,
        "effect": {"type": "string", "enum": ["slash", "impact", "aura"], "default": "aura"},
        "radius": {"type": "number", "minimum": 0.1, "maximum": 20, "default": 1.5},
        "duration": {"type": "number", "minimum": 0.05, "maximum": 10, "default": 0.6},
        "autoplay": {"type": "boolean", "default": True},
        "auto_free": {"type": "boolean", "default": False},
    },
    "create_dynamic_fire_vfx": {
        **VFX_NODE,
        "amount": {"type": "integer", "minimum": 8, "maximum": 256, "default": 48},
        "texture_path": PATH,
    },
    "create_spell_projectile": {
        **VFX_NODE,
        "speed": {"type": "number", "minimum": 0.1, "maximum": 100, "default": 8.0},
        "lifetime": {"type": "number", "minimum": 0.1, "maximum": 30, "default": 4.0},
    },
    "create_spellcasting_demo": {
        "directory": {**PATH, "default": "res://spell_vfx"},
        "mage_path": PATH,
        "tint": VFX_TINT,
        "auto_cast": {"type": "boolean", "default": True},
    },
}

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
TYPED_ACTION_CONTEXT_SCHEMA = {
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

TYPED_ACTION_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["success", "message", "context"],
    "properties": {
        "success": {"const": True},
        "message": {"type": "string"},
        "error": {"type": "null"},
        "prompt": {"type": ["string", "null"]},
        "context": TYPED_ACTION_CONTEXT_SCHEMA,
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
        "scene_path": PATH,
        "camera_path": NODE_PATH,
        "rendering_method": STRING,
        "width": {"type": "integer", "minimum": 16, "maximum": 4096},
        "height": {"type": "integer", "minimum": 16, "maximum": 4096},
        "frame_count": {"type": "integer", "minimum": 1, "maximum": 8},
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

UI_TEXTURE_CONTEXT_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "assigned",
                "status",
                "changed",
                "node_path",
                "node_type",
                "property",
                "resource_type",
                "resource_path",
                "resource_instance_id",
                "width",
                "height",
                "source_sha256",
                "native_rgba8_sha256",
                "source_native_rgba8_matches_import",
                "undo_registered",
            ],
            "properties": {
                "assigned": {"const": True},
                "status": {"enum": ["assigned", "unchanged"]},
                "changed": {"type": "boolean"},
                "node_path": NODE_PATH,
                "node_type": {"enum": ["TextureRect", "Button"]},
                "property": {"enum": ["texture", "icon"]},
                "resource_type": {"const": "CompressedTexture2D"},
                "resource_path": PATH,
                "resource_instance_id": {"type": "string", "minLength": 1, "maxLength": 32},
                "width": {"type": "integer", "minimum": 1, "maximum": 4096},
                "height": {"type": "integer", "minimum": 1, "maximum": 4096},
                "source_sha256": DIGEST,
                "native_rgba8_sha256": DIGEST,
                "source_native_rgba8_matches_import": {"type": "boolean"},
                "undo_registered": {"type": "boolean"},
            },
        },
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["assigned", "status", "reason"],
            "properties": {
                "assigned": {"const": False},
                "status": {
                    "enum": ["rejected", "import_pending", "import_failed", "assignment_failed"]
                },
                "reason": {"type": "string"},
                "rollback_verified": {"type": "boolean"},
            },
        },
    ],
}

UI_TEXTURE_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["success", "message", "context"],
    "properties": {
        "success": {"const": True},
        "message": {"type": "string"},
        "error": {"type": "null"},
        "prompt": {"type": ["string", "null"]},
        "context": UI_TEXTURE_CONTEXT_SCHEMA,
    },
}


RESOURCE_PREVIEW_CONTEXT_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "required": ["path", "available", "preview_path", "width", "height"],
            "properties": {
                "path": PATH,
                "available": {"const": True},
                "preview_path": PATH,
                "width": {"type": "integer", "minimum": 1, "maximum": 1024},
                "height": {"type": "integer", "minimum": 1, "maximum": 1024},
            },
            "additionalProperties": False,
        },
        {
            "type": "object",
            "required": ["path", "available", "reason"],
            "properties": {
                "path": PATH,
                "available": {"const": False},
                "reason": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ]
}
RESOURCE_PREVIEW_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["success", "message", "context"],
    "properties": {
        "success": {"const": True},
        "message": {"type": "string"},
        "error": {"type": "null"},
        "prompt": {"type": ["string", "null"]},
        "context": RESOURCE_PREVIEW_CONTEXT_SCHEMA,
    },
    "additionalProperties": False,
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
    if name == "assign_ui_texture":
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["node_path", "texture_path"],
            "properties": {
                "node_path": {"type": "string", "minLength": 1, "maxLength": 500},
                "texture_path": {
                    "type": "string",
                    "pattern": "^res://.+[.]png$",
                    "maxLength": 500,
                },
            },
        }
        output_schema = json.dumps(UI_TEXTURE_OUTPUT_SCHEMA, separators=(",", ":"))
    elif name == "get_resource_preview":
        # Keep the existing category input shape, but make a terminal result
        # distinguish real image evidence from an unavailable preview.
        schema = {
            "type": "object",
            "properties": CATEGORY_PROPERTIES[category],
            "additionalProperties": True,
        }
        output_schema = json.dumps(RESOURCE_PREVIEW_OUTPUT_SCHEMA, separators=(",", ":"))
    elif name == "start_export_job":
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["preset", "path", "request_id"],
            "properties": {
                "preset": {"type": "string", "minLength": 1, "maxLength": 500},
                "path": {"type": "string", "minLength": 1, "maxLength": 500},
                "request_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
                "debug": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 1800,
                    "default": 600,
                },
            },
        }
        output_schema = "{type: object}"
    elif name in {"get_export_job", "cancel_export_job"}:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["job_id"],
            "properties": {"job_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"}},
        }
        output_schema = "{type: object}"
    elif name in {"get_input_actions", "set_input_action"}:
        properties = {
            "source": {"type": "string", "enum": ["editor", "project"], "default": "editor"}
        }
        if name == "set_input_action":
            properties = {
                "action": {"type": "string", "minLength": 1, "maxLength": 500},
                "keycode": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8388606,
                    "description": (
                        "Known raw Godot Key constant, e.g. KEY_A=65. Host rejects enum "
                        "holes, lowercase ASCII and modifier masks."
                    ),
                },
                "deadzone": {"type": "number", "minimum": 0, "maximum": 1},
                "replace_events": {"type": "boolean", "default": False},
                "persist": {"type": "boolean", "default": False},
            }
        schema = {"type": "object", "properties": properties, "additionalProperties": False}
        if name == "set_input_action":
            schema["required"] = ["action"]
        output_schema = "{type: object}"
    elif name == "set_animation_keyframe":
        properties = dict(CATEGORY_PROPERTIES["animation"])
        properties["value"] = {
            "description": (
                "Payload follows the existing track type. 3D position/scale use exactly "
                "three finite numbers; rotation uses a finite unit quaternion [x,y,z,w] "
                "without normalization. Audio uses an object with stream_path and optional "
                "non-negative start_offset/end_offset, and requires a native wav/ogg/mp3 "
                "already imported and held in the editor resource cache. No resource is "
                "loaded by this call. Other track payloads keep their native semantics."
            )
        }
        schema = {
            "type": "object",
            "required": ["animation", "track", "value"],
            "properties": properties,
            "additionalProperties": True,
        }
        output_schema = "{type: object}"
    elif name == "execute_typed_action":
        schema = TYPED_ACTION_INPUT_SCHEMA
        output_schema = json.dumps(TYPED_ACTION_OUTPUT_SCHEMA, separators=(",", ":"))
    elif name == "execute_game_script":
        schema = COMPATIBILITY_METHOD_INPUT_SCHEMA
        output_schema = "{type: object}"
    elif name in VFX_PROPERTIES:
        schema = {
            "type": "object",
            "properties": VFX_PROPERTIES[name],
            "additionalProperties": False,
        }
        output_schema = "{type: object}"
    elif name == "create_fire_vfx":
        schema = {
            "type": "object",
            "properties": {
                "parent_path": {**NODE_PATH, "default": "."},
                "name": {"type": "string", "minLength": 1, "maxLength": 100, "default": "FireVFX"},
            },
            "additionalProperties": False,
        }
        output_schema = "{type: object}"
    else:
        schema = {
            "type": "object",
            "properties": CATEGORY_PROPERTIES[category],
            "additionalProperties": True,
        }
        output_schema = "{type: object}"
    input_schema = json.dumps(schema, separators=(",", ":"))
    # Serialize the description instead of pasting it into the manifest bare. A
    # plain scalar containing ": " is not valid YAML, and one bad description
    # makes the whole tools.yaml unparseable, which takes every tool in the
    # skill down at load time. json.dumps emits a YAML double-quoted scalar, so
    # a colon-heavy description cannot produce a broken manifest.
    validation = "Parameters are validated again by the Godot host."
    if name in {"start_export_job", "get_export_job", "cancel_export_job"}:
        validation = "Parameters are validated by the adapter export-job contract."
    full_description = f"{description} {validation}"
    idempotent = read_only or name in {"assign_ui_texture", "start_export_job", "cancel_export_job"}
    return f"""  - name: {name}
    description: {json.dumps(full_description)}
    input_schema: {input_schema}
    output_schema: {output_schema}
    read_only: {str(read_only).lower()}
    destructive: {str(destructive).lower()}
    idempotent: {str(idempotent).lower()}
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
        # Explicit bytes preserve LF on Windows and support Python 3.9, where
        # Path.write_text does not yet accept a newline argument.
        (scripts_dir / "dispatch.py").write_bytes(SCRIPT.encode("utf-8"))
        descriptions = " ".join(description for _, description in tools)
        search_names = " ".join(name for name, _ in tools if name != "execute_game_script")
        version = "0.1.0"
        reference_metadata = ""
        if category in COLLISION_GUIDANCE:
            descriptions += " " + COLLISION_DESCRIPTIONS[category]
            search_names += (
                " collision intent solid trigger query-only none reachability regression"
            )
            version = "0.2.0"
        if category == "physics":
            reference_metadata = '\n    skill-reference-docs:\n      - "references/*.md"'
        runtime_guidance = ""
        if category == "input":
            runtime_guidance = (
                "\n\n`set_input_action` defaults to `persist: false`: it edits only the editor "
                "process InputMap, does not save, and does not rebind a running game. "
                "Use `persist: true` to author one `input/<action>` project default. "
                "This mode reads the project's existing events, never copies editor shortcuts, "
                "and leaves the editor InputMap unchanged. `ProjectSettings.save()` saves the "
                "whole current project configuration, including other unsaved settings. "
                "Save failures restore the target in-memory setting and return an error; "
                "disk rollback is not guaranteed. Start/restart the game to load saved defaults. "
                "Use `get_input_actions` with `source: project` to inspect project settings; "
                "the default `source: editor` preserves the legacy view (excluding `ui_` actions). "
                "Project queries include built-in UI actions. Events are human-readable strings, "
                "not round-trip event payloads.\n\n"
                "The setter authors one logical `keycode` only. Existing mouse, joypad, physical "
                "key, modifier and device bindings remain intact unless `replace_events: true` "
                "explicitly clears all events. Omitting `keycode` adds nothing; replacement "
                "without it clears the action. Omitting `deadzone` preserves it, or uses 0.5 "
                "for a new action; existing settings without it use the native 0.2 default. "
                "Null event entries are preserved (shown as empty placeholders by the getter). "
                "`events`, `button`, and simulation parameters are not accepted "
                "by this setter; they do not describe an implemented event-authoring API. "
                "Use simulation tools for the running game, not for project persistence."
            )
        if category == "animation":
            runtime_guidance = (
                "\n\n`set_animation_keyframe` uses the actual track type, not a caller-supplied "
                "type hint. Position/scale tracks accept exactly three finite numeric "
                "components. Rotation accepts a finite unit quaternion `[x, y, z, w]`; "
                "Euler angles, zero and non-unit quaternions are rejected, never normalized. "
                "Components, transition and audio offsets must fit the engine scalar range. "
                'Audio keys accept `{"stream_path": "res://step.wav", '
                '"start_offset": 0, "end_offset": 0}`. Offsets are optional and non-negative. '
                "The wav/ogg/mp3 must be a normalized project path without symlinks, "
                "successfully imported and already held in the editor resource cache, "
                "for example by an AudioStreamPlayer. Unloaded or scripted resources are "
                "rejected; this call never loads resources or parses import metadata. "
                "This is not an audit of resources the project already loaded. "
                "Existing value/method/bezier/animation payloads keep their semantics. "
                "Invalid input is rejected before insertion; a negative native key index "
                "is an error, never `inserted: true`. Repeated times use Godot's existing "
                "same-time key replacement semantics. Read back with `get_animation_info`, "
                "then save and reopen the scene to verify persistence. This is authoring "
                "evidence, not proof of rendered motion or audible synchronization."
            )
        if category == "node":
            runtime_guidance = (
                "\n\n`assign_ui_texture` accepts only `node_path` (relative to the edited scene) "
                "and `texture_path` (a contained lowercase `.png` path). Targets must be native "
                "TextureRect or Button nodes without attached scripts. PNGs are limited to "
                "16 MiB, 4096 pixels per side and 4,194,304 total pixels. Finish the normal "
                "editor Lossless import with mipmaps disabled first; `import_pending` means "
                "no assignment. Retry after import completes, including after changing PNG bytes. "
                "The tool preserves PNG resource references and existing cached scene references, "
                "checks native pixels, and registers undo only for a changed assignment. "
                "Save the scene with `save_scene` for persistence. See `docs/ui-texture.md` "
                "in the source repository for the full contract."
            )
        if category == "runtime":
            runtime_guidance = (
                "\n\nFor playtest or future RL control, use `execute_typed_action` only. "
                "The host verifies the exact effect; rejected and cancelled actions do not "
                "consume authority. A digest-bound host intent is authorized before runtime "
                "mutation, so a delayed commit after terminal timeout is rejected. "
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
                "long editor scripts. `render_scene_preview` renders a `.tscn`/`.scn` offscreen "
                "and returns `rendering_method` and `unique_colors` with every frame: it needs "
                "a windowed host (`--headless` degrades to `rendering/dummy` and is refused, not "
                "silently blanked), and it errors instead of rendering when a requested "
                "`rendering_method` is not the one actually active. Platform coverage is per "
                "launch path and is measured or explicitly not measured, so see "
                "`docs/scene-preview.md` before promising headless or unattended rendering."
            )
        if category == "shader":
            search_names += " VFX stylized fire dissolve noise texture gradient"
            runtime_guidance = (
                "\n\nUse `create_fire_vfx` below a Node3D for a complete original 3D fire: "
                "subdivided cylinder, two scrolling noise textures, gradient, vertex motion, "
                "and dissolve. Tune it with `set_shader_param`; uniform names and types are "
                "validated by the host. Read [Shader VFX](references/shader-vfx.md) for the "
                "recipe, typed values, renderer limits, and validation workflow."
            )
        if category == "vfx":
            search_names += (
                " combat attack melee slash aura buff magic circle rune spell mage fire"
                " particles sparks projectile impact casting Hyper3D"
            )
            runtime_guidance = (
                "\n\nFor reusable game effects, start with "
                "[Combat VFX](references/combat-vfx.md). `install_combat_vfx_library` "
                "copies native scene presets and a gallery to a new project folder; the game "
                "can run them without the adapter. Presets include mesh fire, particle fire, "
                "slash, impact, aura and projectile; the gallery exposes both fire techniques "
                "alongside the combat effects. `create_combat_vfx` adds an adjustable "
                "slash, impact, or magic aura to the edited scene. "
                "The aura separates its ground contour, floating rune orbit, and inner seal; "
                "their reveals and stop fades remain tied to the effect lifecycle. "
                "[Gameplay integration](references/combat-integration.md) defines animation "
                "events, local/world anchors, aura start/stop, projectile exclusions, lifecycle "
                "checks, and performance budgets. Keep damage and buffs in the game."
                "\n\nRead [Spell VFX](references/spell-vfx.md) for the fire workflow: "
                "billowing particle fire, procedural or licensed input textures, skinned mage "
                "import, animation-keyed release, flight trails, impact, and cleanup. "
                "`create_spellcasting_demo` installs a portable example in a new directory "
                "without changing the main scene. Its default articulated mage needs no external "
                "assets. Optional `mage_path` requires a Skeleton3D with `RightCastSocket` and "
                "a `Cast` animation; a static Hyper3D GLB must be rigged first. "
                "Use a complete authored casting clip for body weight, gathering and recoil; "
                "the demo retimes its release event while preserving imported poses and "
                "interpolation. Review uninterrupted motion before polishing effects; "
                "numerical articulation checks do not establish natural animation. "
                "Its palm sigil reuses the aura lifecycle. Keep player movement and grounding "
                "with the game's character controller when adapting it. "
                "Tune the demo's native cue level with `sound_gain_db`; verify the rendered "
                "mix and natural-speed listening separately. "
                "Reuse `godot-animation` for method tracks, `godot-particle` for emission tuning, "
                "and `godot-shader` for checked shader uniforms."
            )
        if category in {"shader", "vfx"}:
            reference_metadata = '\n    skill-reference-docs:\n      - "references/*.md"'
            version = "0.2.0"
        introduction = (
            "Use these editor-integrated tools after opening the target Godot project. "
            "Paths must remain under `res://`."
        )
        guidance = (runtime_guidance + COLLISION_GUIDANCE.get(category, "")).rstrip("\n")
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
    version: "{version}"
    search-hint: "Godot {category} {search_names}"
    tags: "godot,{category},game-development"
    tools: tools.yaml{reference_metadata}
---

# Godot {category.replace("-", " ").title()}

{introduction}{guidance}
"""

        if category == "resource":
            skill_md += """

## Resource preview contract

`get_resource_preview` keeps its `path` input. For queued windowed requests,
`available` is returned only after Godot's callback completes.
`available: true` always includes `preview_path`;
`available: false` is explicitly unavailable, never image evidence. The editor
must be windowed: Godot disables its resource-preview worker in headless mode.
Only one resource request may be pending; a second call fails busy. Scene-preview
requests use a separate slot. The 20-second polling deadline, bridge disconnect and plugin
unload invalidate late callbacks. It is not a hard wall-clock completion guarantee:
Godot generation and bounded image conversion/PNG writes may use the main thread.
Closing a scene tab does not change this disk
resource operation. There is no native dequeue API or per-call cancel parameter;
HTTP client cancellation does not synchronously stop Godot generation.
Do not automatically retry an uncertain transport outcome.

Paths, including output directories, cannot traverse symlinks. A source or
.import metadata change during the request fails before publication. This follows
Godot's mtime/size cache semantics, not content-addressed freshness: same-second,
equal-length edits, changed dependencies, unsaved edits and changes during native
generation do not guarantee latest pixels. This is a Godot editor cached
thumbnail, not a content-addressed snapshot. Images are bounded to
1024 pixels per dimension and 4 MiB of native image data. PNG writes use a staged
file before rename; an unavailable/failed result never points to an older image.
"""
        if category == "export":
            skill_md = """---
name: godot-export
description: >-
  Domain skill — Inspect export presets and templates, package Godot projects
  for desktop EXE/standalone, Web, and mobile targets, and validate packaged-only resource,
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

For a packaging, runnable game, standalone, EXE, or playtest delivery request,
report readiness in the first response, before authoring or opening a GUI.
Read [Cross-platform packaging](references/platform-packaging.md) and identify
the exact engine version/build, edition, architecture, target OS, named preset,
matching template identity/cache, disk needs and download size. State missing
inputs immediately. An EXE request is not download permission; preserve existing
projects, saves and caches while resolving dependencies through normal consent.

Use these editor-integrated tools after opening the target Godot project. Start
with `get_export_info` and `list_export_presets`; do not mutate a preset or
attempt a release export until the requested target and matching template are
known. Paths passed to the tools must remain under `res://`.

Prefer `start_export_job` with a stable 32-hex request ID and a fresh dedicated
output directory, then `get_export_job`. A lost start response is queried with
that same ID, never blindly repeated under a new ID. `cancel_export_job` reports
actual child cleanup, not assumed termination. Unknown outcomes keep the project
busy. Complete logs and output hashes are file receipts, not truncated bridge
text. Windows cleanup is direct-child-only; do not claim all descendants stopped.
One lazy export manager exclusively owns a registry journal across processes;
other adapters sharing it receive busy without changing records or spawning.
Use the existing explicit private-registry option for isolated adapters; concurrent
multi-Godot exports sharing one registry are not supported in this version.
The legacy `export_project` remains synchronous and can exceed bridge deadlines.

Read [Cross-platform packaging](references/platform-packaging.md) before
planning a release build, changing platform presets, or diagnosing a failure
that appears only after export. In particular, editor success is not release
evidence: launch the exported artifact on the target runtime and verify fonts,
resources, storage, input, and startup diagnostics.
"""
            skill_md = skill_md.replace(
                "__EXPORT_SEARCH_HINT__",
                "Godot export package release runnable standalone EXE Windows macOS Linux Web "
                "Android iOS fonts CJK resources presets templates",
            )
        (skill_dir / "SKILL.md").write_bytes(skill_md.encode("utf-8"))
        tools_yaml = "tools:\n" + "".join(_tool_yaml(category, *tool) for tool in tools)
        (skill_dir / "tools.yaml").write_bytes(tools_yaml.encode("utf-8"))


if __name__ == "__main__":
    generate()
