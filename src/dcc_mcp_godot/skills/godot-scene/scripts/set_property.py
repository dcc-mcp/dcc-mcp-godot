from typing import Any

from dcc_mcp_core.skill import skill_entry, skill_success

from dcc_mcp_godot.bridge import call_host


@skill_entry
def main(node_path: str, property: str, value: Any, **_kwargs):
    result = call_host(
        "scene.set_property", {"node_path": node_path, "property": property, "value": value}
    )
    return skill_success(f"Updated {node_path}.{property}.", **result)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
