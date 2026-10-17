---
name: godot-scene-3d
description: >-
  Domain skill — Add a primitive MeshInstance3D. Add or configure a Camera3D. Add or configure a 3D light. Add or configure a WorldEnvironment. Add and configure a GridMap. Create or update a StandardMaterial3D override. Choose explicit collision intent when creating or importing 3D objects.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.2.0"
    search-hint: "Godot scene-3d add_mesh_instance setup_camera_3d setup_lighting setup_environment add_gridmap set_material_3d collision intent solid trigger query-only none reachability regression"
    tags: "godot,scene-3d,game-development"
    tools: tools.yaml
---

# Godot Scene 3D

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.

## Decide collision intent before creating objects

For every created or imported gameplay object, record `solid`, `trigger`,
`query-only`, or `none` and a reason based on gameplay semantics and reachability.
Do not add collision to every visible mesh, or assume a mesh already has it.
Reachable ground, walls, boulders, tree trunks, and solid chest parts normally
need blocking bodies; pickups and water need triggers or explicit queries;
soft foliage, particles, inaccessible backdrops, and UI normally need none.
Classify components separately when an object has both solid and interactive parts.

Load `godot-physics` (`dcc-mcp-cli load-skill godot-physics --dcc-type godot`)
and read its `references/collision-intent.md` before accepting the scene.
Use `skill_refs__list` with `skill: godot-physics`, then `skill_refs__read`
with that skill and the returned path. The reference belongs to that skill;
do not resolve it relative to this skill or assume sibling filesystem access.
If it is unavailable, report the missing guidance and leave collision acceptance
unverified rather than silently skipping the gate.
