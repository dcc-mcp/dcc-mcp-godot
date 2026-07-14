"""Loopback WebSocket bridge shared by the MCP server and Godot plugin."""

from __future__ import annotations

import os
import threading
from typing import Any

from dcc_mcp_core.bridge import DccBridge

_bridge: DccBridge | None = None
_lock = threading.Lock()


def get_bridge() -> DccBridge:
    """Return the process-wide bridge, creating it without starting it."""
    global _bridge
    with _lock:
        if _bridge is None:
            port = int(os.environ.get("DCC_MCP_GODOT_BRIDGE_PORT", "3847"))
            _bridge = DccBridge(
                host="127.0.0.1",
                port=port,
                timeout=float(os.environ.get("DCC_MCP_GODOT_BRIDGE_TIMEOUT", "60")),
                server_name="dcc-mcp-godot",
            )
            os.environ.setdefault("DCC_MCP_GODOT_BRIDGE_URL", f"ws://127.0.0.1:{port}")
        return _bridge


def start_bridge() -> DccBridge:
    bridge = get_bridge()
    bridge.connect(wait_for_dcc=False)
    return bridge


def stop_bridge() -> None:
    global _bridge
    with _lock:
        bridge, _bridge = _bridge, None
    if bridge is not None:
        bridge.disconnect()


def call_host(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Invoke one typed command in the connected Godot editor plugin."""
    result = get_bridge().call(method, **(params or {}))
    if not isinstance(result, dict):
        return {"value": result}
    return result
