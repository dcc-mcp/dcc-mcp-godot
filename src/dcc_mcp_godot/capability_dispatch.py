"""Shared dispatcher used by the fine-grained Godot capability skills."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from dcc_mcp_core.skill import skill_success
from dcc_mcp_core.skills_helper import check_dcc_cancelled

from dcc_mcp_godot.bridge import call_host
from dcc_mcp_godot.screenshot import finalize_screenshot, finalize_screenshot_batch

current_action_name: ContextVar[str] = ContextVar("godot_capability_action", default="")


def dispatch(action_name: str, params: dict[str, Any]) -> Any:
    """Forward one declared skill action to the editor bridge."""
    action_name = action_name or current_action_name.get()
    if not action_name:
        raise ValueError("Godot capability action name is missing")
    action_name = action_name.rsplit("__", 1)[-1]
    if action_name == "execute_typed_action":
        result = _dispatch_typed_action(params)
    else:
        result = call_host(f"capability.{action_name}", params)
    if action_name in {"get_editor_screenshot", "get_game_screenshot"}:
        result = finalize_screenshot(
            result,
            include_base64=bool(params.get("include_base64", False)),
        )
    elif action_name == "capture_frames":
        result = finalize_screenshot_batch(result)
    return skill_success(f"Godot action {action_name} completed.", **result)


def _dispatch_typed_action(params: dict[str, Any]) -> dict[str, Any]:
    """Claim one host mutation, with cancellation checks on both sides of it."""
    check_dcc_cancelled()
    reservation = call_host("capability.reserve_typed_action", params)
    reservation_id = str(reservation.get("reservation_id", ""))
    boundary_params = {"reservation_id": reservation_id}
    try:
        check_dcc_cancelled()
    except BaseException:
        if reservation_id:
            _rollback_typed_action(boundary_params)
        raise
    if not reservation_id:
        raise RuntimeError("Godot typed-action host returned no reservation identity")
    call_host("capability.commit_typed_action", boundary_params)
    try:
        check_dcc_cancelled()
    except BaseException:
        _rollback_typed_action(boundary_params)
        raise
    return call_host("capability.finalize_typed_action", boundary_params)


def _rollback_typed_action(params: dict[str, str]) -> None:
    """Best-effort immediate rollback; the runtime also expires orphaned claims."""
    try:
        call_host("capability.rollback_typed_action", params)
    except Exception:
        pass
