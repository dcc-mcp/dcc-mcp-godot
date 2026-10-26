# Reusable combat VFX

Use this workflow when producing attack, spell, aura, or area effects for a game.
Deliver a native scene preset, a clear gameplay trigger, and runtime evidence.
Keep the visual implementation reusable across characters and combat systems.

| Need | Existing entry point | Tune first |
| --- | --- | --- |
| Mesh flame, campfire or dissolve | `godot-shader.create_fire_vfx`; [mesh-fire guide](../../godot-shader/references/shader-vfx.md) | Noise, height erosion, gradient, sway |
| Billowing fire, sparks and light | `create_dynamic_fire_vfx`; [fire guide](spell-vfx.md) | Density, particle scale, emission and light |
| Animated caster and spell sequence | `create_spellcasting_demo`; [mage guide](mage-casting.md) | Socket, pose/event timing, charge and camera |
| Slash, impact, magic circle or aura | Installed presets below or `create_combat_vfx` | Anchor, radius, duration, tint and stop event |
| Travelling spell | `fire_projectile.tscn`; [integration guide](combat-integration.md) | World origin, target, collision policy and lifetime |

The magic circle is the `aura` component: use an actor anchor for a buff or a
world anchor for a ritual/area. A planar `impact` is a one-shot ring; the
projectile's burst adds fire, flash and a broken envelope. Choose these parts
by their visual role rather than adding a new controller for every spell.

## Install once per game

Load `godot-vfx`, then call `install_combat_vfx_library`:

```json
{"directory":"res://combat_vfx"}
```

The tool installs source shaders, scripts, scene presets, and a playable gallery
into a new directory. Existing files are never replaced and the main scene is
unchanged. Open the returned `gallery_scene` to inspect the effects. Keep the
directory together when moving it: dependencies are relative. The installed
library runs without DCC-MCP, its server, or network access.
The earlier cylinder-fire shader, billowing fire builder, and mage study are
included alongside the combat presets; their recipes remain in the linked guides.

Open `combat_vfx_gallery.tscn` as a scene in the same project and run that scene;
Space restarts its cycle. Its moving aura anchor demonstrates attachment, while
the world aura stays fixed. The gallery's impact is a scheduled display cue;
it is not proof of combat contact. Use the contact contract in the integration
guide when adopting the effect in a game.

| Preset | Typical game event | Coordinate ownership | Lifetime |
| --- | --- | --- | --- |
| `attack_slash.tscn` | Actual attack animation's strike key | Weapon/character anchor or a world snapshot | One shot, frees itself |
| `spell_impact.tscn` | Combat system confirms a hit or area detonation | World position and surface direction | One shot, frees itself |
| `magic_aura.tscn` | Buff applied / removed; area created / expired | Actor anchor for a buff, world root for an area | Loops until `stop()` |
| `fire_projectile.tscn` | Actual cast animation's release key | World root, explicit caster exclusions | Inert until `launch()`; bounded cleanup |

The aura shader contains independently rotating rings, segmented arc markings,
procedural rune-like strokes, an inner sigil, and local particle motes. The slash
uses a swept arc; the impact uses an expanding ring. These are original
procedural effects. Palette changes create variants without downloading assets.
Colors are cosmetic: they do not turn fire into frost damage or grant a buff.

## Save and reopen in the target project

Keep the existing main scene. Install the library once into a new directory,
instance a preset in the intended level, set its exported values, and save that
level with `godot-scene.save_scene`. Close/reopen the saved scene, read back the
properties, then restart the project and run it again. Confirm the material,
shader, particle draw pass and script paths resolve after reopening. Editor
creation alone does not verify persistence or rendering. Keep installed relative
dependencies together; nodes created directly from the addon need that addon
until their resource references have been moved into the project's library.

For existing scene authoring, call `create_combat_vfx`:

```json
{"parent_path":".","name":"HasteAura","effect":"aura","radius":1.5,"tint":"#55d9ff","autoplay":false,"auto_free":false}
```

The tool creates a runtime component whose exported settings survive saving.
Run the scene to build and preview its meshes and particles. `effect` accepts
`slash`, `impact`, or `aura`; the corresponding script property is `kind`.
This editor-created node refers to the addon's bundled script. For a game that
will ship independently, instance the installed presets instead.

## Shared component contract

`combat_effect.gd` has these exported settings:

