# Typed playtest actions

`execute_typed_action` is the only runtime mutation path intended as a foundation for future
playtest or RL episode APIs. It does not create an episode API itself.

## Trust boundary

The project owner places a Draft 2020-12 manifest at the fixed path
`res://.dcc-mcp/playtest-actions.v1.json`. The committed schema is
[`playtest_actions_manifest_v1.schema.json`](../src/dcc_mcp_godot/schemas/playtest_actions_manifest_v1.schema.json).
The runtime rejects an absent, oversized, invalid, replaced, linked, junction-backed, or otherwise
drifted manifest. The caller cannot select another manifest path.

Configure the exact project identity in `project.godot`:

```ini
[dcc_mcp]

playtest/project_id="studio-game"
playtest/session_id="manual-smoke-001"
playtest/authority_id="playtest-owner"
```

An operator may set `DCC_MCP_GODOT_PLAYTEST_SESSION_ID` and
`DCC_MCP_GODOT_PLAYTEST_AUTHORITY_ID` before launching Godot to narrow the two runtime values.
These values are coordination identities, not credentials.

Call `get_runtime_status` after the game starts. Its `typed_actions` object returns the current
redacted `runtime_id`, locked `manifest_digest`, manifest identity, remaining budget, and declared
action selectors. Repeat all of those exact identities in `execute_typed_action`. A runtime restart,
manifest replacement, project/session change, or different authority invalidates the old call.

## Supported v1 actions

- `input_action` presses or releases one exact existing InputMap action. The manifest bounds
  `pressed` and `strength`.
- `set_property` writes one JSON scalar to one exact absolute node path and property. The manifest
  binds the node class, project script path, script SHA-256, value type/range or string enum, and
  measured property readback. The runtime hashes and resolves the exact script immediately before
  and after mutation, verifies the requested scalar exactly, and rolls the property back if the
  setter is ignored or the target drifts.

Both action objects and all nested selector/argument objects reject extra properties. Selectors
containing script execution, console/eval, file/network, account/payment, or multiplayer surfaces
are denied. A structurally valid `script_path` is provenance rather than an executable selector,
so a directory such as `res://scripts/` does not trigger this keyword filter. Its exact path,
project containment (including link rejection), SHA-256, and binding to the target node's actual
script remain enforced; action IDs, node paths/classes, property names, and input action names
still receive the selector filter. No method-call action is supported.

V1 actions must execute on Godot's main thread. A `physics` declaration is represented
explicitly but fails closed until a physics-owned dispatcher exists; it is never silently run on
the main thread.

The adapter reserves a validated host action before crossing the mutation boundary. It rechecks
cancellation before commit and after the claimed mutation; cancellation after commit requests an
immediate rollback, while an orphaned claim is rolled back by the runtime timeout. Only a
successfully verified and finalized action consumes the manifest's total authority budget and
rolling rate budget. Rejected, missing-target, drifted, ignored-setter, cancelled, and orphaned
calls consume neither counter.

The editor stages, but does not forward, a commit until it receives authorization for the exact
request ID, guard ID, request digest, and pinned WebSocket connection. Timeout and authorization
race atomically in the adapter: when timeout wins, its terminal fence rejects any delayed host
intent before runtime mutation; when authorization wins, the adapter waits for the definitive
host result or connection loss instead of returning a false terminal timeout. This protocol does
not depend on sleeps, retries, or reservation expiry for safety.

Successful tool results use Core's `success`/`message`/`context` envelope. The closed `context`
receipt contains the locked manifest identity, action identity/kind, exact target, measured
readback, and remaining budget. They do not expose a process ID, local project path, arbitrary
method result, file content, or network/account data.

## Result envelope migration (0.9.2)

**Breaking change.** Before 0.9.2, a successful `execute_typed_action` returned the receipt as a
flat top-level object. Since 0.9.2 the same receipt is returned inside Core's standard result
envelope: the nine receipt fields moved down one level into `context`, and the envelope adds
`success`, `message`, and optionally `error`/`prompt`. Every receipt field, pattern, and constraint
is unchanged; only its location moved.

Consumers that read the receipt at the top level must add the `context` hop:

| Before 0.9.2 | Since 0.9.2 |
|---|---|
| `payload.status` | `payload.context.status` |
| `payload.schema_version` | `payload.context.schema_version` |
| `payload.manifest_id` | `payload.context.manifest_id` |
| `payload.manifest_digest` | `payload.context.manifest_digest` |
| `payload.action_id` | `payload.context.action_id` |
| `payload.kind` | `payload.context.kind` |
| `payload.target` | `payload.context.target` |
| `payload.readback` | `payload.context.readback` |
| `payload.budget` | `payload.context.budget` |

Two habits survive the move unchanged:

- Gate on `payload.success` (const `true` for an applied action) instead of comparing
  `payload.status` to `"applied"`; `context.status` still only ever carries `applied`.
- Keep reading failures from the error side of the envelope (`success: false` plus a string
  `error`). Rejected, missing-target, drifted, ignored-setter, cancelled, and orphaned calls were
  never a `status` value and still are not.

Before 0.9.2 (`set_property` receipt, abridged):

```json
{
  "status": "applied",
  "schema_version": 1,
  "manifest_id": "studio-game-playtest",
  "action_id": "nudge-health",
  "kind": "set_property",
  "readback": { "kind": "property", "property": "health", "value": 7 },
  "budget": { "used": 1, "remaining": 9, "limit": 10 }
}
```

Since 0.9.2, the same call (abridged the same way):

```json
{
  "success": true,
  "message": "Godot action execute_typed_action completed.",
  "context": {
    "status": "applied",
    "schema_version": 1,
    "manifest_id": "studio-game-playtest",
    "action_id": "nudge-health",
    "kind": "set_property",
    "readback": { "kind": "property", "property": "health", "value": 7 },
    "budget": { "used": 1, "remaining": 9, "limit": 10 }
  }
}
```

A version-tolerant read works across both shapes:

```python
receipt = payload.get("context", payload)
remaining = receipt["budget"]["remaining"]
```

`execute_game_script` remains available only for compatibility. It invokes a named public method
and therefore is not an allowlist, is not the typed action path, and must not be used as playtest or
RL authority.
