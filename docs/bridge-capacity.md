# Bounded bridge message capacity

The Godot bridge has a **1,048,576-byte (1 MiB) maximum complete UTF-8 JSON
message**, in both directions. This includes the envelope, request ID, JSON
escaping and typed-action commit fence. It is not a source-character budget.
Existing capability limits (including the 1,000,000-byte text-file limit) remain
independent and unchanged; passing a semantic limit does not guarantee that
the encoded request fits.

The addon advertises `transport.max_message_bytes` in its connection's `hello`.
Python pins that value to the connection and never accepts a value above its
own limit. Missing, invalid or unsupported capacity advertisements retain the
legacy 65,535-byte request budget, so an old addon fails before send rather than
disconnecting. Upgrade both the Python package and the project addon to use
the larger capacity. A reconnect does not inherit the previous peer's budget.

Both Godot socket buffers are finite (2 MiB), leaving framing/queue headroom;
Python's WebSocket receive limit is explicitly 1 MiB. Godot independently rejects
inbound messages exceeding the protocol limit. These bounds do not authorize
larger files, unbounded queues or additional host actions.

## Errors and recovery

Typed capability tools expose `bridge_message_too_large`, with context fields
`code: -32005`, `direction`, `actual_bytes`, `max_bytes` and `outcome`:

- `direction: request`, `outcome: not_dispatched`: the final encoded request
  was rejected before any bytes were sent or host commit guard was claimed.
  Send smaller typed operations. There is no automatic chunking or truncation.
- `direction: response`, `outcome: unknown`: the host operation ran, but its
  result did not fit. A compact structured error replaces the oversized result.
  **Inspect state before retrying a mutation.** Prefer bounded or path-only
  reads when available.

Both size rejections preserve the connection for subsequent small requests.
An actual socket send failure instead closes the connection explicitly because
a full/broken queue cannot reliably deliver another error. It does not imply
that an operation did not run, and no automatic mutation retry is performed.

## Verification

`tests/test_bridge_capacity.py` covers exact boundaries, Unicode and escaping,
final guarded envelopes, legacy/malformed advertisements, per-connection
budgets, recovery, and the public structured error.

The real-editor smoke performs a typed MCP create/read/validate round trip of
a 90,014-byte mixed Unicode/escaped GDScript, verifies its exact on-disk bytes,
rejects an oversized write before file creation, and rejects an oversized
UTF-8 result from a tiny typed-authored `@tool` script. Both rejection paths
must leave the same connection usable. Run only this headless subset with:

```bash
python tests/live_godot_smoke.py --godot /path/to/godot --bridge-capacity-only
```

The regular CI live smoke includes the same checks before its full editor and
gameplay regression. A focused capacity pass is not a full gameplay pass.
