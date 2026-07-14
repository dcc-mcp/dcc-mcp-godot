from dcc_mcp_core.skill import skill_entry, skill_success

from dcc_mcp_godot.bridge import call_host


@skill_entry
def main(**_kwargs):
    return skill_success("Godot scene saved.", **call_host("scene.save"))


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
