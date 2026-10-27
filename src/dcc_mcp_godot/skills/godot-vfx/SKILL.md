---
name: godot-vfx
description: >-
  Domain skill — Install portable attack, spell, and aura scenes with a combat VFX gallery. Add a configurable slash, impact, or persistent magic aura to a 3D scene. Create billowing 3D fire particles, sparks, and a colored light. Create an inert fire projectile with travel, impact, and cleanup. Install a portable mage casting demo in a new project folder.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.2.0"
    search-hint: "Godot vfx install_combat_vfx_library create_combat_vfx create_dynamic_fire_vfx create_spell_projectile create_spellcasting_demo combat attack melee slash aura buff magic circle rune spell mage fire particles sparks projectile impact casting Hyper3D"
    tags: "godot,vfx,game-development"
    tools: tools.yaml
    skill-reference-docs:
      - "references/*.md"
---

# Godot Vfx

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.

For reusable game effects, start with [Combat VFX](references/combat-vfx.md). `install_combat_vfx_library` copies native scene presets and a gallery to a new project folder; the game can run them without the adapter. Presets include mesh fire, particle fire, slash, impact, aura and projectile; the gallery exposes both fire techniques alongside the combat effects. `create_combat_vfx` adds an adjustable slash, impact, or magic aura to the edited scene. The aura separates its ground contour, floating rune orbit, and inner seal; their reveals and stop fades remain tied to the effect lifecycle. [Gameplay integration](references/combat-integration.md) defines animation events, local/world anchors, aura start/stop, projectile exclusions, lifecycle checks, and performance budgets. Keep damage and buffs in the game.

Read [Spell VFX](references/spell-vfx.md) for the fire workflow: billowing particle fire, procedural or licensed input textures, skinned mage import, animation-keyed release, flight trails, impact, and cleanup. `create_spellcasting_demo` installs a portable example in a new directory without changing the main scene. Its default articulated mage needs no external assets. Optional `mage_path` requires a Skeleton3D with `RightCastSocket` and a `Cast` animation; a static Hyper3D GLB must be rigged first. Tune the demo's native cue level with `sound_gain_db`; verify the rendered mix and natural-speed listening separately. Reuse `godot-animation` for method tracks, `godot-particle` for emission tuning, and `godot-shader` for checked shader uniforms.
