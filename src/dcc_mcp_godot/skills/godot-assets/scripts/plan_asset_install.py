from typing import Any, Optional

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


@skill_entry
def main(
    package: dict[str, Any], destination: Optional[str] = None, **_kwargs: Any
) -> dict[str, Any]:
    try:
        from dcc_mcp_godot.asset_packages import plan_asset_install
        from dcc_mcp_godot.bridge import call_host

        project = call_host("project.inspect")
        plan = plan_asset_install(package, str(project["project_path"]), destination)
        return skill_success("Godot asset installation planned.", **plan)
    except Exception as exc:
        return skill_exception(exc, message="Failed to plan Godot asset installation")


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
