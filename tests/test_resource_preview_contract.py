"""Host-free manifest/envelope contracts; not native preview-worker acceptance."""

from __future__ import annotations

import copy
import runpy
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema
import yaml
from dcc_mcp_core.result_envelope import ToolResultEnvelope
from dcc_mcp_core.skill import skill_success

ROOT = Path(__file__).parents[1]
GEN = runpy.run_path(str(ROOT / "tools/generate_capability_skills.py"))
TOOL_NAME = "get_resource_preview"


def declared_tool():
    path = ROOT / "src/dcc_mcp_godot/skills/godot-resource/tools.yaml"
    return next(t for t in yaml.safe_load(path.read_text())["tools"] if t["name"] == TOOL_NAME)


def receipt(available):
    if available:
        return {
            "path": "res://fixture.png",
            "available": True,
            "preview_path": "res://.dcc-mcp/previews/fixture.png",
            "width": 2,
            "height": 2,
        }
    return {"path": "res://fixture.png", "available": False, "reason": "Headless worker disabled"}


def envelope(available, pruned=False):
    result = skill_success("Godot action get_resource_preview completed.", **receipt(available))
    return ToolResultEnvelope.from_dict(result).to_dict() if pruned else result


class ResourcePreviewContracts(unittest.TestCase):
    def test_generator_and_committed_resource_artifacts_match(self):
        with tempfile.TemporaryDirectory() as temp:
            generate = GEN["generate"]
            old_root = generate.__globals__["ROOT"]
            try:
                generate.__globals__["ROOT"] = Path(temp)
                generate()
            finally:
                generate.__globals__["ROOT"] = old_root
            for name in ["SKILL.md", "tools.yaml", "scripts/dispatch.py"]:
                expected = ROOT / "src/dcc_mcp_godot/skills/godot-resource" / name
                self.assertEqual(
                    (Path(temp) / "godot-resource" / name).read_bytes(), expected.read_bytes()
                )

    def test_declared_schema_matches_generator_constant(self):
        self.assertEqual(declared_tool()["output_schema"], GEN["RESOURCE_PREVIEW_OUTPUT_SCHEMA"])
        self.assertEqual(
            declared_tool()["input_schema"]["properties"], GEN["CATEGORY_PROPERTIES"]["resource"]
        )

    def test_real_core_envelopes_accept_available_and_unavailable(self):
        for available in [False, True]:
            for pruned in [False, True]:
                with self.subTest(available=available, pruned=pruned):
                    jsonschema.validate(
                        envelope(available, pruned), declared_tool()["output_schema"]
                    )

    def test_bare_receipt_and_false_image_evidence_are_rejected(self):
        schema = declared_tool()["output_schema"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(receipt(True), schema)
        for mutation in ["missing_path", "missing_dimensions", "stale_path", "zero_dimension"]:
            payload = envelope(mutation != "stale_path")
            context = payload["context"]
            if mutation == "missing_path":
                context.pop("preview_path")
            elif mutation == "missing_dimensions":
                context.pop("width")
            elif mutation == "stale_path":
                context["preview_path"] = "res://old.png"
            else:
                context["width"] = 0
            with self.subTest(mutation=mutation), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(payload, schema)

    @unittest.skipIf(sys.version_info < (3, 10), "MCP SDK requires Python 3.10+")
    def test_official_mcp_sdk_accepts_real_core_envelopes_once(self):
        import anyio
        from mcp import types
        from mcp.server import Server
        from mcp.shared.memory import create_connected_server_and_client_session

        async def check(payload):
            server = Server("resource-preview-output-contract")
            calls = []

            @server.list_tools()
            async def list_tools():
                tool = declared_tool()
                return [
                    types.Tool(
                        name=TOOL_NAME,
                        inputSchema=tool["input_schema"],
                        outputSchema=tool["output_schema"],
                    )
                ]

            @server.call_tool()
            async def call_tool(name, arguments):
                calls.append((name, arguments))
                return types.CallToolResult(content=[], structuredContent=payload, isError=False)

            with anyio.fail_after(5):
                async with create_connected_server_and_client_session(server) as session:
                    result = await session.call_tool(TOOL_NAME, {"path": "res://fixture.png"})
                    self.assertEqual(result.structuredContent, payload)
                    self.assertFalse(result.isError)
            self.assertEqual(calls, [(TOOL_NAME, {"path": "res://fixture.png"})])

        for available in [False, True]:
            for pruned in [False, True]:
                anyio.run(check, copy.deepcopy(envelope(available, pruned)))


if __name__ == "__main__":
    unittest.main()
