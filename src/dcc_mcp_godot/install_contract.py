"""Thin Install SOP v1 contract compatible with the pending shared Core export."""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path
from typing import Any

from .__version__ import __version__

try:
    from dcc_mcp_core.deployment.install_sop import (
        INSTALL_EXIT_INSTALL,
        INSTALL_EXIT_OK,
        INSTALL_EXIT_PREFLIGHT,
        INSTALL_EXIT_REQUIRES_RESTART,
        INSTALL_EXIT_VERIFY,
        INSTALL_SOP_SCHEMA_VERSION,
    )
except ImportError:  # Remove after dcc-mcp-core#2320 is the minimum supported Core.
    INSTALL_EXIT_INSTALL = 30
    INSTALL_EXIT_OK = 0
    INSTALL_EXIT_PREFLIGHT = 10
    INSTALL_EXIT_REQUIRES_RESTART = 50
    INSTALL_EXIT_VERIFY = 40
    INSTALL_SOP_SCHEMA_VERSION = 1


def core_version() -> str:
    try:
        return importlib.metadata.version("dcc-mcp-core")
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def version_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?", value)
    if match is None:
        return None
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def plan_result(project: Path) -> dict[str, Any]:
    destination = project.resolve() / "addons" / "dcc_mcp_godot"
    return {
        "schema_version": INSTALL_SOP_SCHEMA_VERSION,
        "status": "planned",
        "dcc_type": "godot",
        "adapter_version": __version__,
        "core_version": core_version(),
        "steps": [
            {"id": "preflight", "status": "planned"},
            {
                "id": "install_addon",
                "status": "planned",
                "description": f"Stage the Godot addon at {destination}",
            },
            {"id": "enable_plugin", "status": "planned"},
            {"id": "verify", "status": "planned"},
        ],
        "next_steps": [],
        "receipt_path": str(project.resolve() / ".dcc-mcp" / "receipts" / "godot.json"),
        "verify": {
            "directly_usable": False,
            "failure_stage": "verify",
            "failure_reason": "dry_run",
        },
    }


__all__ = [
    "INSTALL_EXIT_INSTALL",
    "INSTALL_EXIT_OK",
    "INSTALL_EXIT_PREFLIGHT",
    "INSTALL_EXIT_REQUIRES_RESTART",
    "INSTALL_EXIT_VERIFY",
    "INSTALL_SOP_SCHEMA_VERSION",
    "core_version",
    "plan_result",
    "version_tuple",
]
