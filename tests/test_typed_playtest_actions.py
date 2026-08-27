import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
GENERATOR_PATH = ROOT / "tools" / "generate_capability_skills.py"
GENERATOR_SPEC = importlib.util.spec_from_file_location(
    "dcc_mcp_godot_typed_action_generator", GENERATOR_PATH
)
assert GENERATOR_SPEC is not None and GENERATOR_SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(GENERATOR_SPEC)
GENERATOR_SPEC.loader.exec_module(GENERATOR)


def _tool_block(action_name: str) -> str:
    text = (ROOT / "src" / "dcc_mcp_godot" / "skills" / "godot-runtime" / "tools.yaml").read_text(
        encoding="utf-8"
    )
    match = re.search(
        rf"(?ms)^  - name: {re.escape(action_name)}\n(?P<body>.*?)(?=^  - name: |\Z)",
        text,
    )
    assert match is not None
    return match.group("body")


def _inline_schema(block: str, field: str) -> dict:
    match = re.search(rf"(?m)^    {re.escape(field)}: (?P<schema>.+)$", block)
    assert match is not None
    return json.loads(match.group("schema"))


def test_typed_action_schema_is_closed_discriminated_and_generated() -> None:
    description = dict(GENERATOR.CATEGORIES["runtime"])["execute_typed_action"]
    generated = GENERATOR._tool_yaml("runtime", "execute_typed_action", description)
    committed = _tool_block("execute_typed_action")
    input_schema = _inline_schema(committed, "input_schema")

    assert generated.split("\n", 1)[1] == committed
    assert input_schema["additionalProperties"] is False
    assert set(input_schema["required"]) == {
        "project_id",
        "session_id",
        "runtime_id",
        "authority_id",
        "manifest_id",
        "manifest_digest",
        "action",
    }
    assert "manifest_path" not in input_schema["properties"]
    action_schema = input_schema["properties"]["action"]
    branches = action_schema["oneOf"]
    assert {branch["properties"]["kind"]["const"] for branch in branches} == {
        "input_action",
        "set_property",
    }
    for branch in branches:
        assert branch["additionalProperties"] is False
        assert branch["properties"]["target"]["additionalProperties"] is False
        assert branch["properties"]["arguments"]["additionalProperties"] is False

    output_schema = _inline_schema(committed, "output_schema")
    assert output_schema["additionalProperties"] is False
    assert set(output_schema["required"]) == {
        "status",
        "schema_version",
        "manifest_id",
        "manifest_digest",
        "action_id",
        "kind",
        "target",
        "readback",
        "budget",
    }


def test_project_manifest_schema_is_closed_versioned_and_bounded() -> None:
    schema_path = (
        ROOT / "src" / "dcc_mcp_godot" / "schemas" / "playtest_actions_manifest_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["$id"].endswith("playtest-actions-manifest-v1.schema.json")
    assert schema["properties"]["schema_version"] == {"const": 1}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["actions"]["maxItems"] == 64
    assert schema["properties"]["authority"]["additionalProperties"] is False
    branches = schema["properties"]["actions"]["items"]["oneOf"]
    assert {branch["properties"]["kind"]["const"] for branch in branches} == {
        "input_action",
        "set_property",
    }
    assert all(branch["additionalProperties"] is False for branch in branches)
    input_branch = next(
        branch for branch in branches if branch["properties"]["kind"]["const"] == "input_action"
    )
    property_branch = next(
        branch for branch in branches if branch["properties"]["kind"]["const"] == "set_property"
    )
    assert input_branch["properties"]["arguments"]["properties"]["pressed"]["uniqueItems"]
    string_contract = property_branch["properties"]["arguments"]["properties"]["value"]["oneOf"][2]
    assert string_contract["properties"]["enum"]["uniqueItems"]


def test_runtime_enforces_identity_drift_manifest_links_and_main_thread() -> None:
    runtime = (
        ROOT
        / "src"
        / "dcc_mcp_godot"
        / "godot_addon"
        / "addons"
        / "dcc_mcp_godot"
        / "runtime_peer.gd"
    ).read_text(encoding="utf-8")
    body = runtime.split("func _execute_typed_action", 1)[1].split("\nfunc ", 1)[0]

    for required in (
        "TYPED_ACTION_MANIFEST_PATH",
        "FileAccess.get_sha256",
        "is_link",
        "OS.get_thread_caller_id()",
        "OS.get_main_thread_id()",
        "manifest_drift",
        "project_identity_mismatch",
        "session_identity_mismatch",
        "runtime_identity_mismatch",
        "authority_mismatch",
        "rate_limit_exceeded",
        "action_budget_exhausted",
    ):
        assert required in runtime
    assert "_call_node_method" not in body
    assert "callv" not in body


def test_bridge_exposes_only_the_cancellation_bound_typed_action_protocol() -> None:
    capabilities = (
        ROOT
        / "src"
        / "dcc_mcp_godot"
        / "godot_addon"
        / "addons"
        / "dcc_mcp_godot"
        / "capabilities.gd"
    ).read_text(encoding="utf-8")
    runtime_actions = capabilities.split("const RUNTIME_ACTIONS := [", 1)[1].split("]", 1)[0]

    assert '"execute_typed_action"' not in runtime_actions
    for phase in (
        "reserve_typed_action",
        "commit_typed_action",
        "finalize_typed_action",
        "rollback_typed_action",
    ):
        assert f'"{phase}"' in runtime_actions


def test_broad_method_tool_is_truthful_compatibility_only() -> None:
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").lower().split())
    skill = (
        (ROOT / "src" / "dcc_mcp_godot" / "skills" / "godot-runtime" / "SKILL.md")
        .read_text(encoding="utf-8")
        .lower()
    )
    broad_schema = _inline_schema(_tool_block("execute_game_script"), "input_schema")

    assert "execute_game_script is not an allowlist" in readme
    assert "compatibility-only" in skill
    assert "playtest" in skill and "execute_typed_action" in skill
    assert broad_schema["additionalProperties"] is False
    assert set(broad_schema["required"]) == {"node_path", "method", "arguments"}
