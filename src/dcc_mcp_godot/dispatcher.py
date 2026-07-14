"""In-process skill dispatcher for an external Godot editor bridge."""

from __future__ import annotations

from typing import Any, Callable


class GodotBridgeDispatcher:
    """Run Python wrappers inline; Godot executes their host call on its editor tick."""

    def dispatch_callable(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        kwargs.pop("affinity", None)
        kwargs.pop("context", None)
        kwargs.pop("action_name", None)
        kwargs.pop("skill_name", None)
        kwargs.pop("execution", None)
        kwargs.pop("timeout_hint_secs", None)
        return func(*args, **kwargs)
