"""The generator must emit tool manifests the runtime loader can parse."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
GENERATOR_PATH = ROOT / "tools" / "generate_capability_skills.py"
GENERATOR_SPEC = importlib.util.spec_from_file_location(
    "dcc_mcp_godot_capability_skill_generator_contract", GENERATOR_PATH
)
assert GENERATOR_SPEC is not None and GENERATOR_SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(GENERATOR_SPEC)
GENERATOR_SPEC.loader.exec_module(GENERATOR)

VALIDATION_SUFFIX = "Parameters are validated again by the Godot host."


def _generated_tool(description: str) -> dict:
    manifest = "tools:\n" + GENERATOR._tool_yaml("editor", "get_editor_errors", description)
    return yaml.safe_load(manifest)["tools"][0]


def test_a_description_containing_a_colon_still_generates_a_parseable_manifest() -> None:
    # A bare plain scalar containing ": " is not valid YAML, and one bad
    # description makes the whole tools.yaml unparseable, which drops every
    # tool in the skill at load time. The generator serializes the description
    # so the catalog text is free to contain colons.
    description = "Render a frame. Requires a windowed host: no headless fallback."
    tool = _generated_tool(description)
    assert tool["description"].startswith(description)
    assert tool["description"].endswith(VALIDATION_SUFFIX)


def test_a_description_with_quotes_backslashes_and_newlines_round_trips() -> None:
    description = 'Quote " and backslash \\ and colon: space\nthen a new line'
    tool = _generated_tool(description)
    assert tool["description"] == f"{description} {VALIDATION_SUFFIX}"


def test_every_generated_tool_description_loads_without_losing_text() -> None:
    # Skills outside the generator's CATEGORIES (godot-export) are hand-written
    # and keep their own wording, so only assert over what the generator owns.
    generated = {f"godot-{category}" for category in GENERATOR.CATEGORIES}
    checked = 0
    for manifest_path in sorted((ROOT / "src" / "dcc_mcp_godot" / "skills").glob("*/tools.yaml")):
        if manifest_path.parent.name not in generated:
            continue
        tools = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))["tools"]
        assert tools
        for tool in tools:
            assert tool["description"].endswith(VALIDATION_SUFFIX)
            assert "\n" not in tool["description"]
            checked += 1
    assert checked > 100
