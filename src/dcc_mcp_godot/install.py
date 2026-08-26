"""Install the packaged Godot EditorPlugin into a project."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path


def addon_source() -> Path:
    """Return the packaged addon directory."""
    return Path(__file__).resolve().parent / "godot_addon" / "addons" / "dcc_mcp_godot"


def install_addon(project: Path, *, overwrite: bool = False) -> Path:
    """Copy the EditorPlugin into a Godot project and return its destination."""
    project = project.resolve()
    if not (project / "project.godot").is_file():
        raise ValueError(f"Godot project file not found: {project / 'project.godot'}")
    destination = project / "addons" / "dcc_mcp_godot"
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Addon already exists: {destination}; pass --force to replace it")
    shutil.copytree(addon_source(), destination, dirs_exist_ok=overwrite)
    return destination


def _install_plan(project: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "dcc_type": "godot",
        "operation": "install",
        "status": "planned",
        "project_path": str(project.resolve()),
        "verify": {"directly_usable": False},
        "next_steps": [],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Godot install lifecycle command line."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "install":
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("operation", choices=["install"])
        parser.add_argument("project", type=Path, help="Directory containing project.godot")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--yes", action="store_true")
        parser.add_argument("--json", action="store_true", dest="json_output")
        args = parser.parse_args(arguments)
        if not (args.project / "project.godot").is_file():
            raise ValueError(f"Godot project file not found: {args.project / 'project.godot'}")
        if args.dry_run:
            payload = _install_plan(args.project)
            print(json.dumps(payload, sort_keys=True) if args.json_output else payload)
            return 0

    legacy_parser = argparse.ArgumentParser(description=__doc__)
    legacy_parser.add_argument("project", type=Path, help="Directory containing project.godot")
    legacy_parser.add_argument(
        "--force", action="store_true", help="Replace an existing addon installation"
    )
    args = legacy_parser.parse_args(arguments)
    print(install_addon(args.project, overwrite=args.force))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
