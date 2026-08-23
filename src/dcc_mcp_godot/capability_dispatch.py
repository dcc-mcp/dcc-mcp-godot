"""Shared dispatcher used by the fine-grained Godot capability skills."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from dcc_mcp_core.skill import skill_success

from dcc_mcp_godot.bridge import call_host
from dcc_mcp_godot.screenshot import finalize_screenshot

current_action_name: ContextVar[str] = ContextVar("godot_capability_action", default="")


def dispatch(action_name: str, params: dict[str, Any]) -> Any:
    """Forward one declared skill action to the editor bridge."""
    action_name = action_name or current_action_name.get()
    if not action_name:
        raise ValueError("Godot capability action name is missing")
    action_name = action_name.rsplit("__", 1)[-1]
    result = call_host(f"capability.{action_name}", params)
    if action_name == "get_game_screenshot":
        result = finalize_screenshot(
            result,
            include_base64=bool(params.get("include_base64", False)),
        )
    return skill_success(f"Godot action {action_name} completed.", **result)
