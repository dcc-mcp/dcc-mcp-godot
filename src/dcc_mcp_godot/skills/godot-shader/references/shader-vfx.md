# Shader VFX

Use `godot-shader` for shader authoring and `godot-scene-3d` for the surrounding
scene, camera, and environment. Inspect the target scene before editing it.
All paths must remain inside the project under `res://`.

## Stylized 3D fire

`create_fire_vfx` creates a complete `MeshInstance3D` below an existing `Node3D`:

```json
{"parent_path":".","name":"Campfire"}
```

Use the returned node path for subsequent calls. The tool participates in editor
undo and does not save the scene; call `save_scene` when the result is ready.
Each effect owns its material and procedural textures, so tuning one fire does
not change another. The shader remains a bundled addon resource; keep the addon
installed when moving or exporting a scene that references it.

For a portable game, `godot-vfx.install_combat_vfx_library` also copies
`stylized_fire.gdshader`. Point the existing ShaderMaterial at that copied
shader, retain its noise/gradient subresources and parameter values, then save
and reopen the scene. Verify that the saved resource no longer depends on an
addon path before removing the addon. This is still the same mesh-fire effect;
use [dynamic fire](../../godot-vfx/references/spell-vfx.md) when overlapping
billboards, sparks and local illumination are the intended shape.

The native effect combines these components:

| Technique | Implementation |
| --- | --- |
| 3D silhouette | Uncapped `CylinderMesh` with 64 radial segments and 24 rings |
| Rising flow | Two seamless `NoiseTexture2D` resources sampled at different speeds |
| Broken flame edges | Noise subtraction, height erosion, and smooth alpha threshold |
| Color | `GradientTexture1D`, hot at the base and cooler at the tip |
| Motion | Height weighted vertex taper, twist, and sway |
| Vanishing | `dissolve`: 0 visible, 1 fully transparent |

The textures use native deterministic `FastNoiseLite`; no download or artist
texture pack is required. This is a mesh effect, suitable for campfires and
spell flames. It does not simulate fluid, smoke, or volumetric fire.

Tune the effect with `set_shader_param`, for example:

```json
{"node_path":"Campfire","parameter":"scroll_speed","value":1.1}
```

```json
{"node_path":"Campfire","parameter":"noise_scale","value":[3.0,1.8]}
```

```json
{"node_path":"Campfire","parameter":"dissolve","value":0.5}
```

| Uniform | Initial value / purpose |
| --- | --- |
| `noise_texture`, `detail_texture` | Main and subtractive noise textures |
| `color_ramp` | Horizontal gradient texture, base at 0 and tip at 1 |
| `scroll_speed` | 0.65; rising flow speed |
| `noise_scale`, `detail_scale` | `[3.0,1.4]`, `[5.0,2.0]`; UV tiling |
| `erosion` | 0.4; detail subtraction strength |
| `edge_softness` | 0.08; alpha transition width |
| `sway`, `twist` | 0.18, 0.9; vertex displacement and swirl |
| `emission_strength` | 1.6; emissive brightness |
| `dissolve` | 0; visibility and erosion transition |

For a blue spell flame, save a blue/cyan `GradientTexture1D` as a project `.tres`
and set `color_ramp` to that path. Use ordinary node transforms to place and scale
the fire. Increase `custom_aabb` if custom vertex edits exceed the supplied bounds.
For extra sparks, load `godot-particle` separately and configure a 3D draw mesh
and world unit velocities explicitly.

## Typed uniform values

`set_shader_param` checks the declared uniform name and type before mutation:

| Shader type | JSON value |
| --- | --- |
| `bool` | Boolean |
| `int` | Finite integral number |
| `float` | Finite number |
| `vec2`, `vec3`, `vec4` | Exact length numeric array |
| Color (`source_color`) | `#rrggbb` / `#rrggbbaa`; `[r,g,b]` for a no-alpha RGB hint (alpha becomes 1), `[r,g,b,a]` otherwise |
| `sampler2D` | Existing `Texture2D` resource path under `res://`, or `null` |

Unknown uniforms, invalid component counts, nonfinite values, mismatched resource
types, and paths outside the project are rejected. Matrices, boolean/integer vectors,
uniform arrays, and other sampler types are not supported by this setter.
Unsigned integers with native unsigned metadata are rejected; signed integers use
the 32 bit range. Custom integer range hints should stay within that range.
Use `get_shader_params` for readback; generated textures have no external resource
path until they are saved. Shader range hints guide editing; stay within the
documented values when animating parameters.

## Verification

1. Create a dedicated `Node3D` scene, call `create_fire_vfx`, add a camera, then
   read back the uniforms and save the scene.
2. Run the scene with a real renderer. Wait for procedural texture generation
   before capturing pixels; `NoiseTexture2D` generates asynchronously.
3. Check at least two times for motion and compare `dissolve=0` with `dissolve=1`.
   Verify visible flame pixels, transparent edges, and disappearance against the
   same background. A shader resource loading in headless mode proves structure,
   not visible GPU output.
4. Inspect editor/runtime errors. Validate the intended renderer and exported
   target separately before release. Bloom depends on the environment and renderer;
   this effect does not require bloom to be visible.

The repository's `tests/live_godot_smoke.py` exercises the production MCP bridge
and saves `vfx_fire.tscn` in its isolated test project. The accompanying
`fire_vfx_smoke.gd` checks saved resources and optionally performs GPU pixel checks.

Godot references: [spatial shaders](https://docs.godotengine.org/en/stable/tutorials/shaders/shader_reference/spatial_shader.html),
[CylinderMesh](https://docs.godotengine.org/en/stable/classes/class_cylindermesh.html),
[NoiseTexture2D](https://docs.godotengine.org/en/stable/classes/class_noisetexture2d.html).
