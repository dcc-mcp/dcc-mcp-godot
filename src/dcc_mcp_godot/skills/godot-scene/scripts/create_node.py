from dcc_mcp_core.skill import skill_entry, skill_success

from dcc_mcp_godot.bridge import call_host


@skill_entry
def main(type: str, name: str, parent_path: str = "", **_kwargs):
    result = call_host(
        "scene.create_node", {"type": type, "name": name, "parent_path": parent_path}
    )
    return skill_success(f"Created Godot node {name}.", **result)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
