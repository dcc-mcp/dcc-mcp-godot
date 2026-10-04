"""Exercise typed Core results through the official SDK's output validator.

The observed native receipt shape is retained with synthetic identities and
resource paths. No Godot host, network listener, or SDK validator patch is used.
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
    TYPED_ACTION_CONTEXT_SCHEMA,
    TYPED_ACTION_OUTPUT_SCHEMA,
)

ROOT = Path(__file__).parents[1]
TOOL_NAME = "execute_typed_action"
TARGET = {
    "node_path": "/root/TestScene",
    "node_type": "Control",
    "property": "mode",
    "script_path": "res://scripts/target.gd",
    "script_sha256": "a" * 64,
}
PARAMS = {
    "project_id": "test-project",
    "session_id": "test-session",
    "runtime_id": "test-runtime",
    "authority_id": "test-owner",
    "manifest_id": "test-manifest",
    "manifest_digest": "b" * 64,
    "action": {
        "id": "set_mode",
        "kind": "set_property",
        "target": TARGET,
        "arguments": {"value": "success"},
    },
}
PROPERTY_RECEIPT = {
    "status": "applied",
    "schema_version": 1,
    "manifest_id": "test-manifest",
    "manifest_digest": "b" * 64,
    "action_id": "set_mode",
    "kind": "set_property",
    "target": TARGET,
    "readback": {
        "kind": "property",
        "node_path": "/root/TestScene",
        "node_type": "Control",
        "property": "mode",
        "value": "success",
        "script_sha256": "a" * 64,
    },
    "budget": {"limit": 16, "remaining": 15, "used": 1},
}
SDK_CASES = [
    False,
    pytest.param(
        True,
        marks=pytest.mark.skipif(
            sys.version_info < (3, 10), reason="MCP SDK requires Python 3.10+"
        ),
    ),
]


def declared_tool():
    inventory = yaml.safe_load(
        (ROOT / "src/dcc_mcp_godot/skills/godot-runtime/tools.yaml").read_text()
    )
    return next(tool for tool in inventory["tools"] if tool["name"] == TOOL_NAME)


def receipt_for(kind):
    receipt = copy.deepcopy(PROPERTY_RECEIPT)
    if kind == "input_action":
        receipt.update(
            action_id="press_accept",
            kind=kind,
            target={"action": "ui_accept"},
            readback={"kind": kind, "action": "ui_accept", "pressed": True, "strength": 1.0},
        )
    return receipt


def core_result(monkeypatch, receipt):
    monkeypatch.setattr(
        capability_dispatch, "_dispatch_typed_action", lambda _: copy.deepcopy(receipt)
    )
    return capability_dispatch.dispatch(TOOL_NAME, PARAMS)


def check_sdk(payload, output_schema, *, expect_invalid=False):
    import anyio
    from mcp import types
    from mcp.server import Server
    from mcp.shared.memory import create_connected_server_and_client_session

    async def check():
        server = Server("typed-action-output-contract")
        calls = []

        @server.list_tools()
        async def list_tools():
            return [
                types.Tool(
                    name=TOOL_NAME,
                    inputSchema=declared_tool()["input_schema"],
                    outputSchema=output_schema,
                )
            ]

        @server.call_tool()
        async def call_tool(name, arguments):
            calls.append((name, arguments))
            return types.CallToolResult(content=[], structuredContent=payload, isError=False)

        with anyio.fail_after(5):
            async with create_connected_server_and_client_session(server) as session:
                catalog = await session.list_tools()
                assert catalog.tools[0].outputSchema == output_schema
                if expect_invalid:
                    with pytest.raises(RuntimeError, match="Invalid structured content returned"):
                        await session.call_tool(TOOL_NAME, PARAMS)
                else:
                    result = await session.call_tool(TOOL_NAME, PARAMS)
                    assert result.structuredContent == payload
                    assert result.isError is False
                # Validation occurs after execution. Never replay a mutation
                # to recover from an output-schema mismatch.
                assert calls == [(TOOL_NAME, PARAMS)]

    anyio.run(check)


@pytest.mark.parametrize("kind", ["set_property", "input_action"])
@pytest.mark.parametrize("pruned", [False, True])
@pytest.mark.parametrize("use_sdk", SDK_CASES)
def test_core_typed_receipt_passes_declared_envelope(monkeypatch, kind, pruned, use_sdk):
    receipt = receipt_for(kind)
    payload = core_result(monkeypatch, receipt)
    assert payload == {
        "success": True,
        "message": "Godot action execute_typed_action completed.",
        "error": None,
        "prompt": None,
        "context": receipt,
    }
    if pruned:
        payload = ToolResultEnvelope.from_dict(payload).to_dict()
        assert "error" not in payload and "prompt" not in payload
    assert declared_tool()["output_schema"] == TYPED_ACTION_OUTPUT_SCHEMA
    jsonschema.validate(payload, declared_tool()["output_schema"])
    if use_sdk:
        check_sdk(payload, declared_tool()["output_schema"])


@pytest.mark.parametrize(
    "defect",
    [
        "flat",
        "missing_context",
        "null_context",
        "extra_context",
        "extra_outer",
        "outer_failure",
        "outer_error",
        "missing_readback",
        "bad_readback_hash",
        "extra_target",
        "bad_budget",
        "wrong_status",
    ],
)
@pytest.mark.parametrize("use_sdk", SDK_CASES)
def test_malformed_typed_envelope_is_rejected(monkeypatch, defect, use_sdk):
    payload = core_result(monkeypatch, PROPERTY_RECEIPT)
    if defect == "flat":
        payload = payload["context"]
    elif defect == "missing_context":
        del payload["context"]
    elif defect == "null_context":
        payload["context"] = None
    elif defect == "extra_context":
        payload["context"]["unexpected"] = True
    elif defect == "extra_outer":
        payload["unexpected"] = True
    elif defect == "outer_failure":
        payload["success"] = False
    elif defect == "outer_error":
        payload["error"] = "failed"
    elif defect == "missing_readback":
        del payload["context"]["readback"]
    elif defect == "bad_readback_hash":
        payload["context"]["readback"]["script_sha256"] = "wrong"
    elif defect == "extra_target":
        payload["context"]["target"]["method"] = "run"
    elif defect == "bad_budget":
        payload["context"]["budget"]["used"] = True
    else:
        payload["context"]["status"] = "pending"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, declared_tool()["output_schema"])
    if use_sdk:
        check_sdk(payload, declared_tool()["output_schema"], expect_invalid=True)


@pytest.mark.parametrize("use_sdk", SDK_CASES)
def test_previous_flat_contract_rejects_observed_core_shape(monkeypatch, use_sdk):
    payload = core_result(monkeypatch, PROPERTY_RECEIPT)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, TYPED_ACTION_CONTEXT_SCHEMA)
    if use_sdk:
        check_sdk(payload, TYPED_ACTION_CONTEXT_SCHEMA, expect_invalid=True)
