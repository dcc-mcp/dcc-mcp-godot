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

## Result envelope (0.9.2)

**Contract correction, not a payload migration.** Every release that shipped `execute_typed_action`
(0.7.0 onward) returned a successful result inside Core's standard success envelope: `success`,
`message`, optionally `error`/`prompt`, and the nine receipt fields one level down under `context`.
Before 0.9.2 the *published* output contract — the generated `output_schema` of the skill — declared
that receipt as a flat top-level object, so the declared shape lagged the payload the runtime
actually returned. Since 0.9.2 the published contract declares the envelope the runtime has always
returned. The runtime result itself is unchanged across 0.9.1 to 0.9.2, so upgrading does not break
a consumer that reads the live payload; what changes is that code written against the old flat
declaration now agrees with what it reads at runtime.

Read the receipt from `context`:

| Declared before 0.9.2 | Declared since 0.9.2, always returned |
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

Two habits worth keeping:

- Gate on `payload.success` (const `true` for an applied action). It has been present in every
  result, and `context.status` still only ever carries `applied`, so it adds nothing beyond
  `success`.
- Keep reading failures from the error side of the envelope (`success: false` plus a string
  `error`). Rejected, missing-target, drifted, ignored-setter, cancelled, and orphaned calls were
  never a `status` value and still are not.

The shape the runtime returns (abridged `set_property` result):

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

The flat shape below is what the pre-0.9.2 **published contract** declared. No release ever
returned it: a consumer written against that declaration was already reading a payload that did not
exist, so no version-tolerant fallback is needed. Read the receipt from `context` directly:

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

```python
remaining = payload["context"]["budget"]["remaining"]
```

`execute_game_script` remains available only for compatibility. It invokes a named public method
and therefore is not an allowlist, is not the typed action path, and must not be used as playtest or
RL authority.
