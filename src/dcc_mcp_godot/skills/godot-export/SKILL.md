---
name: godot-export
description: >-
  Domain skill — Inspect export presets and templates, package Godot projects
  for desktop, Web, and mobile targets, and validate packaged-only resource,
  font, signing, and hosting failures. Use for export planning and release
  preflight, not for editing gameplay or scene content.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.2.0"
    search-hint: "Godot export package release Windows macOS Linux Web Android iOS fonts CJK resources presets templates"
    tags: "godot,export,game-development"
    tools: tools.yaml
    skill-reference-docs:
      - "references/*.md"
---

# Godot Export

Use these editor-integrated tools after opening the target Godot project. Start
with `get_export_info` and `list_export_presets`; do not mutate a preset or
attempt a release export until the requested target and matching template are
known. Paths passed to the tools must remain under `res://`.

Read [Cross-platform packaging](references/platform-packaging.md) before
planning a release build, changing platform presets, or diagnosing a failure
that appears only after export. In particular, editor success is not release
evidence: launch the exported artifact on the target runtime and verify fonts,
resources, storage, input, and startup diagnostics.
