# Dynamic fire and spellcasting

Use this recipe when a request combines fire shading, 3D particles, an animated
caster, and moving spells. Load `godot-vfx` on the target Godot instance. Keep
ordinary scene edits in `godot-node`, animation tracks in `godot-animation`,
emission controls in `godot-particle`, and shader edits in `godot-shader`.

## Start with a working scene

Call `create_spellcasting_demo` with:

```json
{"directory":"res://spell_vfx","auto_cast":true,"tint":"#ff6018"}
```

Open and run the returned `scene_path`. The scene includes an articulated mage,
arena, charge effect, animation-keyed release, travelling fire, and impact.
The generated files use relative dependencies and can be moved together.
The destination must be a new directory. The tool does not change the main
scene or overwrite a previous demo. A failed write preserves files for inspection;
use a new destination after diagnosing the error.

Use Space to cast manually, Q for a fast ember followed by a heavier strike,
and E for an aura followed by two arcane shots. Keys 1/2/3 change the single
cast palette. `cast_combo("ember_chain")` and `cast_combo("arcane_surge")`
reject overlapping sequences and stop the temporary aura when the sequence
finishes. The demo exposes release and impact counters for
verification. Disable `auto_cast` when evaluating one cast or integrating the
controller with gameplay. The procedural mage is a mesh-joint example; optional
imported characters must pass the skeleton and animation contract described in
[Mage assets and casting](mage-casting.md).

## Build the effect in an existing scene

Open a scene with a Node3D root, then call:

```json
{"parent_path":".","name":"DynamicFire","amount":48,"tint":"#ff6018"}
```

`create_dynamic_fire_vfx` adds a subtree containing visible particle draw meshes,
process materials, the fire shader, sparks, and an OmniLight3D. Save and reload
the scene to confirm all owned children and resource parameters persist. The
tool creates the whole subtree in one undoable edit.

Call `get_shader_params` with `node_path: "DynamicFire/Flames"`, then use
`set_shader_param` on the same node to tune `density`, `intensity`, or `dissolve`.
The draw pass and material override share the same ShaderMaterial.

| Control | Initial value | Use |
| --- | --- | --- |
| MCP `amount` | 48, allowed 8–256 | Flame count; inspect coverage before increasing |
| `density` / `edge_softness` | 0.62 / 0.13 | Fullness and eroded edge softness |
| `intensity` / `tint` | 2.8 / requested color | Bright interior and colored envelope |
| `texture_scale` / `scroll_speed` | 1.65 / 0.22 | Internal detail size and upward flow |
| `dissolve` | 0 | Increase toward 1 to erode visibility |
| `Flames.lifetime` / `local_coords` | 0.95 / false | Residual duration and world-space emission |
| `Light.light_energy` / `omni_range` | 1.5 / 3.0 | Illumination around the effect |

The shader values are material parameters, not extra `create_dynamic_fire_vfx`
arguments. Use `godot-particle` for particle motion/emission and ordinary node
properties for light settings. To attach a compact charge to a moving hand,
use local particle coordinates; free fire normally leaves emitted particles
in world space. Changing emission stops new particles, not existing ones.

For portable runtime construction after installing the library:

```gdscript
const FIRE = preload("res://combat_vfx/dynamic_fire.gd")

func add_fire() -> Node3D:
    var effect := FIRE.create(Color("ff873f"), 48)
    add_child(effect)
    return effect
```

`FIRE.set_emitting(effect, false)` stops both emitters and hides the light;
the caller owns removal after the particles fade. For editor-created effects,
save/reopen the whole subtree, including draw meshes and material subresources.

The layers serve different purposes:

| Layer | Visual role | Main controls |
| --- | --- | --- |
| Overlapping billboard quads | Rolling fire volume and irregular silhouette | Particle amount, spread, scale, lifetime |
| Noise or source texture | Internal lobes and erosion | Material sampler and threshold |
| Hot interior and colored edge | Readable fire temperature | Tint, intensity, opacity |
| Rising sparks | Direction and speed cues | Velocity, gravity, lifetime |
| Colored light | Contact with the floor and nearby geometry | Range and energy |

Start with 48 flame particles. Inspect the silhouette at gameplay distance
before increasing the count. Reduce overlapping transparent area first if the
effect becomes expensive. More particles can flatten the shape into a bright
blob; opacity, size variation, and lifecycle are as important as count.

For a licensed project texture, pass an imported `Texture2D` path:

```json
{"parent_path":".","name":"TexturedFire","texture_path":"res://textures/fire.png","tint":"#28aaff"}
```

The default uses original procedural textures and needs no downloads. Read
[Texture sources](texture-sources.md) before selecting an external image.
Tint changes offer cyan, orange, and magenta variations; they do not implement
different gameplay damage types.

## Attach a projectile to gameplay

`create_spell_projectile` creates an inert scripted Node3D:

```json
{"parent_path":".","name":"SpellProjectile","speed":8.0,"lifetime":4.0,"tint":"#ff6018"}
```

