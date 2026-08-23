"""Loopback WebSocket bridge shared by the MCP server and Godot plugin."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any

from dcc_mcp_core.bridge import DccBridge

logger = logging.getLogger(__name__)

_bridge: DccBridge | None = None
_lock = threading.Lock()


class GodotDccBridge(DccBridge):
    """Core bridge configured for an editor that may stop polling while idle."""

    async def _serve(self) -> None:
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "The 'websockets' package is required for DccBridge. "
                "Install it with: pip install websockets"
            ) from exc

        shutdown_event = asyncio.Event()
        self._shutdown_event = shutdown_event
        try:
            # Godot's WebSocketPeer only handles control frames while the editor
            # main loop polls it.  An idle or unfocused editor may therefore miss
            # the library's default ping deadline despite remaining alive.  This
            # loopback transport relies on TCP close for process-death detection.
            async with websockets.serve(
                self._handle_dcc,
                self._host,
                self._port,
                ping_interval=None,
            ) as server:
                self._ws_server = server
                self._server_ready.set()
                logger.debug("Godot DccBridge listening on %s", self.endpoint)
                await shutdown_event.wait()
        finally:
            self._shutdown_event = None
            self._ws_server = None


def get_bridge() -> DccBridge:
    """Return the process-wide bridge, creating it without starting it."""
    global _bridge
    with _lock:
        if _bridge is None:
            port = int(os.environ.get("DCC_MCP_GODOT_BRIDGE_PORT", "3847"))
            _bridge = GodotDccBridge(
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
    wire_params = dict(params or {})
    if "method" in wire_params:
        # DccBridge.call() owns the Python ``method`` keyword. Keep the public
        # tool field while using a private wire key inside the Godot adapter.
        wire_params["__method__"] = wire_params.pop("method")
    result = get_bridge().call(method, **wire_params)
    if not isinstance(result, dict):
        return {"value": result}
    return result
