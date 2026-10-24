---
name: godot-animation
description: >-
  Domain skill — List AnimationPlayer libraries and animations. Create an animation in an AnimationPlayer. Add a typed animation track. Insert a typed animation key with optional easing. Return animation tracks and keys. Remove an animation from a library.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot animation list_animations create_animation add_animation_track set_animation_keyframe get_animation_info remove_animation"
    tags: "godot,animation,game-development"
    tools: tools.yaml
---

# Godot Animation

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.

`set_animation_keyframe` uses the actual track type, not a caller-supplied type hint. Position/scale tracks accept exactly three finite numeric components. Rotation accepts a finite unit quaternion `[x, y, z, w]`; Euler angles, zero and non-unit quaternions are rejected, never normalized. Components, transition and audio offsets must fit the engine scalar range. Audio keys accept `{"stream_path": "res://step.wav", "start_offset": 0, "end_offset": 0}`. Offsets are optional and non-negative. The wav/ogg/mp3 must be a normalized project path without symlinks, successfully imported and already held in the editor resource cache, for example by an AudioStreamPlayer. Unloaded or scripted resources are rejected; this call never loads resources or parses import metadata. This is not an audit of resources the project already loaded. Existing value/method/bezier/animation payloads keep their semantics. Invalid input is rejected before insertion; a negative native key index is an error, never `inserted: true`. Repeated times use Godot's existing same-time key replacement semantics. Read back with `get_animation_info`, then save and reopen the scene to verify persistence. This is authoring evidence, not proof of rendered motion or audible synchronization.
