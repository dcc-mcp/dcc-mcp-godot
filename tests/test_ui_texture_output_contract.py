"""Validate actual Core envelopes through the SDK's public in-memory call path.

No Godot host, adapter server or network listener is started. The SDK fixture
returns CallToolResult directly so validation is performed by ClientSession,
matching the boundary that receives the adapter's serialized Core result.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml
from dcc_mcp_core.result_envelope import ToolResultEnvelope

from dcc_mcp_godot import capability_dispatch
from tools.generate_capability_skills import (
    UI_TEXTURE_CONTEXT_SCHEMA,
    UI_TEXTURE_OUTPUT_SCHEMA,
)

ROOT = Path(__file__).parents[1]
TOOL_NAME = "assign_ui_texture"
PARAMS = {"node_path": "Icon", "texture_path": "res://assets/red.png"}
SDK_CASES = [
    False,
    pytest.param(
        True,
        marks=pytest.mark.skipif(
            sys.version_info < (3, 10), reason="MCP SDK requires Python 3.10+"
        ),
    ),
]
ASSIGNED = {
    "assigned": True,
    "changed": True,
    "height": 16,
    "native_rgba8_sha256": "a" * 64,
    "node_path": "Icon",
    "node_type": "TextureRect",
    "property": "texture",
    # Object identity is an opaque string, including native signed values.
    "resource_instance_id": "-9223372036854775807",
    "resource_path": "res://assets/red.png",
    "resource_type": "CompressedTexture2D",
    "source_native_rgba8_matches_import": True,
    "source_sha256": "b" * 64,
    "status": "assigned",
    "undo_registered": True,
    "width": 16,
}


def declared_tool():
    inventory = yaml.safe_load(
        (ROOT / "src/dcc_mcp_godot/skills/godot-node/tools.yaml").read_text()
    )
    return next(tool for tool in inventory["tools"] if tool["name"] == TOOL_NAME)


def domain_result(status):
    if status in {"assigned", "unchanged"}:
        return {
            **ASSIGNED,
            "status": status,
            "changed": status == "assigned",
            "undo_registered": status == "assigned",
        }
    result = {"assigned": False, "status": status, "reason": "Expected bounded rejection"}
    if status == "assignment_failed":
        result["rollback_verified"] = True
    return result


def core_result(monkeypatch, result):
    monkeypatch.setattr(
        capability_dispatch, "_dispatch_ui_texture", lambda _: copy.deepcopy(result)
    )
    return capability_dispatch.dispatch(TOOL_NAME, PARAMS)


async def sdk_call(payload, output_schema, *, expect_invalid=False):
    """Use SDK initialize/list_tools/call_tool without patching its validator."""
    import anyio
    from mcp import types
    from mcp.server import Server
    from mcp.shared.memory import create_connected_server_and_client_session

    server = Server("ui-texture-output-contract")
    calls = []
    declared = declared_tool()

    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name=TOOL_NAME,
                inputSchema=declared["input_schema"],
                outputSchema=output_schema,
            )
        ]

    @server.call_tool()
    async def call_tool(name, arguments):
        calls.append((name, arguments))
        # A complete result models the Core wire boundary. The real client
        # still validates structuredContent after this handler has executed.
        return types.CallToolResult(content=[], structuredContent=payload, isError=False)

    with anyio.fail_after(5):
        async with create_connected_server_and_client_session(server) as session:
            catalog = await session.list_tools()
            assert catalog.tools[0].outputSchema == output_schema
            if expect_invalid:
                with pytest.raises(RuntimeError, match="Invalid structured content returned"):
                    await session.call_tool(TOOL_NAME, PARAMS)
                result = None
            else:
                result = await session.call_tool(TOOL_NAME, PARAMS)
                assert result.structuredContent == payload
                assert result.isError is False
            # Output validation failure happens after the handler executes.
            # SDK call_tool must neither erase this fact nor replay the call.
            assert calls == [(TOOL_NAME, PARAMS)]
            return result


def check_sdk(payload, output_schema, *, expect_invalid=False):
    import anyio

    async def check():
        await sdk_call(payload, output_schema, expect_invalid=expect_invalid)

    anyio.run(check)


@pytest.mark.parametrize(
    "status",
    ["assigned", "unchanged", "rejected", "import_pending", "import_failed", "assignment_failed"],
)
@pytest.mark.parametrize("use_sdk", SDK_CASES)
def test_core_dispatch_envelope_passes_declared_contract(monkeypatch, status, use_sdk):
    payload = core_result(monkeypatch, domain_result(status))
    assert payload["success"] is True
    assert payload["context"]["assigned"] is (status in {"assigned", "unchanged"})
    assert declared_tool()["output_schema"] == UI_TEXTURE_OUTPUT_SCHEMA
    jsonschema.validate(payload, declared_tool()["output_schema"])
    if use_sdk:
        check_sdk(payload, declared_tool()["output_schema"])


@pytest.mark.parametrize("use_sdk", SDK_CASES)
def test_core_pruned_script_envelope_also_passes_contract(monkeypatch, use_sdk):
    payload = ToolResultEnvelope.from_dict(core_result(monkeypatch, ASSIGNED)).to_dict()
    assert "error" not in payload and "prompt" not in payload
    jsonschema.validate(payload, declared_tool()["output_schema"])
    if use_sdk:
        check_sdk(payload, declared_tool()["output_schema"])


@pytest.mark.parametrize(
    "defect",
    [
        "flat",
        "missing_context",
        "null_context",
        "pending_success",
        "null_resource",
        "extra_context",
        "failure_claims_assignment",
        "outer_failure",
        "outer_error",
    ],
)
@pytest.mark.parametrize("use_sdk", SDK_CASES)
def test_invalid_envelopes_fail_declared_contract(monkeypatch, defect, use_sdk):
    payload = core_result(monkeypatch, ASSIGNED)
    if defect == "flat":
        payload = payload["context"]
    elif defect == "missing_context":
        del payload["context"]
    elif defect == "null_context":
        payload["context"] = None
    elif defect == "pending_success":
        payload["context"]["status"] = "import_pending"
    elif defect == "null_resource":
        payload["context"]["resource_path"] = None
    elif defect == "extra_context":
        payload["context"]["unexpected"] = True
    elif defect == "failure_claims_assignment":
        payload["context"] = {"assigned": True, "status": "rejected", "reason": "failed"}
    elif defect == "outer_failure":
        payload["success"] = False
    else:
        payload["error"] = "unexpected"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, declared_tool()["output_schema"])

    if use_sdk:
        check_sdk(payload, declared_tool()["output_schema"], expect_invalid=True)


@pytest.mark.parametrize("use_sdk", SDK_CASES)
def test_previous_flat_schema_rejects_actual_core_envelope(monkeypatch, use_sdk):
    payload = core_result(monkeypatch, ASSIGNED)

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, UI_TEXTURE_CONTEXT_SCHEMA)
    if use_sdk:
        # This is the former advertised root schema, preserved unchanged as
        # the inner context contract. It rejects the actual Core envelope.
        check_sdk(payload, UI_TEXTURE_CONTEXT_SCHEMA, expect_invalid=True)
