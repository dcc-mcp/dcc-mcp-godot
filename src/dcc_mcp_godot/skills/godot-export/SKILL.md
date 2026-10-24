---
name: godot-export
description: >-
  Domain skill — Inspect export presets and templates, package Godot projects
  for desktop EXE/standalone, Web, and mobile targets, and validate packaged-only resource,
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
    search-hint: "Godot export package release runnable standalone EXE Windows macOS Linux Web Android iOS fonts CJK resources presets templates"
    tags: "godot,export,game-development"
    tools: tools.yaml
    skill-reference-docs:
      - "references/*.md"
---

# Godot Export

For a packaging, runnable game, standalone, EXE, or playtest delivery request,
report readiness in the first response, before authoring or opening a GUI.
Read [Cross-platform packaging](references/platform-packaging.md) and identify
the exact engine version/build, edition, architecture, target OS, named preset,
matching template identity/cache, disk needs and download size. State missing
inputs immediately. An EXE request is not download permission; preserve existing
projects, saves and caches while resolving dependencies through normal consent.

Use these editor-integrated tools after opening the target Godot project. Start
with `get_export_info` and `list_export_presets`; do not mutate a preset or
attempt a release export until the requested target and matching template are
known. Paths passed to the tools must remain under `res://`.

Prefer `start_export_job` with a stable 32-hex request ID and a fresh dedicated
output directory, then `get_export_job`. A lost start response is queried with
that same ID, never blindly repeated under a new ID. `cancel_export_job` reports
actual child cleanup, not assumed termination. Unknown outcomes keep the project
busy. Complete logs and output hashes are file receipts, not truncated bridge
text. Windows cleanup is direct-child-only; do not claim all descendants stopped.
One lazy export manager exclusively owns a registry journal across processes;
other adapters sharing it receive busy without changing records or spawning.
Use the existing explicit private-registry option for isolated adapters; concurrent
multi-Godot exports sharing one registry are not supported in this version.
The legacy `export_project` remains synchronous and can exceed bridge deadlines.

Read [Cross-platform packaging](references/platform-packaging.md) before
planning a release build, changing platform presets, or diagnosing a failure
that appears only after export. In particular, editor success is not release
evidence: launch the exported artifact on the target runtime and verify fonts,
resources, storage, input, and startup diagnostics.
