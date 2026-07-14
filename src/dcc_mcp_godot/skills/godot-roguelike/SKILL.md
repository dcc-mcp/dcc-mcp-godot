---
name: godot-roguelike
description: >-
  Domain skill — Create and validate a playable Godot 4 2D arena roguelike
  prototype with movement, spawning, combat, experience, and leveling. Use for
  an end-to-end tested game foundation. Not for isolated scene edits — use
  godot-scene. Not for standalone GDScript files — use godot-project.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "create 2D roguelike survivor arena game Godot prototype validate gameplay"
    tags: "godot,2d,roguelike,game-development,prototype"
    tools: tools.yaml
    depends: "dcc-diagnostics"
---

# Godot 2D Roguelike

Start with `create_2d_roguelike`, then call `validate_2d_roguelike`. The generated project uses
primitive drawing and requires no external assets, so an agent can immediately iterate with
`godot-project.write_script` and `godot-scene` tools.
