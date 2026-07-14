"""Install the packaged Godot EditorPlugin into a project."""

from __future__ import annotations

import argparse
import shutil
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


def main() -> None:
    """Install the bundled addon from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="Directory containing project.godot")
    parser.add_argument(
        "--force", action="store_true", help="Replace an existing addon installation"
    )
    args = parser.parse_args()
    print(install_addon(args.project, overwrite=args.force))


if __name__ == "__main__":
    main()
