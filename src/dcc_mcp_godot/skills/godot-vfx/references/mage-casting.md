# Mage assets and animation events

## Choose the character route

Omit `mage_path` for the original procedural articulated mage. This route needs
no generated model, provider account or external texture pack and is the portable
default. An existing rigged character can use the same socket/event contract.

The study can use an existing Hyper3D mage with a locally fitted rig.
The model is not bundled in the skill package. Record its generation source and
separate permissions for rendered media and raw-model/project redistribution.
Keep these permissions separate from the original procedural VFX code.

## Asset generation

Use the existing Hyper3D provider skill for generation. Check its current tool
schema, balance, and pricing; submit once and poll the returned task rather
than repeating a paid submission after an ambiguous response. Keep API keys,
task receipts, and signed download URLs out of project files and public docs.

A useful starting prompt is an adult stylized humanoid wizard, navy cloth and
gold trim, visible separated hands and boots, straight T-pose, clean silhouette,
no staff, no magic baked into the mesh, and a moderate game-ready triangle count.
Download GLB with embedded PBR maps. Record its hash, geometry count, source, and
usage terms. The provider may return only static geometry; never infer rigging
from a T-pose option or from a successful import.

## Prepare the character

The bundled demo has a deliberately narrow import contract:

- A `Node3D` scene root contains a child `Skeleton3D` with a bone named
  `RightCastSocket` at the right palm.
- An `AnimationPlayer` has a `Cast` clip (a library prefix is allowed).
- Cast duration is 1.6 seconds, with the release pose at 0.65 seconds.
- The model is upright on +Y, faces -Z, and is approximately 1.9 units tall.
- Optional `Idle` animation provides the resting pose.

Bind the mesh to the skeleton with normalized weights and valid inverse bind
matrices. Animate upper arms, forearms, and hands so the release pose has a clear
direction. Check the elbows, sleeve transitions, and shoulder deformation at
the beginning, release, and recovery poses. A fitted rig for one generated
character is not a general automatic rigging solution. For another model,
adjust the rig and animation before using the demo or adapt the copied demo
script explicitly.

Import the rigged GLB under the target project's `res://` directory. Wait for
Godot import, inspect the resulting skeleton/animation resources, then call:

```json
{"directory":"res://mage_spells","mage_path":"res://characters/mage_cast.glb","auto_cast":true}
```

`create_spellcasting_demo` rejects a supplied scene without the required bone
and clip before creating files. Omitting `mage_path` uses the bundled procedural
mage. Keep imported animation resources unchanged; duplicate animation data
before adding gameplay event tracks.

The current study retimes that copied clip to 1.85 seconds, with release at
0.90 seconds. The GLB contract above stays unchanged. Its example phases are
windup 0–0.28, gather 0.28–0.68, contract 0.68–0.90, release at 0.90, then
recovery to 1.85, all in clip seconds. Real time divides by AnimationPlayer
speed. `pulse(speed_scale)` keeps the aura's contraction aligned with release.
These are case presets awaiting visual approval, not universal timing rules.

| Current study setting | Single | Ember fast / heavy | Arcane first / second |
| --- | --- | --- | --- |
| Animation speed | 1.0 | 1.45 / 0.92 | 1.25 / 0.92 |
| Projectile speed | 13.5 | 13.0 / 11.0 | 12.0 / 10.5 |
| Visual scale | 1.0 | 0.70 / 1.35 | 0.85 / 1.20 |
| Impact strength | 1.0 | 0.65 / 1.50 | 0.80 / 1.30 |

These values are controller presets, not MCP arguments. Both two-shot sequences
queue their second shot automatically after the first animation finishes and a
0.12-process-second gap. Input buffering and combat cancellation are not
implemented. `auto_cast=false` isolates manual or scripted requests.

The hand ring contracts from `0.62 * visual_scale` to `0.10 * visual_scale`
between clip .68 and .90. Residue fades over .22 process seconds with per-instance
alpha. The aura contracts at the same clip event via `pulse(speed_scale)`; its
peak footprint is 1.35 times nominal radius. These visual radii are not damage
ranges. See the [aura lifecycle](combat-vfx.md) before using a persistent buff.

## Sync the release

