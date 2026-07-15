"""Run the production bridge and roguelike skill against a real Godot editor."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, NoReturn

from dcc_mcp_godot import bridge
from dcc_mcp_godot.server import GodotMcpServer

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "src" / "dcc_mcp_godot"


def _mcp_post(mcp_url: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    request = urllib.request.Request(
        mcp_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MCP {method} failed with HTTP {error.code}: {body}") from error


def _raise_mcp_error(action: str, response: dict[str, Any]) -> NoReturn:
    raise RuntimeError(f"MCP {action} failed: {json.dumps(response, indent=2, sort_keys=True)}")


def _call_tool(
    mcp_url: str,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    wait_for_terminal: bool = True,
) -> dict[str, Any]:
    params: dict[str, Any] = {"name": name, "arguments": arguments or {}}
    response = _mcp_post(
        mcp_url,
        "tools/call",
        params,
    )
    result = response.get("result", {})
    if response.get("error") or result.get("isError") is True:
        _raise_mcp_error(name, response)
    if wait_for_terminal:
        envelope = result.get("structuredContent")
        if envelope is None and result.get("content"):
            envelope = json.loads(result["content"][0]["text"])
        job_id = envelope.get("job_id") if isinstance(envelope, dict) else None
        if job_id:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                poll = _mcp_post(
                    mcp_url,
                    "tools/call",
                    {
                        "name": "jobs_get_status",
                        "arguments": {"job_id": job_id, "include_result": True},
                    },
                )
                poll_result = poll.get("result", {})
                if poll.get("error") or poll_result.get("isError") is True:
                    _raise_mcp_error(f"jobs_get_status({job_id})", poll)
                status = poll_result.get("structuredContent")
                if status is None and poll_result.get("content"):
                    status = json.loads(poll_result["content"][0]["text"])
                if status.get("status") == "completed":
                    return poll
                if status.get("status") in {"failed", "cancelled", "interrupted"}:
                    _raise_mcp_error(f"job {job_id}", poll)
                time.sleep(0.05)
            raise TimeoutError(f"MCP job {job_id} did not complete within 90 seconds")
    return response


def _resolve_tool_name(mcp_url: str, suffix: str) -> str:
    names: list[str] = []
    cursor: str | None = None
    for _ in range(20):
        response = _mcp_post(mcp_url, "tools/list", {"cursor": cursor} if cursor else None)
        if response.get("error"):
            _raise_mcp_error("tools/list", response)
        result = response.get("result", {})
        names.extend(tool["name"] for tool in result.get("tools", []))
        cursor = result.get("nextCursor")
        if not cursor:
            break
    else:
        raise RuntimeError("MCP tools/list exceeded the 20-page smoke-test budget")
    matches = [name for name in names if name == suffix or name.endswith(f"__{suffix}")]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one MCP tool ending in {suffix!r}, found {matches!r}")
    return matches[0]


def _tool_context(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result", {})
    envelope = result.get("structuredContent")
    if envelope is None and result.get("content"):
        envelope = json.loads(result["content"][0]["text"])
    if isinstance(envelope, dict):
        if envelope.get("status") == "completed" and isinstance(envelope.get("result"), dict):
            envelope = envelope["result"]
        if envelope.get("success") is False:
            raise RuntimeError(f"Tool reported failure: {envelope!r}")
        return envelope.get("context", envelope)
    return {}


def run_smoke(godot: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="dcc-mcp-godot-") as directory:
        project = Path(directory)
        shutil.copy2(ROOT / "tests" / "godot_project" / "project.godot", project)
        shutil.copytree(
            PACKAGE / "godot_addon" / "addons",
            project / "addons",
        )
        log_path = project / "editor.log"
        log_stream = log_path.open("w", encoding="utf-8")
        editor: subprocess.Popen[str] | None = None
        server: GodotMcpServer | None = None
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                bridge_port = probe.getsockname()[1]
            os.environ["DCC_MCP_GODOT_BRIDGE_PORT"] = str(bridge_port)
            os.environ["DCC_MCP_GODOT_BRIDGE_URL"] = f"ws://127.0.0.1:{bridge_port}"
            server = GodotMcpServer(port=0)
            server.register_builtin_actions()
            server.start(install_atexit_hook=False)
            mcp_url = server.mcp_url
            if not mcp_url:
                raise RuntimeError("Godot MCP server did not publish an MCP URL")
            env = os.environ.copy()
            editor = subprocess.Popen(
                [
                    str(godot),
                    "--headless",
                    "--editor",
                    "--path",
                    str(project),
                    "--quit-after",
                    "3600",
                ],
                env=env,
                stdout=log_stream,
                stderr=subprocess.STDOUT,
                text=True,
            )
            deadline = time.monotonic() + 45
            while not bridge.get_bridge().is_connected() and time.monotonic() < deadline:
                if editor.poll() is not None:
                    break
                time.sleep(0.1)
            if not bridge.get_bridge().is_connected():
                log_stream.flush()
                raise RuntimeError(
                    f"Godot plugin did not connect.\n{log_path.read_text(encoding='utf-8')}"
                )

            try:
                _call_tool(
                    mcp_url,
                    "load_skill",
                    {
                        "skill_names": [
                            "godot-project-management",
                            "godot-scene-management",
                            "godot-node",
                            "godot-input",
                            "godot-runtime",
                        ]
                    },
                )
                project_info_tool = _resolve_tool_name(mcp_url, "get_project_info")
                create_scene_tool = _resolve_tool_name(mcp_url, "create_scene")
                add_node_tool = _resolve_tool_name(mcp_url, "add_node")
                save_scene_tool = _resolve_tool_name(mcp_url, "save_scene")
                play_scene_tool = _resolve_tool_name(mcp_url, "play_scene")
                runtime_status_tool = _resolve_tool_name(mcp_url, "get_runtime_status")
                runtime_tree_tool = _resolve_tool_name(mcp_url, "get_game_scene_tree")
                start_recording_tool = _resolve_tool_name(mcp_url, "start_recording")
                stop_recording_tool = _resolve_tool_name(mcp_url, "stop_recording")
                replay_recording_tool = _resolve_tool_name(mcp_url, "replay_recording")
                simulate_key_tool = _resolve_tool_name(mcp_url, "simulate_key")
                stop_scene_tool = _resolve_tool_name(mcp_url, "stop_scene")
                project_info = _tool_context(_call_tool(mcp_url, project_info_tool))
                if project_info.get("name") != "DCC-MCP Godot CI":
                    raise RuntimeError(f"Unexpected project metadata: {project_info!r}")
                _call_tool(
                    mcp_url,
                    create_scene_tool,
                    {"path": "res://capability_smoke.tscn", "root_type": "Node2D"},
                )
                _call_tool(
                    mcp_url,
                    add_node_tool,
                    {"type": "Label", "name": "CapabilityLabel", "parent_path": "."},
                )
                _call_tool(mcp_url, save_scene_tool)
                _call_tool(mcp_url, play_scene_tool, {"mode": "current"})
                runtime_status: dict[str, Any] = {}
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    runtime_status = _tool_context(_call_tool(mcp_url, runtime_status_tool))
                    if runtime_status.get("connected"):
                        break
                    time.sleep(0.1)
                if not runtime_status.get("connected"):
                    raise RuntimeError(f"Godot runtime peer did not connect: {runtime_status!r}")
                runtime_tree = _tool_context(_call_tool(mcp_url, runtime_tree_tool))
                if runtime_tree.get("root", {}).get("name") != "Root":
                    raise RuntimeError(f"Unexpected runtime scene tree: {runtime_tree!r}")
                _call_tool(mcp_url, start_recording_tool)
                _call_tool(mcp_url, simulate_key_tool, {"keycode": 65, "pressed": True})
                _call_tool(mcp_url, simulate_key_tool, {"keycode": 65, "pressed": False})
                recording = _tool_context(_call_tool(mcp_url, stop_recording_tool))
                replay = _tool_context(
                    _call_tool(
                        mcp_url,
                        replay_recording_tool,
                        {"events": recording.get("events", [])},
                    )
                )
                if [item.get("type") for item in replay.get("results", [])] != [
                    "key",
                    "key",
                ]:
                    raise RuntimeError(f"Runtime input replay lost event types: {replay!r}")
                _call_tool(mcp_url, stop_scene_tool)

                _call_tool(mcp_url, "load_skill", {"skill_name": "godot-roguelike"})
                create_tool = _resolve_tool_name(mcp_url, "create_2d_roguelike")
                validate_tool = _resolve_tool_name(mcp_url, "validate_2d_roguelike")
                _call_tool(
                    mcp_url,
                    create_tool,
                    {"title": "Agent Roguelike CI"},
                    wait_for_terminal=True,
                )
                _call_tool(mcp_url, validate_tool, wait_for_terminal=True)
            except Exception as error:
                log_stream.flush()
                editor_log = log_path.read_text(encoding="utf-8")
                raise RuntimeError(f"Godot skill bridge failed.\n{editor_log}") from error
        finally:
            if editor is not None and editor.poll() is None:
                editor.terminate()
                try:
                    editor.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    editor.kill()
            log_stream.close()
            if server is not None:
                server.stop()
            else:
                bridge.stop_bridge()

        completed = subprocess.run(
            [
                str(godot),
                "--headless",
                "--path",
                str(project),
                "--script",
                "res://roguelike/ci_smoke.gd",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        output = completed.stdout + completed.stderr
        if completed.returncode != 0 or "ROGUELIKE_SMOKE_OK" not in output:
            raise RuntimeError(f"Godot gameplay smoke failed ({completed.returncode}).\n{output}")
        print(output.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", type=Path, required=True)
    args = parser.parse_args()
    run_smoke(args.godot.resolve())


if __name__ == "__main__":
    main()
