---
name: godot-phantom-camera
description: >-
  Optional Godot 4 integration for the Phantom Camera addon. Detect, install,
  configure, and inspect PhantomCameraHost, PhantomCamera2D, and
  PhantomCamera3D nodes without changing the DCC-MCP core.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-godot 0.1+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot Phantom Camera virtual camera follow look-at tween priority"
    tags: "godot,camera,phantom-camera,game-development"
    tools: tools.yaml
---

# Godot Phantom Camera

Optional adapter for the third-party MIT-licensed Phantom Camera Godot addon.
It is not bundled into DCC-MCP. Use inspect first. Install and configure are
mutating operations and require authorization at call time.

The installer is pinned to an explicit upstream tag, rejects archive traversal,
requires addons/phantom_camera/plugin.cfg, preserves an existing installation
unless replacement is requested, refreshes the filesystem, and enables the
plugin only after verification. It does not submit code upstream.

Scene configuration creates a Camera3D, PhantomCameraHost, and
PhantomCamera3D chain only when missing, applies priority and allowlisted
properties, optionally saves, and always reads back the result. Phantom Camera
v0.12 requires Godot 4.4+ and has breaking dead-zone property changes.


## Godot 4.7 autoload compatibility gate

Phantom Camera v0.11.x had a documented Godot 4.7.1 autoload/singleton regression:
`PhantomCameraManager` could appear in Project Settings but fail to register at runtime.
Godot 4.7.2 is expected to include the engine-side fix, but this must be verified on the
actual host. Treat bridge readiness and PhantomCameraManager readiness as separate checks.
On Godot 4.7.x, inspect editor/runtime errors after enabling the plugin and before accepting configuration.
Do not silently patch upstream addon files. If the manager fails, report the upstream issue and
keep the installation unchanged; a version-gated, reversible workaround requires a separate
explicit change.
