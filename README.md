# dcc-mcp-godot

Godot 4 editor adapter for the DCC Model Context Protocol ecosystem. It ships a GDScript
`EditorPlugin`, typed project and scene tools, and a tested 2D arena-roguelike skill.

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

The MCP endpoint defaults to `http://127.0.0.1:8765/mcp`. The plugin connects to the
loopback bridge at `ws://127.0.0.1:3847`; override the port with
`DCC_MCP_GODOT_BRIDGE_PORT` before starting both processes.

## Agent workflow

1. Load `godot-project` to inspect the project or write a bounded `.gd` file below `res://`.
2. Load `godot-scene` to inspect the current scene and make undoable node edits.
3. Load `godot-roguelike`, call `create_2d_roguelike`, then `validate_2d_roguelike`.
4. Run the project. Arrow keys move the player; enemies spawn continuously and the player
   auto-attacks, earns experience, levels up, and eventually reaches game over.

No raw editor evaluation or arbitrary filesystem command is exposed. Scene edits use Godot's
undo manager; script writes are restricted to `.gd` files below `res://`.

## Real Godot CI

CI resolves the official `godotengine/godot` latest stable GitHub release and downloads the Linux
editor. It starts the packaged MCP server and EditorPlugin, sends real JSON-RPC `load_skill`,
paginated `tools/list`, `tools/call`, and `jobs_get_status` requests, then runs the generated game
simulation and requires `ROGUELIKE_SMOKE_OK`.

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
