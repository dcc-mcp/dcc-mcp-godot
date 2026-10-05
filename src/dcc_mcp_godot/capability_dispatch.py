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
from dcc_mcp_godot.ui_texture import (
    TextureImportPending,
    TextureValidationError,
    prepare_texture,
    validate_request,
)

current_action_name: ContextVar[str] = ContextVar("godot_capability_action", default="")

# Actions whose published schema declares both ``path`` and the deprecated
# ``script_path`` alias. The host prefers ``path``, so a caller that only sends
# the alias used to be answered about an empty path; empty GDScript reloads as
# OK, which reported a successful check for no script at all. Resolving the
# alias here keeps the deprecated name working without a host round trip.
SCRIPT_PATH_ALIAS_ACTIONS = frozenset({"validate_script"})


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
    if action_name == "assign_ui_texture":
        result = _dispatch_ui_texture(params)
        return skill_success(
            f"Godot UI texture status: {result.get('status', 'unknown')}.", **result
        )
    elif action_name == "execute_typed_action":
        result = _dispatch_typed_action(params)
    else:
        if action_name in SCRIPT_PATH_ALIAS_ACTIONS:
            params = normalize_script_path_alias(params)
        result = call_host(f"capability.{action_name}", params)
    if action_name in {"get_editor_screenshot", "get_game_screenshot"}:
        result = finalize_screenshot(
            result,
            include_base64=bool(params.get("include_base64", False)),
        )
    elif action_name == "render_scene_preview":
        result = finalize_screenshot(
            result,
            include_base64=bool(params.get("include_base64", False)),
            with_metrics=True,
        )
    elif action_name == "capture_frames":
        result = finalize_screenshot_batch(result)
    return skill_success(f"Godot action {action_name} completed.", **result)


def normalize_script_path_alias(params: dict[str, Any]) -> dict[str, Any]:
    """Resolve the deprecated ``script_path`` alias onto ``path``.

    Raises ``ValueError`` for the inputs the host would have answered with a
    silently successful empty check: a conflicting alias pair, an explicitly
    empty alias, or no path and no ``source`` to compile.
    """
    path = str(params.get("path") or "")
    alias = str(params.get("script_path") or "")
    if path and alias and path != alias:
        raise ValueError(f"Conflicting script paths: path={path} but script_path={alias}")
    if ("path" in params and not path) or ("script_path" in params and not alias):
        raise ValueError("path (or script_path) must be a non-empty res:// path when supplied")
    resolved = path or alias
    if not resolved and not str(params.get("source") or ""):
        raise ValueError("validate_script requires a non-empty source, or path (or script_path)")
    if resolved and not path:
        return {**params, "path": resolved}
    return params


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


def _dispatch_ui_texture(params: dict[str, Any]) -> dict[str, Any]:
    """Bind file validation to the currently connected editor project."""
    try:
        validate_request(params)
        check_dcc_cancelled()
        project = call_host("capability.get_project_info", {})
        prepared = prepare_texture(str(project.get("project_path", "")), params)
        check_dcc_cancelled()
        return call_host("capability.assign_ui_texture", prepared)
    except TextureImportPending as exc:
        return {"assigned": False, "status": "import_pending", "reason": str(exc)}
    except TextureValidationError as exc:
        return {"assigned": False, "status": "rejected", "reason": str(exc)}
    except OSError:
        return {
            "assigned": False,
            "status": "rejected",
            "reason": "Project file could not be read safely",
        }
