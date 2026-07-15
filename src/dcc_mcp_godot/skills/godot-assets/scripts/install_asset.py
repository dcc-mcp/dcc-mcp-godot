from typing import Any, Optional

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


@skill_entry
def main(
    package: dict[str, Any],
    destination: Optional[str] = None,
    overwrite: bool = False,
    **_kwargs: Any,
) -> dict[str, Any]:
    try:
        from dcc_mcp_godot.asset_packages import install_asset_package
        from dcc_mcp_godot.bridge import call_host

        project = call_host("project.inspect")
        result = install_asset_package(
            package,
            str(project["project_path"]),
            destination,
            overwrite,
        )
        call_host("assets.refresh")
        return skill_success("Godot asset package installed.", **result)
    except Exception as exc:
        return skill_exception(exc, message="Failed to install Godot asset package")


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
