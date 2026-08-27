import re
from pathlib import Path

from tools.generate_capability_skills import _tool_yaml

ROOT = Path(__file__).parents[1]


def _affinity(skill_name: str, action_name: str) -> str:
    text = (ROOT / "src" / "dcc_mcp_godot" / "skills" / skill_name / "tools.yaml").read_text(
        encoding="utf-8"
    )
    tool = re.search(
        rf"(?ms)^  - name: {re.escape(action_name)}\n(?P<body>.*?)(?=^  - name: |\Z)", text
    )
    assert tool is not None
    affinity = re.search(r"(?m)^    affinity: (?P<value>\w+)$", tool.group("body"))
    assert affinity is not None
    return affinity.group("value")


def test_remote_bridge_read_tools_do_not_hold_the_adapter_main_affinity_lane() -> None:
    measured_tools = {
        "godot-editor": ["get_game_screenshot"],
        "godot-runtime": [
            "get_runtime_status",
            "get_game_scene_tree",
            "get_game_node_properties",
            "find_ui_elements",
        ],
    }

    for skill_name, action_names in measured_tools.items():
        for action_name in action_names:
            assert _affinity(skill_name, action_name) == "any"
            generated = _tool_yaml(
                skill_name.removeprefix("godot-"), action_name, "Measured remote bridge read."
            )
            assert "\n    affinity: any\n" in generated
