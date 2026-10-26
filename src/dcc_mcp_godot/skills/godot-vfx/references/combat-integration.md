# Connect visuals to gameplay

The combat system owns attack validity, cooldowns, damage, buffs, targets,
team rules, and replication. VFX respond to these decisions. Rendering can be
reduced or disabled without changing the outcome of an attack.

## Reuse the response contract

Describe an attack as accepted → windup → release → contact → aftermath →
recover. A stage can have zero duration; a miss can skip contact. Acceptance
comes from the game's input/ability rules, release from its animation or
simulation event, and contact from its hit result. Never manufacture contact
merely because a projectile reached a requested empty point.

Keep a small per-preset record alongside the scene:

| Field | What to record |
| --- | --- |
| Timing | Stage times, units, clock domain, animation speed, interruption policy |
| Shape | Charge, projectile, impact and aura radius/opacity curves |
| Strength | Per-beat presentation amplitude, separately from damage values |
| Camera | Framing, optional impulse, off switch and screen-coverage limits |
| Gameplay windows | Input buffer, cancellation, combo and damage windows, or explicitly unimplemented |
| Evidence | Original reference, reconstructed controls, source hashes, event trace and actual render review |

Use contact to trigger heavy impact feedback. A release flash may play on a
miss; a hit burst, target reaction or contact camera impulse must not. Keep
feedback optional and bounded. The mage example has no global hitstop and no
damage or real input-buffer system. Its automatic follow-up delay is a
presentation sequence, not a gameplay combo window.

Godot's animation seconds advance with AnimationPlayer speed; projectile
motion uses physics delta and aura fade uses process delta. These are scaled
engine clocks, not wall-clock timers. This sample does not establish behavior
under global pause, slow motion or network rollback; validate those in the
game before adding them to its preset contract.

## Animation events and one-shot effects

Put the VFX event on the **actual attack/cast animation** or the game's animation
state event. An AnimationPlayer method key can call `show_slash()` or
`release_spell()` at the release pose. This stays aligned when animation speed
changes. Do not introduce an independent wall-clock timer. The mage study
duplicates its imported bone tracks into the event timeline; adapt the event
pose to the game's own clip instead of copying the example's 0.90-second key.

Keep an explicit world VFX root in the active level. For example, the actor can
hold a reference to it and spawn a slash from the weapon's current transform:

```gdscript
const SLASH = preload("res://combat_vfx/attack_slash.tscn")

func show_slash() -> void:
    var effect := SLASH.instantiate()
    effect.autoplay = false
    effect.tint = Color("ffb84d")
    effect.radius = 1.8
    vfx_root.add_child(effect)
    effect.global_transform = weapon_socket.global_transform
    effect.play()
```

The preset frees itself after completion. A world snapshot remains where the
attack was released. For an effect that should track the weapon for its whole
duration, add it below the weapon socket and use its local transform instead.
The actor's removal then removes its attached effects too.

Use the same pattern for `spell_impact.tscn`, triggered by an authoritative hit
event. Place the root at the hit position and rotate its +Y normal to match the
surface. Horizontal ground rings are the default; do not show a floor-oriented
ring embedded in a vertical wall.

## Persistent aura

Instance `magic_aura.tscn` once under the character's ground anchor. Set
`autoplay=false` and `auto_free=false` before adding it. A game-owned buff event
starts or stops that instance:

```gdscript
func on_haste_changed(enabled: bool) -> void:
    if enabled:
        haste_aura.play()
    else:
        haste_aura.stop()
```

Avoid issuing `play()` every frame: it intentionally restarts the animation.
Buff refresh policy belongs in the buff system. The aura can stop, finish its
fade, and play again without accumulating children. For a stationary area spell,
put the same preset under the world root instead of the actor. On area expiry,
call `stop()` and remove the retained instance after `finished`, or set
`auto_free=true` for that instance.

## Fire projectile

The reusable projectile starts inert. Place it before launch and supply explicit
caster bodies when it lives under the world VFX root:

```gdscript
const FIREBALL = preload("res://combat_vfx/fire_projectile.tscn")

func release_spell(target_position: Vector3) -> void:
    var effect := FIREBALL.instantiate()
    effect.speed = 8.0
    effect.lifetime = 4.0
    effect.impact_on_arrival = false
    vfx_root.add_child(effect)
    effect.global_transform = cast_socket.global_transform
    var exclusions: Array[RID] = [caster_body.get_rid()]
    effect.launch(target_position, exclusions)
```

Configure and connect signals before launch. A new projectile is single-use;
do not call `launch()` each frame or expect a second call to restart it. The
example chooses collision-only feedback. For a deliberate cosmetic detonation
at a point, explicitly retain `impact_on_arrival=true` and keep damage separate.

`launch(target, excluded_bodies=[])` retains the launch transform and makes the
node top-level, so moving or rotating its parent does not redirect its flight.
Ancestor collision bodies are excluded automatically; a detached projectile
needs the explicit caster list. Set `collision_mask` for the game's physics
layers. It uses a swept segment to avoid skipping thin colliders at high speed.

Top-level transform independence does not change scene ownership: deleting a
parent still deletes the projectile. Put lingering spells under the level's
VFX root when they must survive caster removal. Keep the original one-argument
`launch(target)` for scenes that need no explicit exclusions.

`lifetime` is a **total visual time budget**, including the residual tail. The
reserved tail is `min(0.95, lifetime * 0.25)` seconds; flight stops before this
tail interval. `impacted(position)` describes a cosmetic burst when a collider
is reached **or the requested destination is reached**. It does not prove a
combat hit, identify an enemy, or authorize damage. Use the game's own collision
and combat result when accuracy or replication matters.

The runtime property `impact_on_arrival` defaults to `true`. Set it to `false` when reaching an empty
destination must count as a miss. It stops flight and cleans up without an
impact signal or explosion. `get_state().impact_kind` is initially `""`, then
`"collision"`, `"destination"`, `"missed"`, or `"expired"`. The mage study uses this mode
with a spherical target collider, so its heavy feedback follows contact. This
still does not implement health, hurtboxes, damage windows, or damage authority.

The mage's target is a radius-0.30 sphere on physics layer 1. That is a demo
collider, not a reusable hurtbox policy. Replace it with the game's collision
layers and hit result. Put any ground effect on the actual surface and align
its normal; the mage's horizontal floor placement is specific to its arena.

## Required checks when adopting the library

| Check | Failure it catches |
| --- | --- |
| Instantiate from a copied directory without the addon | Hidden dependencies on an authoring installation |
| Save/reload exported values | Lost presets or scene-owned resources |
| Change one instance's tint/radius | Shared material state leaking across effects |
| Replay a one-shot; start/stop/restart an aura | Duplicate completion events or accumulated children |
| Stop at early and late phases | Effects that can only finish naturally |
| Move the actor during flight | Projectiles inheriting caster motion |
| Exclude caster, retain target collisions | Self-hits or masks that disable all collision |
| Remove caster/level | Orphaned effects and ownership mistakes |
| Test simultaneous effects at the gameplay camera | Fill-rate, light-count, or frame-time spikes |
| Run exported build on intended platform | Missing shader/resource/import and platform differences |

The repository's `combat_vfx_smoke.gd` exercises lifecycle, isolation, projectile
motion and collision, and native frame differences. `live_godot_smoke.py` also
creates effects through the production bridge, rejects malformed requests, and
runs the copied library without the addon. Keep native renderer captures and
source hashes with the game's own performance/export evidence.

Use the project DCC-CUA route for any editor UI observation or input. Engine
rendered images and headless assertions validate different boundaries from an
interactive UI or packaged-game acceptance run.
