"""Godot MCP server composition and lifecycle."""

from __future__ import annotations

import os
import signal
import threading
from pathlib import Path
from typing import Any, Optional

from dcc_mcp_core import AdapterReadinessBinder, DccServerOptions, HostExecutionBridge
from dcc_mcp_core.host import QueueDispatcher, StandaloneHost
from dcc_mcp_core.server_base import DccServerBase

from .__version__ import __version__
from .bridge import call_host, get_bridge, start_bridge, stop_bridge
from .context import GodotContextMonitor, GodotContextPublisher
from .dispatcher import GodotBridgeDispatcher
from .readiness import BridgeReadinessMonitor

DEFAULT_PORT = 0
_server: Optional["GodotMcpServer"] = None


class GodotMcpServer(DccServerBase):
    """DCC-MCP server backed by the bundled Godot EditorPlugin."""

    def __init__(
        self,
        port: Optional[int] = None,
        *,
        gateway_port: Optional[int] = None,
        registry_dir: Optional[str] = None,
        enable_gateway_failover: bool = True,
        strict_gateway: bool = False,
        enable_file_logging: bool = True,
        enable_job_persistence: bool = True,
        enable_telemetry: bool = True,
        enable_checkpoint_persistence: bool = True,
        enable_checkpoint_tools: bool = True,
        job_retention_hours: Optional[int] = None,
        checkpoint_path: Optional[str] = None,
    ) -> None:
        """Compose Godot with Core's public gateway and observability options.

        Identity, bundled skills and the host execution bridge belong to this
        adapter. Log and job paths use Core's documented process environment;
        see ``docs/server-configuration.md``. Construction does not start the
        bridge, host driver or MCP listener; call ``start`` explicitly.
        """
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
            gateway_port=gateway_port,
            registry_dir=registry_dir,
            enable_gateway_failover=enable_gateway_failover,
            strict_gateway=strict_gateway,
            enable_file_logging=enable_file_logging,
            enable_job_persistence=enable_job_persistence,
            enable_telemetry=enable_telemetry,
            enable_checkpoint_persistence=enable_checkpoint_persistence,
            enable_checkpoint_tools=enable_checkpoint_tools,
            job_retention_hours=job_retention_hours,
            checkpoint_path=checkpoint_path,
        )
        self._godot_options = options
        super().__init__(options=options)
        self._readiness_binder = AdapterReadinessBinder(
            self,
            dcc_ready_probe=self._bridge_connected,
        )
        self._readiness_monitor = BridgeReadinessMonitor(
            self._readiness_binder,
            self._bridge_connected,
        )
        self._context_publisher = GodotContextPublisher(
            call_host=call_host,
            publish=self.update_gateway_metadata,
        )
        self._context_monitor = GodotContextMonitor(
            self._context_publisher,
            is_connected=self._bridge_connected,
        )

    @property
    def options(self) -> DccServerOptions:
        """Resolved, immutable construction options for launch controllers."""
        return self._godot_options

    def start(self, **kwargs: Any) -> Any:
        start_bridge()
        try:
            self._host_driver.start()
            self._readiness_monitor.start()
            handle = super().start(**kwargs)
            self._context_monitor.start()
            return handle
        except Exception:
            self._context_monitor.stop()
            self._readiness_monitor.stop()
            self._host_driver.stop()
            stop_bridge()
            raise

    def stop(self) -> None:
        try:
            self._context_monitor.stop()
            self._readiness_monitor.stop()
            super().stop()
        finally:
            try:
                self._host_driver.stop()
            finally:
                stop_bridge()

    def _version_string(self) -> str:
        return os.environ.get("DCC_MCP_GODOT_VERSION", "unknown")

    @staticmethod
    def _bridge_connected() -> bool:
        """Return the current process-wide bridge state, including after restart."""
        return get_bridge().is_connected()


def start_server(port: Optional[int] = None) -> GodotMcpServer:
    global _server
    if _server is None or not _server.is_running:
        _server = GodotMcpServer(port)
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
