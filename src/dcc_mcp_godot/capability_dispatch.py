"""Shared dispatcher used by the fine-grained Godot capability skills."""

from __future__ import annotations

import secrets
import threading
from contextvars import ContextVar, copy_context
from typing import Any

from dcc_mcp_core.skill import skill_success
from dcc_mcp_core.skills_helper import check_dcc_cancelled, current_job_id

from dcc_mcp_godot.bridge import call_host
from dcc_mcp_godot.screenshot import finalize_screenshot, finalize_screenshot_batch

current_action_name: ContextVar[str] = ContextVar("godot_capability_action", default="")


class _TypedActionCommitGuard:
    """Recheck cancellation at the adapter-to-host mutation boundary."""

    def __init__(self, params: dict[str, Any]) -> None:
        self._context = copy_context()
        self._lock = threading.Lock()
        self._claimed = False
        self.wire_claim = {
            "claim_id": secrets.token_hex(16),
            "job_id": current_job_id() or f"sync-{secrets.token_hex(16)}",
            "project_id": str(params.get("project_id", "")),
            "session_id": str(params.get("session_id", "")),
            "runtime_id": str(params.get("runtime_id", "")),
            "authority_id": str(params.get("authority_id", "")),
            "manifest_id": str(params.get("manifest_id", "")),
            "manifest_digest": str(params.get("manifest_digest", "")),
            "action_id": str(params.get("action", {}).get("id", "")),
        }

    def claim(self) -> None:
        with self._lock:
            if self._claimed:
                raise RuntimeError("Godot typed-action host commit was already claimed")
            self._context.run(check_dcc_cancelled)
            self._claimed = True

    @property
    def claimed(self) -> bool:
        with self._lock:
            return self._claimed


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
    commit_guard = _TypedActionCommitGuard(params)
    commit_params = {
        **boundary_params,
        "commit_claim": commit_guard.wire_claim,
    }
    try:
        call_host(
            "capability.commit_typed_action",
            commit_params,
            commit_guard=commit_guard,
        )
    except BaseException:
        if not commit_guard.claimed:
            _rollback_typed_action(boundary_params)
        raise
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
