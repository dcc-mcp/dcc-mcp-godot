"""Project-owned filesystem transactions for the Godot addon lifecycle."""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from .__version__ import __version__

PLUGIN_PATH = "res://addons/dcc_mcp_godot/plugin.cfg"


def addon_source() -> Path:
    """Return the packaged addon directory."""
    return Path(__file__).resolve().parent / "godot_addon" / "addons" / "dcc_mcp_godot"


def install_addon(project: Path, *, overwrite: bool = False) -> Path:
    """Copy the EditorPlugin for the legacy install-only entry point."""
    project = project.resolve()
    if not (project / "project.godot").is_file():
        raise ValueError(f"Godot project file not found: {project / 'project.godot'}")
    destination = project / "addons" / "dcc_mcp_godot"
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Addon already exists: {destination}; pass --force to replace it")
    shutil.copytree(addon_source(), destination, dirs_exist_ok=overwrite)
    return destination


def enable_plugin(content: str) -> tuple[str, bool]:
    """Return project settings with the adapter plugin enabled exactly once."""
    if PLUGIN_PATH in content:
        return content, False
    newline = "\r\n" if "\r\n" in content else "\n"
    section = re.search(r"(?m)^\[editor_plugins\]\s*$", content)
    if section is None:
        prefix = content
        if prefix and not prefix.endswith(("\n", "\r")):
            prefix += newline
        return (
            f'{prefix}{newline}[editor_plugins]{newline}enabled=PackedStringArray("{PLUGIN_PATH}")'
            f"{newline}",
            True,
        )
    section_end = re.search(r"(?m)^\[", content[section.end() :])
    end = section.end() + section_end.start() if section_end else len(content)
    before, body, after = content[: section.end()], content[section.end() : end], content[end:]
    enabled = re.search(r"(?m)^enabled=PackedStringArray\((.*)\)\s*$", body)
    if enabled is None:
        body = f'{newline}enabled=PackedStringArray("{PLUGIN_PATH}"){body}'
    else:
        values = enabled.group(1).strip()
        replacement = f'enabled=PackedStringArray({values + ", " if values else ""}"{PLUGIN_PATH}")'
        body = body[: enabled.start()] + replacement + body[enabled.end() :]
    return before + body + after, True


def disable_plugin(content: str) -> str:
    """Remove only the adapter entry from Godot's enabled plugin list."""
    if PLUGIN_PATH not in content:
        return content
    enabled = re.search(r"(?m)^enabled=PackedStringArray\((.*)\)\s*$", content)
    if enabled is None:
        return content
    values = re.findall(r'"([^"]*)"', enabled.group(1))
    remaining = [value for value in values if value != PLUGIN_PATH]
    replacement = (
        "enabled=PackedStringArray(" + ", ".join(json.dumps(value) for value in remaining) + ")"
        if remaining
        else ""
    )
    updated = content[: enabled.start()] + replacement + content[enabled.end() :]
    return re.sub(r"(?m)^\[editor_plugins\]\s*\r?\n\s*(?=\[|\Z)", "", updated)


def atomic_write(path: Path, content: str) -> None:
    """Replace one text file only after its complete staged write succeeds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.stage-{uuid.uuid4().hex}")
    staged.write_text(content, encoding="utf-8")
    os.replace(staged, path)


def stage_addon(destination: Path) -> Path | None:
    """Swap a complete staged addon tree and retain the previous tree for rollback."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.parent / f".{destination.name}.stage-{uuid.uuid4().hex}"
    backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}"
    shutil.copytree(addon_source(), staged)
    had_destination = destination.exists()
    try:
        if had_destination:
            os.replace(destination, backup)
        os.replace(staged, destination)
    except OSError:
        shutil.rmtree(staged, ignore_errors=True)
        if had_destination and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    return backup if had_destination else None


def rollback_addon(destination: Path, backup: Path | None) -> None:
    """Restore the pre-transaction addon tree."""
    if destination.exists():
        shutil.rmtree(destination)
    if backup is not None and backup.exists():
        os.replace(backup, destination)


def receipt_path(project: Path) -> Path:
    return project / ".dcc-mcp" / "receipts" / "godot.json"


def write_receipt(
    project: Path,
    destination: Path,
    *,
    plugin_config_added: bool,
    godot: dict[str, Any],
    python: Path,
) -> Path:
    """Commit the bounded ownership receipt after project files commit."""
    target = receipt_path(project)
    files = [
        str(path.relative_to(project)).replace("\\", "/")
        for path in destination.rglob("*")
        if path.is_file()
    ]
    receipt = {
        "schema_version": 1,
        "dcc_type": "godot",
        "adapter_version": __version__,
        "destination": str(destination),
        "files": sorted(files),
        "plugin_config_added": plugin_config_added,
        "godot": {"path": godot["path"], "version": godot["version"]},
        "python": str(python.resolve()),
    }
    atomic_write(target, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return target


def inspect_install(project: Path) -> dict[str, Any]:
    """Classify absent, partial, and receipt-complete project installs."""
    project = project.resolve()
    project_file = project / "project.godot"
    destination = project / "addons" / "dcc_mcp_godot"
    target = receipt_path(project)
    marker_present = project_file.is_file() and PLUGIN_PATH in project_file.read_text(
        encoding="utf-8"
    )
    receipt: dict[str, Any] | None = None
    receipt_error: str | None = None
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or loaded.get("dcc_type") != "godot":
                raise ValueError("receipt does not belong to the Godot adapter")
            receipt = loaded
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            receipt_error = str(exc)
    recorded_files = receipt.get("files", []) if receipt is not None else []
    files_present = bool(recorded_files) and all(
        (project / str(relative)).is_file() for relative in recorded_files
    )
    addon_present = destination.is_dir() and (destination / "plugin.cfg").is_file()
    complete = receipt is not None and files_present and addon_present and marker_present
    any_present = target.exists() or destination.exists() or marker_present
    return {
        "install_state": "installed" if complete else ("partial" if any_present else "absent"),
        "receipt_path": str(target),
        "receipt": receipt,
        "receipt_error": receipt_error,
        "addon_present": addon_present,
        "plugin_enabled": marker_present,
        "files_present": files_present,
    }


__all__ = [
    "PLUGIN_PATH",
    "addon_source",
    "atomic_write",
    "disable_plugin",
    "enable_plugin",
    "inspect_install",
    "install_addon",
    "receipt_path",
    "rollback_addon",
    "stage_addon",
    "write_receipt",
]
