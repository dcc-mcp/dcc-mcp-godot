# Godot 2D roguelike qualification

The `godot-roguelike` workflow keeps one generated asset-free project and exposes
an observable gameplay contract.

## Gameplay contract

- Arrow input changes the player position through Godot's input map.
- Automatic firing produces projectiles and combat kills.
- Space toggles automatic firing while the player is alive.
- Enemy contact reaches a game-over state with `health == 0`.
- Space restarts a failed run through `ui_accept`.
- The state receipt includes position, health, kills, level, game-over state,
  automatic-fire state, and restart count.

`ci_smoke.gd` sends native Godot input events and checks each state transition.
The editor-side validator also requires the scene, gameplay script, smoke script,
and the enemy-failure helper that the qualification contract uses.

## Qualification lanes

`tests/probe_roguelike_qualification.py` creates a clean project from the same
template files used by `create_2d_roguelike`.

1. The editor imports the project, exits, and reopens it. The probe verifies the
   main scene reference after reopening and stores both editor logs.
2. The native lane runs the gameplay smoke outside the editor.
3. The desktop lane exports with the pinned official template, starts the
   exported artifact outside the editor, and records its hash and runtime log.
4. The Web lane serves the export through localhost. A real browser verifies
   movement, automatic-fire toggle, focus recovery, natural failure, restart,
   page errors, console errors, and a screenshot.

The fixture declares no audio asset, so the report records
`not_applicable_no_audio_track_declared`. Projects that add audio need a
separate audio-unlock check.

Each report records the engine version and hash, template hashes, generated
project hashes, export artifact hashes, browser version, input steps, logs, and
Web output hashes. The pull-request workflow pins Godot 4.6.3 and its Linux and
Web export templates. Local runs can use an installed matching engine/template
pair. A report with `passed: true` covers the exact pair recorded in that
report.
