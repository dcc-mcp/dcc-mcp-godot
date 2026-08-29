import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
GENERATOR_PATH = ROOT / "tools" / "generate_capability_skills.py"
GENERATOR_SPEC = importlib.util.spec_from_file_location(
    "dcc_mcp_godot_capability_skill_generator", GENERATOR_PATH
)
assert GENERATOR_SPEC is not None and GENERATOR_SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(GENERATOR_SPEC)
GENERATOR_SPEC.loader.exec_module(GENERATOR)


def _tool_block(skill_name: str, action_name: str) -> str:
    text = (ROOT / "src" / "dcc_mcp_godot" / "skills" / skill_name / "tools.yaml").read_text(
        encoding="utf-8"
    )
    tool = re.search(
        rf"(?ms)^  - name: {re.escape(action_name)}\n(?P<body>.*?)(?=^  - name: |\Z)", text
    )
    assert tool is not None
    return tool.group("body")


def _affinity(skill_name: str, action_name: str) -> str:
    affinity = re.search(
        r"(?m)^    affinity: (?P<value>\w+)$", _tool_block(skill_name, action_name)
    )
    assert affinity is not None
    return affinity.group("value")


def test_same_path_screenshot_concurrency_and_cancel_resume_use_serial_main_lane() -> None:
    # Core's enforced sync/main lane is the ordering and cancellation boundary:
    # a later same-path publisher cannot pass an older running request.
    manifest = _tool_block("godot-editor", "get_game_screenshot")
    assert "\n    execution: sync\n" in manifest
    assert "\n    affinity: main\n" in manifest
    assert "\n    enforce_thread_affinity: true\n" in manifest
    generated = GENERATOR._tool_yaml(
        "editor", "get_game_screenshot", "Publish one immutable screenshot snapshot."
    )
    assert "\n    affinity: main\n" in generated


def test_remote_bridge_polling_tools_do_not_hold_the_adapter_main_affinity_lane() -> None:
    for action_name in (
        "get_runtime_status",
        "get_game_scene_tree",
        "get_game_node_properties",
        "find_ui_elements",
    ):
        assert _affinity("godot-runtime", action_name) == "any"
        generated = GENERATOR._tool_yaml("runtime", action_name, "Measured remote bridge read.")
        assert "\n    affinity: any\n" in generated


def test_budgeted_builtin_schemas_expose_a_fail_closed_time_contract() -> None:
    for action_name in (
        "get_runtime_status",
        "get_game_scene_tree",
        "get_game_node_properties",
        "find_ui_elements",
    ):
        block = _tool_block("godot-runtime", action_name)
        assert '"budget_ms":{"type":"integer","minimum":1,"maximum":50}' in block
        assert '"max_nodes":{"type":"integer","minimum":1,"maximum":128}' in block

    editor_block = _tool_block("godot-editor", "get_editor_screenshot")
    assert '"budget_ms":{"type":"integer","minimum":1,"maximum":50}' in editor_block


def test_godot_host_keeps_png_encoding_off_the_editor_and_runtime_threads() -> None:
    capabilities = (
        ROOT / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot/capabilities.gd"
    ).read_text(encoding="utf-8")
    editor_screenshot = capabilities.split("func _get_editor_screenshot", 1)[1].split(
        "func _execute_editor_script", 1
    )[0]
    assert "__raw_snapshot__" in editor_screenshot
    assert "save_png" not in editor_screenshot
    assert "make_dir_recursive_absolute" in editor_screenshot

    runtime = (
        ROOT / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot/runtime_peer.gd"
    ).read_text(encoding="utf-8")
    capture_frames = runtime.split("func _capture_frames", 1)[1].split(
        "func _monitor_properties", 1
    )[0]
    assert "__raw_snapshots__" in capture_frames
    assert "save_png" not in capture_frames
    assert "budget_exceeded" in capture_frames
    assert "_cleanup_screenshot_snapshots(snapshots)" in capture_frames
