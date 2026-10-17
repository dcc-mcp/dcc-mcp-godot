# Collision intent and scene acceptance

Use this contract whenever an agent creates, imports, duplicates, or changes
gameplay objects, and before it calls a scene playable. It is a Godot authoring
and QA policy, not a new tool argument or an automatic scene validator.

## 1. Declare intent before implementation

Record an object path (or a reproducible group of equivalent instances), role,
reachable states, one of the four intents below, and an explicit reason. Include
the expected blocking/detection behavior, implementation paths or query owner,
layers/masks, and the tests that will prove it. Recheck the decision when an
object's placement, scale, animation, player abilities, or gameplay role changes.

- `solid`: must support or block a relevant actor. Use a suitable physics body
  and enabled shape(s). Examples: ground, floors, walls, reachable boulders,
  tree trunks, and the solid base/lid of a chest. Use a stationary body for
  stationary scenery; choose the appropriate moving body for moving objects.
- `trigger`: overlap should cause an event without blocking movement. Use an
  Area with enabled shape(s), the intended monitoring configuration, filters,
  and event handling. Examples: a pickup region, water/swimming volume, hazard
  region, checkpoint, or a chest's interaction area.
- `query-only`: detect or interact by an explicit ray, shape, or bounded spatial
  predicate without adding an unwanted movement blocker. Record the query
  owner, target representation, masks/exclusions, range, height, and obstruction
  policy. Examples: ray-selected pickups or a water surface-height query. A
  physics ray still needs a queryable target shape; a purely mathematical
  region must define and test its own bounds. A query-only target must not
  accidentally block the player's movement via its layers/masks.
- `none`: no physical blocking or detection is needed. Record why. Examples:
  soft foliage and palm fronds that should brush past the player; cosmetic
  particles; distant backdrops outside an enforced playable boundary; and UI.
  "Decorative" alone is insufficient for a reachable wall, boulder, or trunk.
  If a particle, plant, or backdrop has a gameplay role, classify that role
  separately instead of using its visual category as an exemption.

Choose from semantics and reachability, not mesh visibility or polygon count.
Reachability includes off-route walking, jumping, falling, swimming, alternate
approaches, and supported camera/projectile queries. An inaccessible object
can use `none` only while that exclusion remains true. A chest may have a
`solid` base plus a `trigger` interaction region; a palm may have a `solid`
trunk plus `none` fronds. One collider may represent multiple visual meshes;
one visible object may need several simple shapes. Neither mesh count nor
collider count is an acceptance threshold.

Example inventory (paths and dimensions come from the actual project):

| Object/component | Intent | Reason | Implementation and evidence to record |
| --- | --- | --- | --- |
| Walkable ground | solid | Player must stand on it | Body/shape paths, floor contact, edge traversal |
| Reachable rock | solid | Player cannot pass through its visible mass | Fitted hull(s), approaches from multiple sides |
| Palm trunk / fronds | solid / none | Trunk blocks; fronds are soft dressing | Trunk capsule fit; no frond snagging |
| Chest base / interaction region | solid / trigger | Base blocks; use remains reachable | Body plus Area; prompt/action reach agreement |
| Pickup | trigger or query-only | Detect collection without blocking travel | Range, height, obstruction, one-shot state |
| Water | trigger or query-only | Enter/exit swimming; surface is not a floor | Volume or surface bounds; shore/depth transitions |
| Distant backdrop | none | Enforced boundary prevents reaching it | Boundary and alternate-route checks |
| UI / cosmetic particles | none | No world-physics role | Explicit exclusion, visual/input checks as applicable |

## 2. Build and inspect actual physics

1. Inspect imported scenes and instances before adding collision. A rendered
   mesh, navigation mesh, material, or successful import does not establish a
   physics body. Preserve suitable imported collision; avoid duplicate shapes.
2. For solids, create a `StaticBody3D`, `CharacterBody3D`, `RigidBody3D`, or other
   suitable body. For triggers, create an `Area3D`. Use the corresponding 2D
   types for 2D scenes. Add a non-disabled `CollisionShape3D` with a non-null,
   appropriately sized `Shape3D` directly under its collision-object parent.
   `setup_physics_body` only configures an existing node, and `setup_collision`
   only adds a shape under `parent_path`. Neither creates a missing body nor
   turns a `MeshInstance3D` parent into one. Use `godot-node` for body creation.