At runtime, place a new instance at the hand socket and call
`launch(target_global_position: Vector3)` from the release method. The projectile
moves in world space, emits a trail, checks its travelled segment for collision,
bursts at a hit or destination, and removes its remaining particles after their
lifetime. `impacted(position)` reports the event. Damage and targeting belong in
the game's own combat code.

The travel layer uses a camera-facing tapered ribbon with at most 32 samples.
The impact transitions from a short hot flash to an expanding envelope and
embers. In the copied runtime scene, `visual_scale`, `trail_length`, and
`impact_strength` tune the appearance; `acceleration_time` ramps travel from
30% to full speed (zero disables it). These are runtime properties, not extra
MCP arguments. A ribbon needs the active Camera3D. Validate camera changes and
overlapping transparent effects at the game's actual viewing distance.

| Runtime property | Default | Accepted finite range |
| --- | --- | --- |
| `visual_scale` | 1.0 | 0.25–3.0, presentation multiplier |
| `trail_length` | 2.2 | 0.2–6.0 world units |
| `impact_strength` | 1.0 | 0.25–3.0, presentation multiplier |
| `acceleration_time` | 0.12 | 0–0.4 physics seconds |
| `impact_on_arrival` | true | false makes an empty arrival a miss |
| `collision_mask` | 1 | Physics layer bitmask; pair with caster exclusions |

The four numeric presentation values are clamped to the listed ranges;
non-finite values reject launch before effects are created. Acceleration consumes part of the flight budget,
so speed times lifetime is not a guaranteed range, especially for short spells.

The current envelope is a soft, procedurally broken shape rather than a closed
rim. Its shader mode 2 changes the impact silhouette; modes 0/1/3 provide the
ribbon, hot core and rays. Keep the contact clock, particle budget and camera
fixed when comparing a silhouette edit. The current study's appearance is a
candidate preset, not an accepted quality target for every game.

For moving casters, explicit collision exclusions, and the total lifetime/tail
budget, follow [Gameplay integration](combat-integration.md). The installed
`fire_projectile.tscn` is the portable scene preset for future games.

Use an AnimationPlayer method track for release. The bundled example releases
at 0.90 seconds in a 1.85-second presentation cast. The imported source clip
remains 1.6 seconds with its release pose at 0.65; the copied bone tracks are
retimed to the presentation key. Re-time the event to the actual pose when
using another clip. A separate timer must not drift away from the animation.
The mage study duplicates the imported Cast clip, rebases its bone tracks, and
adds release events to the same CastTimeline. Changing its speed therefore
retimes both the pose and release. It preserves the GLB. A game's own character
clip still needs events at its actual release pose, as described in the integration guide.
For scene editing, `add_animation_track` with `track_type: "method"` and
`set_animation_keyframe` can insert a key with
`{"method":"release_spell","args":[]}`; the release method supplies the typed
Vector3 target. See the existing `godot-animation` tool schemas for field names.

## Verify the complete chain

1. Create, save, and reload the effect; confirm particle draw meshes, process
   materials, textures, lights, and exported parameters survived.
2. With auto casting off, play a cast. Before the release key, the release count
   must stay unchanged. Crossing the key creates exactly one projectile.
3. Confirm the hand moves with the arm and the projectile starts at that hand.
   Check the trail remains in world space as the projectile moves.
4. Confirm one impact event for collision or the default destination burst.
   With `impact_on_arrival=false`, an empty destination emits no impact; flight
   expiry also emits none. Verify bounded cleanup for all three outcomes.
   Repeat casts and verify the transient node count returns to its baseline.
5. Render actual frames on each intended renderer. Headless success verifies
   structure and behavior, not particle appearance. Check silhouette, texture
   erosion, animation changes, floor illumination, and opaque surfaces behind
   translucent particles. Desktop Mobile renderer testing is not mobile-device
   performance acceptance; exported Web/mobile builds require their own run.

Repository checks are `tests/live_godot_smoke.py` for the real bridge and
`tests/godot_project/spell_vfx_smoke.gd` for runtime behavior and native rendering.
Keep renderer output and source/model hashes with the result. Use the project
DCC-CUA route for any native UI observations or inputs; native render artifacts
do not imply that interactive UI acceptance was performed.

## References and scope

This is an original reusable implementation informed by the public description,
chapters, and preview of [Le Lu's dynamic fire tutorial](https://www.youtube.com/watch?v=Y1ZBzIiP-v4).
The public preview shows billowing colored fires, sparks, and floor lighting.
The mage, charge, projectile, and impact form the additional casting workflow.
It is not a claim of frame-for-frame reproduction of the full video.

Godot's [Animation resource](https://docs.godotengine.org/en/stable/classes/class_animation.html)
defines timed tracks, including method events. The
[GPUParticles3D reference](https://docs.godotengine.org/en/stable/classes/class_gpuparticles3d.html)
documents draw passes, lifetime, local coordinates, and visibility bounds.
