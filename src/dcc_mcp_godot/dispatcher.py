"""In-process skill dispatcher for an external Godot editor bridge."""

from __future__ import annotations

from typing import Any, Callable

from .capability_dispatch import current_action_name


class GodotBridgeDispatcher:
    """Run Python wrappers inline; Godot executes their host call on its editor tick."""

    def dispatch_callable(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        action_name = kwargs.pop("action_name", "")
        kwargs.pop("affinity", None)
        kwargs.pop("context", None)
        kwargs.pop("skill_name", None)
        kwargs.pop("execution", None)
        kwargs.pop("timeout_hint_secs", None)
        token = current_action_name.set(action_name)
        try:
            return func(*args, **kwargs)
        finally:
            current_action_name.reset(token)
