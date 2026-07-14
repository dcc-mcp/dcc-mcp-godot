"""Godot MCP server composition and lifecycle."""

from __future__ import annotations

import os
import signal
import threading
from pathlib import Path
from typing import Any, Optional

from dcc_mcp_core import DccServerOptions, HostExecutionBridge
from dcc_mcp_core.host import QueueDispatcher, StandaloneHost
from dcc_mcp_core.server_base import DccServerBase

from .__version__ import __version__
from .bridge import start_bridge, stop_bridge
from .dispatcher import GodotBridgeDispatcher

DEFAULT_PORT = 8765
_server: Optional["GodotMcpServer"] = None


class GodotMcpServer(DccServerBase):
    """DCC-MCP server backed by the bundled Godot EditorPlugin."""

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        self._host_dispatcher = QueueDispatcher()
        self._host_driver = StandaloneHost(
            self._host_dispatcher,
            thread_name="dcc-mcp-godot-host",
        )
        execution_bridge = HostExecutionBridge(
            dispatcher=GodotBridgeDispatcher(),
            host_dispatcher=self._host_dispatcher,
            default_thread_affinity="main",
            default_execution="sync",
            default_timeout_hint_secs=60,
        )
        options = DccServerOptions.from_env(
            "godot",
            Path(__file__).resolve().parent / "skills",
            port=port,
            server_name="dcc-mcp-godot",
            server_version=__version__,
            execution_bridge=execution_bridge,
        )
        super().__init__(options=options)

    def start(self, **kwargs: Any) -> Any:
        start_bridge()
        try:
            self._host_driver.start()
            return super().start(**kwargs)
        except Exception:
            self._host_driver.stop()
            stop_bridge()
            raise

    def stop(self) -> None:
        try:
            super().stop()
        finally:
            try:
                self._host_driver.stop()
            finally:
                stop_bridge()

    def _version_string(self) -> str:
        return os.environ.get("DCC_MCP_GODOT_VERSION", "unknown")


def start_server(port: Optional[int] = None) -> GodotMcpServer:
    global _server
    if _server is None or not _server.is_running:
        _server = GodotMcpServer(port or int(os.environ.get("DCC_MCP_GODOT_PORT", DEFAULT_PORT)))
        _server.register_builtin_actions()
        _server.start()
    return _server


def stop_server() -> None:
    global _server
    if _server is not None:
        _server.stop()
        _server = None


def main() -> None:
    """Run the standalone adapter until interrupted."""
    stopped = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    start_server()
    try:
        stopped.wait()
    finally:
        stop_server()


if __name__ == "__main__":
    main()
