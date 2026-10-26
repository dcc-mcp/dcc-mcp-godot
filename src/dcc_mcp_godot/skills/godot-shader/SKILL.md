---
name: godot-shader
description: >-
  Domain skill — Create an animated, textured 3D fire with editable shader uniforms. Create a bounded .gdshader resource. Read a project shader file. Replace or search/replace shader source. Assign a ShaderMaterial to a CanvasItem or GeometryInstance3D. Set one ShaderMaterial parameter. Return shader parameters on a node material.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.2.0"
    search-hint: "Godot shader create_fire_vfx create_shader read_shader edit_shader assign_shader_material set_shader_param get_shader_params VFX stylized fire dissolve noise texture gradient"
    tags: "godot,shader,game-development"
    tools: tools.yaml
    skill-reference-docs:
      - "references/*.md"
---

# Godot Shader

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.

Use `create_fire_vfx` below a Node3D for a complete original 3D fire: subdivided cylinder, two scrolling noise textures, gradient, vertex motion, and dissolve. Tune it with `set_shader_param`; uniform names and types are validated by the host. Read [Shader VFX](references/shader-vfx.md) for the recipe, typed values, renderer limits, and validation workflow.
