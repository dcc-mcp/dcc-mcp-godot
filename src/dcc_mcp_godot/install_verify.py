"""Live, instance-bound verification for a receipt-owned Godot install."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dcc_mcp_core.install_lifecycle import (
    query_runtime_state,
)

from .install_contract import INSTALL_EXIT_OK, INSTALL_EXIT_VERIFY, plan_result
from .install_project import inspect_install


def run_probe_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _failure(project: Path, stage: str, reason: str) -> tuple[int, dict[str, Any]]:
    result = plan_result(project)
    result.update(status="failed")
    result["steps"] = [{"id": stage, "status": "failed", "message": reason}]
    result["verify"] = {
        "directly_usable": False,
        "failure_stage": stage,
        "failure_reason": reason,
    }
    return INSTALL_EXIT_VERIFY, result


def _find_json_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for nested in value.values():
            found = _find_json_value(nested, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_json_value(nested, key)
            if found is not None:
                return found
    return None


def _command_error(completed: subprocess.CompletedProcess[str], fallback: str) -> str:
    return (completed.stderr or completed.stdout).strip() or fallback


def _call_core_tool(
    mcp_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout_secs: float,
) -> dict[str, Any]:
    """Call the Core-owned MCP route without requiring an external CLI."""
    parsed = urlsplit(mcp_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        return {"success": False, "status": "probe_invalid_url", "message": "invalid MCP URL"}
    request = urllib.request.Request(
        mcp_url,
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": f"install-verify-{uuid.uuid4().hex}",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        ).encode("utf-8"),
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(0.1, timeout_secs)) as response:
            status_code = int(getattr(response, "status", 200))
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        try:
            error_payload = json.loads(response_body)
        except json.JSONDecodeError:
            error_payload = None
        reason = _find_json_value(error_payload, "message")
        return {
            "success": False,
            "status": "probe_http_error",
            "http_status": exc.code,
            "message": str(reason or f"Core tool route returned HTTP {exc.code}"),
        }
    except (OSError, ValueError):
        return {
            "success": False,
            "status": "probe_unreachable",
            "message": "Core tool route is unreachable",
        }
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"success": False, "status": "probe_bad_response", "message": "invalid Core JSON"}
    error = payload.get("error") if isinstance(payload, dict) else None
    output = payload.get("result") if isinstance(payload, dict) else None
    if (
        status_code >= 300
        or error
        or (
            isinstance(output, dict)
            and (output.get("success") is False or output.get("isError") is True)
        )
    ):
        reason = _find_json_value(error or output, "message")
        return {
            "success": False,
            "status": "probe_failed",
            "message": str(reason or "Core tool call failed"),
        }
    return {"success": True, "result": output}


def _runtime_instances() -> tuple[dict[str, str], str | None]:
    deadline = time.monotonic() + 5.0
    while True:
        try:
            state = query_runtime_state(
                None,
                dcc_type="godot",
                role="runtime",
                include_dead=False,
            )
        except OSError:
            if time.monotonic() >= deadline:
                return {}, "runtime registry is temporarily unavailable"
            time.sleep(0.05)
            continue
        entries = state.get("entries", []) if isinstance(state, dict) else []
        instances = {
            str(entry["instance_id"]): str(entry["mcp_url"])
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("runtime_alive") is not False
            and isinstance(entry.get("instance_id"), str)
            and isinstance(entry.get("mcp_url"), str)
        }
        return instances, None if instances else "no live Godot instance"


def _terminal_probe(mcp_url: str, probe: dict[str, Any]) -> dict[str, Any]:
    job_id = _find_json_value(probe, "job_id")
    if not isinstance(job_id, str) or not job_id:
        return probe
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        status = _call_core_tool(
            mcp_url,
            "jobs_get_status",
            {"job_id": job_id, "include_result": True},
            timeout_secs=5.0,
        )
        job_status = _find_json_value(status, "status")
        if job_status == "completed":
            return status
        if job_status in {"failed", "cancelled", "interrupted"}:
            return {"success": False, "message": f"typed project ping {job_status}"}
        time.sleep(0.05)
    return {"success": False, "message": "typed project ping timed out"}


def _wait_for_skill_load(mcp_url: str) -> dict[str, Any]:
    deadline = time.monotonic() + 5.0
    loaded: dict[str, Any] = {"success": False, "message": "instance is not ready"}
    while time.monotonic() < deadline:
        loaded = _call_core_tool(
            mcp_url,
            "load_skill",
            {"skill_names": ["godot-project-management"]},
            timeout_secs=1.0,
        )
        if loaded.get("success"):
            return loaded
        if loaded.get("status") not in {"probe_http_error", "probe_unreachable"}:
            return loaded
        time.sleep(0.1)
    return loaded


def _probe_instance(mcp_url: str) -> tuple[str, str | None, Any]:
    loaded = _wait_for_skill_load(mcp_url)
    if not loaded.get("success"):
        return "readiness", str(loaded.get("message") or "instance is not ready"), None
    ping = _call_core_tool(
        mcp_url,
        "godot_project_management__get_project_info",
        {},
        timeout_secs=15.0,
    )
    ping = _terminal_probe(mcp_url, ping)
    if not ping.get("success"):
        return "typed_ping", str(ping.get("message") or "typed project ping failed"), None
    return "ok", None, ping


def verify(project: Path, instance_id: str | None = None) -> tuple[int, dict[str, Any]]:
    """Verify import, ready bits, typed ping, and exact target-project ownership."""
    project = project.resolve()
    state = inspect_install(project)
    if state["install_state"] != "installed" or state["receipt"] is None:
        return _failure(project, "install", "installation is absent or partial")
    python = str(state["receipt"].get("python", sys.executable))
    imported = run_probe_command([python, "-c", "import dcc_mcp_godot"])
    if imported.returncode != 0:
        return _failure(project, "import", _command_error(imported, "target import failed"))
    instances, discovery_error = _runtime_instances()
    if not instances:
        return _failure(project, "readiness", discovery_error or "no live Godot instance")
    if instance_id is not None:
        if instance_id not in instances:
            return _failure(project, "target_binding", "requested Godot instance is not registered")
        instance_ids = [instance_id]
    else:
        instance_ids = list(instances)
    last_stage = "readiness"
    last_reason = "no ready Godot instance"
    matched_instance: str | None = None
    for candidate_id in instance_ids:
        stage, reason, response = _probe_instance(instances[candidate_id])
        if stage != "ok":
            last_stage, last_reason = stage, reason or last_reason
            continue
        project_path = _find_json_value(response, "project_path")
        if isinstance(project_path, str) and Path(project_path).resolve() == project:
            matched_instance = candidate_id
            break
        last_stage = "target_binding"
        last_reason = "ready instance is not the target project"
    if matched_instance is None:
        return _failure(project, last_stage, last_reason)
    result = plan_result(project)
    result.update(status="ok", install_state="installed", instance_id=matched_instance)
    result["steps"] = [
        {"id": "inspect", "status": "ok"},
        {"id": "import", "status": "ok"},
        {"id": "readiness", "status": "ok"},
        {"id": "typed_ping", "status": "ok"},
    ]
    result["verify"] = {
        "directly_usable": True,
        "failure_stage": None,
        "failure_reason": None,
    }
    return INSTALL_EXIT_OK, result


__all__ = ["run_probe_command", "verify"]
