"""Publish typed Godot editor context through the Core instance metadata surface."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from typing import Any

logger = logging.getLogger(__name__)


class GodotContextPublisher:
    """Read one main-thread editor snapshot and publish it through Core."""

    def __init__(
        self,
        *,
        call_host: Callable[[str], Mapping[str, Any]],
        publish: Callable[..., bool],
    ) -> None:
        self._call_host = call_host
        self._publish = publish

    def refresh(self) -> bool:
        """Publish the latest Godot project and edited-scene context."""
        snapshot = self._call_host("context.snapshot")
        version = snapshot.get("version")
        display_name = snapshot.get("display_name")
        scene = snapshot.get("scene")
        documents = snapshot.get("documents")
        if (
            not isinstance(version, str)
            or not version.strip()
            or version.strip().lower() == "unknown"
            or not isinstance(display_name, str)
            or not display_name.strip()
            or not isinstance(scene, str)
            or not isinstance(documents, list)
            or any(not isinstance(document, str) for document in documents)
        ):
            return False
        return bool(
            self._publish(
                version=version,
                display_name=display_name,
                scene=scene,
                documents=documents,
            )
        )


class GodotContextMonitor:
    """Refresh editor context without touching the Godot API off its bridge."""

    def __init__(
        self,
        publisher: GodotContextPublisher,
        *,
        is_connected: Callable[[], bool],
        poll_interval_secs: float = 1.0,
    ) -> None:
        self._publisher = publisher
        self._is_connected = is_connected
        self._poll_interval_secs = poll_interval_secs
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="dcc-mcp-godot-context",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._poll_interval_secs * 2.0))
            if not self._thread.is_alive():
                self._thread = None

    def refresh(self) -> bool:
        """Publish one snapshot when connected, preserving the last good context on failure."""
        try:
            return bool(self._is_connected() and self._publisher.refresh())
        except Exception as exc:
            logger.warning("Godot context refresh failed: %s", exc)
            return False

    def _run(self) -> None:
        while not self._stop_event.wait(self._poll_interval_secs):
            self.refresh()


__all__ = ["GodotContextMonitor", "GodotContextPublisher"]
