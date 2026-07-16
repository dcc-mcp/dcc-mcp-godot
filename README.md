# dcc-mcp-godot

Godot 4 editor adapter for the DCC Model Context Protocol ecosystem. It ships a GDScript
`EditorPlugin`, an `EngineDebugger` runtime peer, 163 on-demand tools, and a tested 2D
arena-roguelike skill.

## Install

```bash
pip install dcc-mcp-godot
```

Install the packaged addon into a Godot project:

```bash
dcc-mcp-godot-install /path/to/project
```

Enable **DCC-MCP Godot** under **Project Settings > Plugins**, then run:

```bash
dcc-mcp-godot
```

Each adapter instance uses an OS-assigned MCP port and registers it for CLI discovery.
Connect through the stable gateway at `http://127.0.0.1:9765/mcp`; set
`DCC_MCP_GODOT_PORT` only when a fixed direct endpoint is required. The plugin connects
to the loopback bridge at `ws://127.0.0.1:3847`; override the bridge port with
`DCC_MCP_GODOT_BRIDGE_PORT` before starting both processes.

## Agent workflow

1. Search skills for the required domain, such as `Godot animation`, `Godot runtime`, or
   `Godot TileMap`.
2. Load only the returned domain skill. Tools remain deferred until their skill is loaded.
3. Inspect the project or scene before mutating it, then save and validate the result.
4. Load `godot-runtime`, `godot-input`, or `godot-testing-qa` after starting the game when
   live inspection, input simulation, or QA assertions are required.

The original `godot-project`, `godot-scene`, and `godot-roguelike` skills remain available.

## Capability skills

The adapter groups 163 fine-grained tools into 23 independently loadable domains:

| Domains | Tools |
| --- | ---: |
| Project, scene management, node, script, editor | 47 |
| Input and runtime | 26 |
| Animation and AnimationTree | 14 |
| 3D scene, physics, particles, navigation, audio | 29 |
| TileMap, Theme/UI, shader, resource | 24 |
| Batch/refactor, analysis, testing/QA, profiling, export | 23 |

Runtime tools use the official `EditorDebuggerPlugin` and `EngineDebugger` channel, so input
events and game-node operations run in the game process rather than the editor process. Enabling
the plugin registers the bundled runtime peer as an autoload; disabling it removes the autoload.

Scene edits use Godot's undo manager and file operations are restricted to `res://` with size and
extension checks. `execute_editor_script` only calls a method on an existing `@tool` project
script; `execute_game_script` only calls a public method on an existing runtime node. Neither tool
accepts raw source for immediate evaluation.

## Real Godot CI

CI resolves the official `godotengine/godot` latest stable GitHub release and downloads the Linux
editor. It starts the packaged MCP server and EditorPlugin, sends real JSON-RPC `load_skill`,
paginated `tools/list`, `tools/call`, and `jobs_get_status` requests, creates and edits a scene,
starts the game, verifies the runtime scene tree, then runs the generated gameplay simulation and
requires `ROGUELIKE_SMOKE_OK`.

Run the same smoke locally:

```bash
python tools/download_latest_godot.py --output .godot-bin
python tests/live_godot_smoke.py --godot /path/to/Godot
```

## Development

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src tests tools
ruff format --check src tests tools
python tools/lint_skills.py
python -m build
python -m twine check dist/*
```
