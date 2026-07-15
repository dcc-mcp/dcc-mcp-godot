"""Live readiness tracking for the Godot editor bridge."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class BridgeReadinessMonitor:
    """Mirror the live EditorPlugin connection into adapter readiness bits."""

    def __init__(
        self,
        binder: Any,
        is_connected: Callable[[], bool],
        *,
        poll_interval_secs: float = 0.1,
    ) -> None:
        self._binder = binder
        self._is_connected = is_connected
        self._poll_interval_secs = poll_interval_secs
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_ready: bool | None = None

    def start(self) -> None:
        """Publish current state and start watching for disconnects/reconnects."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.refresh()
        self._thread = threading.Thread(
            target=self._run,
            name="dcc-mcp-godot-readiness",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop monitoring and make bridge-dependent readiness explicitly red."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._poll_interval_secs * 4.0))
            self._thread = None
        self._publish(False)

    def refresh(self) -> bool:
        """Synchronously sample and publish the current bridge connection."""
        try:
            ready = bool(self._is_connected())
        except Exception as exc:
            logger.warning("Godot bridge readiness probe failed: %s", exc)
            ready = False
        if ready != self._last_ready:
            self._publish(ready)
        return ready

    def _run(self) -> None:
        while not self._stop_event.wait(self._poll_interval_secs):
            self.refresh()

    def _publish(self, ready: bool) -> None:
        self._binder.mark_dispatcher_ready(
            True,
            dcc_ready=ready,
            host_execution_bridge_ready=ready,
            main_thread_executor_ready=ready,
        )
        self._last_ready = ready


__all__ = ["BridgeReadinessMonitor"]
