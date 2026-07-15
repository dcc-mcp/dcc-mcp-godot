from typing import Any

from dcc_mcp_core.skill import skill_entry, skill_exception, skill_success


@skill_entry
def main(plugin_name: str, enabled: bool, **_kwargs: Any) -> dict[str, Any]:
    try:
        from dcc_mcp_godot.bridge import call_host

        result = call_host(
            "assets.set_plugin_enabled",
            {"plugin_name": plugin_name, "enabled": enabled},
        )
        return skill_success("Godot plugin state updated.", **result)
    except Exception as exc:
        return skill_exception(exc, message="Failed to update Godot plugin state")


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
