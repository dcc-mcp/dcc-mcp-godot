from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_success

from .dispatch import inspect_camera


@skill_entry
def main(**params):
    return skill_success("Phantom Camera inspection completed.", **inspect_camera(params))
