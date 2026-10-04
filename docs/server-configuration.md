# Embedded server configuration

Requires Core 0.20.41 or newer, the verified public options contract used here.

`GodotMcpServer(port=None, *, ...)` accepts the following keyword-only Core
options: `gateway_port`, `registry_dir`, `enable_gateway_failover`,
`strict_gateway`, `enable_file_logging`, `enable_job_persistence`,
`enable_telemetry`, `enable_checkpoint_persistence`, `enable_checkpoint_tools`,
`job_retention_hours`, and `checkpoint_path`. Defaults match Core's normal
adapter defaults. Explicit `gateway_port=0` and `enable_gateway_failover=False`
are preserved. `port=None` retains Core environment resolution; `port=0`
requests an OS-assigned adapter port.

These are public `DccServerOptions.from_env` parameters, not arguments to
`start`. The adapter always owns its `godot` identity, version, bundled skills,
`HostExecutionBridge`, and `QueueDispatcher`. Unsupported keywords, including
identity and dispatcher overrides, raise `TypeError` before construction.
The read-only `server.options` property exposes resolved frozen options for
inspection before an explicit `server.start()`.

For process-local state, set Core's documented `DCC_MCP_LOG_DIR` and
`DCC_MCP_JOB_STORAGE_PATH` environment variables before constructing the server.
Pass `registry_dir` and `checkpoint_path` explicitly. Alternatively disable
file logging, job persistence and checkpoint persistence using the corresponding
constructor flags. Paths are owned by the controller; the adapter does not
change global environment variables or silently redirect existing state.
`DCC_MCP_DISABLE_TELEMETRY=1` is Core's environment opt-out in addition to the
explicit constructor flag. There is no `log_dir` or `job_storage_path`
constructor keyword in Core's options contract.

```python
from dcc_mcp_godot.server import GodotMcpServer

server = GodotMcpServer(
    port=0,
    gateway_port=0,
    enable_gateway_failover=False,
    registry_dir="./session/registry",
    enable_telemetry=False,
    enable_file_logging=False,
    enable_job_persistence=False,
    enable_checkpoint_persistence=False,
)
assert server.options.gateway.port == 0
assert server.options.gateway.enable_failover is False
# The controller chooses when to register actions, start, and stop the server.
```

The WebSocket bridge is configured separately. Set both
`DCC_MCP_GODOT_BRIDGE_PORT` and `DCC_MCP_GODOT_BRIDGE_URL` to the same loopback
endpoint before launching the adapter and editor. The addon consumes the URL;
the Python bridge consumes the port. Configuration does not establish native
editor readiness or prove that a PNG has finished importing.
