---
name: godot-testing-qa
description: >-
  Domain skill — Run a sequence of runtime actions and assertions. Assert runtime node existence and properties. Assert visible runtime text. Compare two PNGs using bounded pixel sampling. Sample runtime performance for a bounded frame count. Return the latest runtime test report. Gate collision acceptance on saved-scene physics and exploratory playtests.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.2.0"
    search-hint: "Godot testing-qa run_test_scenario assert_node_state assert_screen_text compare_screenshots run_stress_test get_test_report collision intent solid trigger query-only none reachability regression"
    tags: "godot,testing-qa,game-development"
    tools: tools.yaml
---

# Godot Testing Qa

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.

## Collision regression gate

Require a reasoned `solid` / `trigger` / `query-only` / `none` inventory,
actual body/shape and layer/mask readback, visual alignment, save/reopen,
off-script exploration, and pickup height/line-of-sight checks. A screenshot,
node count, successful tool call, or one prescribed route cannot pass this gate.
Report passed, failed, and not measured checks separately; distinguish native
physics queries or direct script calls from real-input and rendered playtests.

Load `godot-physics` (`dcc-mcp-cli load-skill godot-physics --dcc-type godot`)
and read its `references/collision-intent.md` before accepting the scene.
Use `skill_refs__list` with `skill: godot-physics`, then `skill_refs__read`
with that skill and the returned path. The reference belongs to that skill;
do not resolve it relative to this skill or assume sibling filesystem access.
If it is unavailable, report the missing guidance and leave collision acceptance
unverified rather than silently skipping the gate.
