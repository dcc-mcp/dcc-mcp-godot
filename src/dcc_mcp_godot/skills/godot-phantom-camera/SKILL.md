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