3. Read back node types, shape resources, disabled flags, sizes, global
   transforms, and ownership. Use `get_collision_info` on the actual body or
   Area, not only the mesh. It reports immediate shape children, disabled
   flags, and shape properties; inspect transforms and ownership separately
   with scene/node readback. Inspect each relevant instance, including runtime
   spawns and duplicates. A prototype check does not cover differently scaled
   instances. Prefer simple fitted primitives or convex pieces; do not wrap
   palm fronds, empty archways, or an entire hollow prop in a blocking box.
4. Define named collision layers and masks for the project's actors, solids,
   triggers, interaction queries, camera, and projectiles as applicable. Read
   them back with `get_physics_layers`; test intended and excluded pairs.
   Nonzero values alone do not prove compatibility. Query filters can differ
   from movement filters. Enable area detection in a ray query when needed.
5. Fit collision to the visible blocking surfaces at the final transform.
   Prefer changing shape resource dimensions over non-uniform shape scaling.
   Check feet on floors, sloped ground, rock edges, chest clearance, and door
   openings. For stairs, align a walkable ramp or implement tested step-up
   behavior; blindly adding vertical risers can prevent traversal. A hidden
   ramp must not leave visible steps floating above or swallowing the player.

Godot references: [CollisionShape3D](https://docs.godotengine.org/en/stable/classes/class_collisionshape3d.html),
[physics and collision filters](https://docs.godotengine.org/en/stable/tutorials/physics/physics_introduction.html),
and [ray query parameters](https://docs.godotengine.org/en/stable/classes/class_physicsrayqueryparameters3d.html).

## 3. Share interaction reachability

Use the same reachability predicate for the prompt and the action. Check
appropriate 3D distance or separately bounded horizontal and vertical reach;
XZ-only distance lets a player collect an item from far above or below it.
For ordinary physical pickups and chest interactions, require line of sight
from a suitable player/hand/eye point to an actual interaction point. Exclude
the player's own collider; accept a hit on the intended target's own collider
when it is the first relevant hit, or deliberately exclude that target while
checking intervening obstacles. Do not ignore all solids to make the query pass.
Choose interaction points that remain reachable outside a solid chest or prop.

Document deliberate exceptions, such as a remote-use mechanic, rather than
silently weakening the predicate. Recheck at action time after movement or
state changes. Test one-shot collection, repeated input, already collected
items, and save/reload. Water interaction must also respect swimming height
and the intended surface/volume bounds.

## 4. Collision regression gate

Keep a result for every applicable check: **passed**, **failed**, or
**not measured** with the reason and next step. An intentional exclusion needs
an object-specific `none` reason and evidence for its reachability assumption.
Do not mark the scene collision-complete with unresolved failures or required
checks that were not measured.

- **Inventory and structure:** every gameplay object/component has an intent
  and reason; every required solid/trigger has a real body/Area and enabled,
  non-null shape. Verify layers, masks, monitoring, transforms, and query
  configuration. Inspect spawned objects as well as saved scene nodes.
- **Native physics:** use real Godot physics queries and the actual player
  controller to test ground support and collision from both sides of walls,
  rocks, trunks, and solid props. Include intentionally passable trigger and
  `none` objects, plus query-only targets that must not block movement. A ray
  hit does not prove the player capsule can traverse or stop correctly.
- **Visual alignment:** inspect rendered movement with collision debug shapes
  where useful. Look for penetration, floating feet, invisible blockers, poor
  doorway clearance, camera clipping, and snagging. Set tolerances from the
  project's scale and controller; do not invent a universal acceptable gap.
- **Save/reopen:** save the scene/resources, stop play, close/reopen or reload
  the saved project, and repeat structure and runtime checks. Verify ownership
  and imported/runtime-generated collision survive the actual reload path.
- **Off-script exploration:** leave the prescribed route. Approach solid props
  from the back and sides; test edges, corners, stairs up/down, jumping/falling,
  swimming/shore transitions, and camera obstruction when those mechanics exist.
- **Pickup height and line of sight:** test near/far, above/below, blocked/
  unblocked, the target's own collider, swimming pickups, repeated action, and
  prompt/action agreement. Include a same-XZ but clearly out-of-height case
  and a nearby item behind a wall, both rejected unless explicitly designed
  otherwise. Re-run after collision changes and from fresh/saved state.

Record the project revision, Godot version/backend, scene, actor/controller,
object paths, initial state, inputs or query parameters, expected/observed
results, and evidence location. Separate editor inspection, headless physics,
direct function calls, native real-input playtests, and rendered visual review.
A direct `interact()` call is not real-input proof; a screenshot is not physics
proof; one successful scripted route is not exploratory coverage.

Repository tests for these skills guard generated text, reference resolution,
and packaged files only. They do not run this project-specific gameplay gate
or certify arbitrary scenes. Report that distinction when delivering a scene.