| Setting | Meaning |
| --- | --- |
| `kind` | `slash`, `impact`, or `aura` |
| `tint` | Effect color; configure before playing |
| `radius` | Local radius in game units, 0.1–20; default scenes use metre-scale geometry |
| `duration` | Slash/impact duration, 0.05–10 seconds; aura remains active until stopped |
| `autoplay` | Start when the node enters the scene tree |
| `auto_free` | Remove the node after completion; false for a retained/reusable aura |

- `play() -> bool` validates settings, resets the local clock, and starts or
  restarts the effect. Configure first; adding an autoplay node starts it.
- `stop()` begins a bounded 0.25-second fade. Repeated stops do not restart it.
- `pulse(playback_speed=1.0) -> bool` contracts a playing aura to 0.48 of
  its nominal radius, expands to 1.35, then settles to 1.0. It rejects invalid
  speeds, overlapping pulses, stopped effects and non-aura kinds. Pass the
  cast animation speed to keep the contraction aligned with its release key.
- `finished` fires once at completion. Connect before adding an autoplay node
  if the caller needs this signal.
- `get_state()` reports `playing`, `phase`, `kind`, `stopping`, `visual_scale`,
  `footprint_radius`, and `pulse_phase` (-1 when no pulse is active).

Allow space for the aura's peak footprint: 1.35 times `radius`, before root
scale. Opening expands from 0.18 to 1.06 over 0.22 seconds and settles by
0.40 seconds. Pulse contraction/expansion/settling take 0.22/0.14/0.42
clip seconds, divided by the supplied speed. Stop contracts from the current
scale and fades over 0.25 process seconds, including an interrupted pulse.
These are adjustable study curves, not damage ranges or universal game-feel rules.

Meshes lie on local XZ with +Y normal; slash forward is -Z. Translate/rotate the
root to place a weapon trail or align an impact with a surface. Geometry sits
slightly above the local plane to avoid coplanar flicker. Root scale changes
the apparent size; normalize character/import scale before tuning `radius`.

Each instance owns its material and lifecycle. Shader animation uses the
instance's elapsed time and progress, so newly spawned hits begin at their
first frame. Aura animation loops, while slash/impact progress is finite.
Repeated play does not build additional mesh or particle children.

Read [Gameplay integration](combat-integration.md) before attaching these
components to attacks or buffs. Reuse the existing [fire and spell workflow](spell-vfx.md)
for textured flames and [mage workflow](mage-casting.md) for generated characters.

## Turn a new reference into a reusable effect

1. **Describe the readable shape.** Record silhouette, scale at the gameplay
   camera, palette, and the parts that must remain visible behind scenery.
   Separate what was actually observed from inferred implementation.
2. **Split the timeline.** Identify anticipation, release, travel/sustain,
   contact, and residual fade. Not every effect needs all five stages.
3. **Choose existing parts.** Use the slash arc, impact ring, persistent circle,
   fire particles, projectile trail, light, and animation event before adding
   another shader or controller. Add a new primitive only for a missing shape.
4. **Decide ownership.** Record the parent anchor, local/world transform, who
   stops the effect, and whether it survives the caster's removal.
5. **Save a native preset.** Set the exported values in a new `.tscn`; retain
   shared script/shader dependencies. Keep external textures' source and
   licensing evidence. Do not embed provider credentials in assets.
6. **Verify the playable result.** Save/reload, event timing, instance isolation,
   attachment motion, cancellation, repeated use, cleanup, renderer pixels,
   and the exported target build are separate checks.

For each new game preset, record: purpose, source reference, preset path,
palette/radius/duration, anchor, trigger, stop event, concurrent-effect budget,
tested renderer/device, and evidence paths. This small record plus the scene
is the reusable output; a screenshot alone is insufficient.

## Performance and quality

The circle/arc/impact uses one plane and one material per instance; the bundled
aura uses 20 motes and one local light. These are starting choices, not measured
performance guarantees. Particle fire has a different cost profile, especially
when large transparent quads overlap near the camera.

Profile the game's expected simultaneous effect count at its actual camera and
target resolution. Set a game-owned cosmetic spawn cap, reduce transparent
screen coverage and light count, then reduce particle count or material detail.
Only add pooling when measurements show allocation or shader warm-up is a
bottleneck; reusable `auto_free=false` scenes already support replay. A desktop
Mobile renderer pass does not establish phone or Web performance.
