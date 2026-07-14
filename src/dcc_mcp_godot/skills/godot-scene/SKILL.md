---
name: godot-scene
description: >-
  Domain skill — Inspect and edit the current Godot 4 scene with undoable,
  typed node operations. Use for scene trees, nodes, and properties. Not for
  GDScript authoring — use godot-project. Not for complete game generation —
  use godot-roguelike.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot scene tree create node set property save scene"
    tags: "godot,scene,nodes,game-development"
    tools: tools.yaml
    depends: "dcc-diagnostics"
---

# Godot Scene

Scene mutations use Godot's `EditorUndoRedoManager`. Inspect the scene before choosing node paths.