Attach a `BoneAttachment3D` to the socket and use its global transform for the
charge and projectile origin. Drive release from the animation's method event,
not wall-clock delay. The demo controller's event creates a projectile and
connects its impact signal. The projectile owns its transient effects and their
cleanup; the character owns the persistent charge effect.

The existing `godot-assets`/scene tools handle import and instancing, and
`godot-animation` handles tracks. The VFX skill composes these capabilities
instead of introducing a second importer, retargeter, or animation transport.

Test both repeated casts and a single cast with auto mode disabled. Confirm
the rendered arm pose changes, the socket tracks the hand, only one release
occurs per animation, and the target records an impact. Inspect actual GPU
frames as well as the numerical counters.

## Polish a game-ready cast

Keep the same character and target while improving one layer at a time. Start
with a short native A/B capture before recording a long showcase. Preserve the
baseline script and model hashes; match the renderer, camera, resolution, frame
rate and release time for an effect comparison. Compare camera changes separately.

| Phase | Readable cue | Reusable owner |
| --- | --- | --- |
| Anticipation | Torso turn, asymmetric support hand, growing palm light | Character animation and charge |
| Release | Fast extension, brief hot flash, shoulder recoil | Animation method event |
| Travel | Compact bright core, colored envelope, continuous tapered trail | Projectile |
| Impact | Brief flash, expanding volume, floor ring and target reaction | Projectile signal and game presentation |
| Recovery | Fading embers, settled pose, clean floor | Effect lifetime and character animation |

Inspect the charge peak, release +0.1 s, and impact +0.05/+0.25/+0.8 s as
well as the complete short clip. Readability at gameplay distance matters more
than particle count. Keep background fires dimmer than the active spell, avoid
overexposed faces, and leave room for both the caster silhouette and impact.

Compose combos from the same release and impact contracts. Give each beat a
different timing and strength; repeated identical particles are not a combo.
Keep targeting, damage, cooldowns and buffs in the game. Validate the expected
number of releases, event order, repeatability, and return to the baseline
transient-node count. A finite combo must stop any temporary aura on completion.

Keep separate evidence for script-driven playback, ordinary input, exported
Web playback, real mobile hardware, and concurrent-effect performance. A movie
or a desktop Mobile renderer capture does not qualify those other paths.

For feedback studies, first hold the camera, assets, seeds and shared impact
components fixed while comparing phase orchestration. Then hold the new
orchestration fixed while comparing camera framing. Disable
`camera_feedback_enabled` in those controls; test the optional feedback
separately. Record each case's exact original film and source baseline. Mark
reconstructed controls as such, rather than calling them the original video.
Keep input acceptance, contact, and actual damage windows in separate fields;
the bundled demo has script acceptance and cosmetic contact but no damage system.

`camera_feedback_enabled` defaults to `true`; it controls the charge FOV
compression and the contact camera impulse. Disabling it does not suppress
target reactions or impact effects. Keep it off for controlled timing/framing
comparisons and assess its comfort separately at the gameplay camera.

The frozen v3 study uses FOV 49 degrees, aim `(0.2, 1.25, -0.1)`, and camera
position `(-1.87, 2.5725, 8.755)`: 15% farther from the aim than the preceding
close view, with the same direction and FOV. The impact envelope uses soft
spatial breakup. Its shape comparison holds the camera fixed; its camera
comparison holds the effect source fixed. Native clips verify that these paths
render, but do not establish human aesthetic acceptance, ordinary input or a
packaged game. Use the game's actual camera and actor proportions when adapting
the preset; neither the framing nor the .90 release key is universal.

## Sound follows the same events

The demo exports `charge_sound`, `release_sound`, and `impact_sound` as optional
`AudioStream` resources. Omitted streams use original deterministic PCM cues.
`begin_charge`, `release_spell`, and `_on_impact` play spatial cues from the
same animation/contact events as the visuals. A miss never calls `_on_impact`.
Set `sound_enabled=false` to suppress new cues; active cues finish naturally.
Release/charge pitch follows cast speed within 0.5–2.0; impact pitch follows
presentation strength. Replace the short PCM cues with licensed assets through
the Inspector or existing audio/resource tools. `sound_gain_db` is exposed on
the demo root and defaults to `2 dB`; each new cue clamps it to -40 through
12 dB. That is the player gain before distance attenuation and mixing, not an
output loudness guarantee. Inspect the recorded mix and listen at natural speed.
