# Install DCC-MCP for Godot

## Requirements

- Windows 10/11, macOS 12+, or a current Linux distribution.
- Godot 4.0 or newer. The adapter does not download or cache Godot; install it
  from the official Godot distribution or your operating-system package manager.
- Python 3.9 or newer and `dcc-mcp-core` 0.19.45 or newer.
- A Godot project containing `project.godot`.

The Python interpreter runs the adapter outside Godot. The bundled GDScript
EditorPlugin is installed into one project and all Godot API calls remain on the
editor main thread.

## Supported host locations

Automatic discovery checks `godot4` and `godot` on `PATH`. Use `--dcc-path`
for any other installation. Common paths include:

- Windows: `C:\Program Files\Godot\Godot_v4.x-stable_win64.exe`
- macOS: `/Applications/Godot.app/Contents/MacOS/Godot`
- Linux: `/usr/bin/godot4`, `/usr/local/bin/godot`, or an operator-managed AppImage

## Agent quick path

Install the released wheel into the Python environment that will run the
adapter:

```bash
python -m pip install dcc-mcp-godot
```

Plan first. Replace the example paths with the target project, Godot executable,
and Python interpreter:

```bash
dcc-mcp-godot install /path/to/project --dcc-path /path/to/godot --python /path/to/python --dry-run --json
dcc-mcp-godot install /path/to/project --dcc-path /path/to/godot --python /path/to/python --yes --json
```

The installer validates the host, Python, Core, and project before mutation. It
stages a complete addon replacement, updates the `[editor_plugins]` entry, and
writes `.dcc-mcp/receipts/godot.json`. Exit 50 is expected until the adapter and
Godot editor are running. Follow the JSON `next_steps` exactly, then verify:

```bash
dcc-mcp-godot serve
dcc-mcp-godot verify /path/to/project --json
```

`verify` imports the adapter in the recorded interpreter, waits for Godot/Core
readiness, loads the typed project skill, calls `get_project_info`, and confirms
that the responding editor owns the requested project. A copied addon alone is
never reported as directly usable.

When several Godot editors are registered, `verify` probes them independently
and accepts only the matching project. An operator may narrow the same check
with `--instance-id <uuid>`; project-path readback is still mandatory.

## Manual path

The supported agent path above is preferred. If policy requires manual file
placement, copy the packaged `godot_addon/addons/dcc_mcp_godot` directory to
`<project>/addons/dcc_mcp_godot`, enable
`res://addons/dcc_mcp_godot/plugin.cfg` in the project's `[editor_plugins]`
section, start `dcc-mcp-godot serve`, and run `verify`. Manual installs have no
receipt and therefore cannot use the receipt-owned uninstall command; repair
with the standard installer first.

## Status and repair

```bash
dcc-mcp-godot status /path/to/project --json
dcc-mcp-godot install /path/to/project --dcc-path /path/to/godot --python /path/to/python --yes --json
```

`status` distinguishes absent, partial, and receipt-complete installs without
claiming live readiness. Re-running `install` repairs a partial install and is
idempotent. Locked files fail closed; exit 50 means close or restart Godot and
repeat the same command.

The plugin writes bounded startup state to
`<project>/.godot/dcc_mcp_godot_bootstrap.json`. `starting` without `ready`, a
missing file, or an editor error indicates a bootstrap failure. This file is a
diagnostic only; live typed readiness remains authoritative.

## Upgrade

Upgrade the wheel, then transactionally replace the project addon:

```bash
python -m pip install --upgrade dcc-mcp-godot
dcc-mcp-godot upgrade /path/to/project --dcc-path /path/to/godot --python /path/to/python --dry-run --json
dcc-mcp-godot upgrade /path/to/project --dcc-path /path/to/godot --python /path/to/python --yes --json
```

The staged replacement removes files no longer shipped by the new version and
rolls back to the previous tree if the transaction fails.

## Uninstall

```bash
dcc-mcp-godot uninstall /path/to/project --dry-run --yes --json
dcc-mcp-godot uninstall /path/to/project --yes --json
python -m pip uninstall dcc-mcp-godot
```

Uninstall requires the project receipt, removes only the adapter-owned addon
tree and plugin entry, and preserves other addons and project settings. It
fails closed instead of guessing when the receipt is missing or invalid.

## JSON and exit codes

Every lifecycle verb accepts `--json`; mutating verbs also accept `--yes` and
`--dry-run`. `--dcc-path` and `--python` override discovery. Results follow
Install SOP schema version 1 and use these stable exits:

| Exit | Meaning |
| ---: | --- |
| 0 | The requested plan, status, uninstall, or live verification succeeded. |
| 10 | Preflight or explicit confirmation failed. |
| 20 | Payload acquisition failed. The Godot adapter currently acquires no external payload. |
| 30 | Install, repair, receipt, or uninstall failed. |
| 40 | Target import, live readiness, typed ping, or project binding failed. |
| 50 | Files are locked or the newly installed plugin requires a host restart/load. |

## Troubleshooting

- **Godot was not found:** pass the real editor binary with `--dcc-path`; the
  adapter never scrapes or downloads a latest host build.
- **Exit 10 for Core or Python:** run the command from the intended Python
  environment and upgrade `dcc-mcp-core` before retrying.
- **Status is partial:** keep the project closed and rerun `install --yes`; the
  staged transaction converges the addon, plugin entry, and receipt.
- **Exit 40 at readiness:** start `dcc-mcp-godot serve` and the target Godot
  project with the same `DCC_MCP_GODOT_BRIDGE_PORT`, then rerun `verify`.
- **Target binding failed:** more than one Godot editor may be registered. Stop
  unrelated instances and verify the requested project again.
- **Bootstrap did not become ready:** inspect
  `.godot/dcc_mcp_godot_bootstrap.json` and the Godot editor Output panel. Fix
  the reported script/import problem, reload the plugin, and rerun `verify`.
- **Exit 50 for locked files:** close Godot, repeat the exact lifecycle command,
  then restart the editor. The previous addon remains recoverable until the
  staged replacement commits.
