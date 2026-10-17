---
name: godot-physics
description: >-
  Domain skill — Configure physics-body properties. Add and configure a collision shape. Set collision layer and mask. Read collision layer and mask. Return collision child and shape details. Add a RayCast2D or RayCast3D. Implement solid, trigger, query-only, or none collision intent and verify it.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.2.0"
    search-hint: "Godot physics setup_physics_body setup_collision set_physics_layers get_physics_layers get_collision_info add_raycast collision intent solid trigger query-only none reachability regression"
    tags: "godot,physics,game-development"
    tools: tools.yaml
    skill-reference-docs:
      - "references/*.md"
---

# Godot Physics

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.

## Collision intent and acceptance

Read [Collision intent](references/collision-intent.md) before creating,
changing, or validating physics. Record `solid`, `trigger`, `query-only`, or
`none` with an explicit reason for each gameplay object or component.
`setup_physics_body` configures an existing node; it does not create a body.
`setup_collision` creates a shape under `parent_path`; it does not make a mesh
solid. Create the appropriate physics body or Area first using `godot-node`,
then inspect body type, enabled shape resource, transforms, layers, and masks.
The reference defines the save/reopen and real gameplay regression gate.
