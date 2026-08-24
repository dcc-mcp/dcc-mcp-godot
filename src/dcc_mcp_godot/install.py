"""Install the packaged Godot EditorPlugin into a project."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence

from .install_contract import (
    INSTALL_EXIT_INSTALL,
    INSTALL_EXIT_OK,
    INSTALL_EXIT_PREFLIGHT,
    INSTALL_EXIT_REQUIRES_RESTART,
)
from .install_contract import (
    plan_result as _plan_result,
)
from .install_contract import (
    version_tuple as _version_tuple,
)
from .install_project import (
    PLUGIN_PATH as PLUGIN_PATH,
)
from .install_project import (
    addon_source as addon_source,
)
from .install_project import (
    atomic_write as _atomic_write,
)
from .install_project import (
    disable_plugin as _disable_plugin,
)
from .install_project import (
    enable_plugin as _enable_plugin,
)
from .install_project import (
    inspect_install as _inspect_install,
)
from .install_project import (
    install_addon as install_addon,
)
from .install_project import (
    receipt_path as _receipt_path,
)
from .install_project import (
    rollback_addon as _rollback_addon,
)
from .install_project import (
    stage_addon as _stage_addon,
)
from .install_project import (
    write_receipt as _write_receipt,
)
from .install_verify import verify as _run_verify

MIN_GODOT_VERSION = (4, 0, 0)
MIN_CORE_VERSION = (0, 19, 45)


def _probe_godot(path: Path) -> dict[str, Any]:
    executable = path.resolve()
    if not executable.is_file():
        raise ValueError(f"Godot executable not found: {executable}")
    completed = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    output = (completed.stdout or completed.stderr).strip()
    version = _version_tuple(output)
    if completed.returncode != 0 or version is None:
        raise ValueError("Godot version probe failed")
    if version < MIN_GODOT_VERSION:
        raise ValueError(f"Godot 4.0 or newer is required; found {output}")
    return {"path": str(executable), "version": output, "version_tuple": version}


def _probe_python(path: Path) -> dict[str, str]:
    completed = subprocess.run(
        [
            str(path),
            "-c",
            (
                "import importlib.metadata,json,sys; "
                "print(json.dumps({'python': '.'.join(map(str, sys.version_info[:3])), "
                "'core': importlib.metadata.version('dcc-mcp-core')}))"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Selected Python could not report its Core version") from exc
    python_version = _version_tuple(str(payload.get("python", "")))
    core_version = _version_tuple(str(payload.get("core", "")))
    if completed.returncode != 0 or python_version is None:
        raise ValueError("Selected Python version probe failed")
    if python_version < (3, 9, 0):
        raise ValueError(f"Python 3.9 or newer is required; found {payload['python']}")
    if core_version is None or core_version < MIN_CORE_VERSION:
        raise ValueError("dcc-mcp-core 0.19.45 or newer is required in the selected Python")
    return {"python": str(payload["python"]), "core": str(payload["core"])}


def _preflight_install(
    args: argparse.Namespace,
) -> tuple[Path, dict[str, Any], dict[str, str]]:
    project = args.project.resolve()
    if not (project / "project.godot").is_file():
        raise ValueError(f"Godot project file not found: {project / 'project.godot'}")
    python = args.python.resolve()
    if not python.is_file():
        raise ValueError(f"Python interpreter not found: {python}")
    python_info = _probe_python(python)
    if args.dcc_path is None:
        discovered = shutil.which("godot4") or shutil.which("godot")
        if discovered is None:
            raise ValueError("Godot executable was not found; pass --dcc-path")
        args.dcc_path = Path(discovered)
    return project, _probe_godot(args.dcc_path), python_info


def _run_install(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    try:
        project, godot, python_info = _preflight_install(args)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        result = _plan_result(args.project)
        result.update(status="failed")
        result["steps"][0] = {"id": "preflight", "status": "failed", "message": str(exc)}
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "preflight",
            "failure_reason": str(exc),
        }
        return INSTALL_EXIT_PREFLIGHT, result

    destination = project / "addons" / "dcc_mcp_godot"
    before = _inspect_install(project)["install_state"]
    install_mode = (
        "upgrade" if args.verb == "upgrade" else ("fresh" if before == "absent" else "repair")
    )
    project_file = project / "project.godot"
    original_config = project_file.read_text(encoding="utf-8")
    updated_config, config_added = _enable_plugin(original_config)
    backup: Path | None = None
    try:
        backup = _stage_addon(destination)
        if updated_config != original_config:
            _atomic_write(project_file, updated_config)
        receipt = _write_receipt(
            project,
            destination,
            plugin_config_added=config_added,
            godot=godot,
            python=args.python,
        )
    except OSError as exc:
        _atomic_write(project_file, original_config)
        _rollback_addon(destination, backup)
        result = _plan_result(project)
        result.update(status="requires_restart" if isinstance(exc, PermissionError) else "failed")
        result["steps"][1] = {"id": "install_addon", "status": "failed", "message": str(exc)}
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "install",
            "failure_reason": "files_locked" if isinstance(exc, PermissionError) else str(exc),
        }
        return (
            INSTALL_EXIT_REQUIRES_RESTART
            if isinstance(exc, PermissionError)
            else INSTALL_EXIT_INSTALL,
            result,
        )
    finally:
        if backup is not None and backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

    result = _plan_result(project)
    result.update(
        status="requires_restart",
        receipt_path=str(receipt),
        install_mode=install_mode,
        core_version=python_info["core"],
        host={"path": godot["path"], "version": godot["version"]},
    )
    result["steps"] = [
        {"id": "preflight", "status": "ok"},
        {"id": "install_addon", "status": "ok"},
        {"id": "enable_plugin", "status": "ok"},
        {"id": "verify", "status": "requires_restart"},
    ]
    result["next_steps"] = [
        {
            "id": "start_adapter",
            "description": "Start the Godot adapter service.",
            "command": ["dcc-mcp-godot", "serve"],
            "why": "The EditorPlugin connects to the adapter's loopback bridge.",
        },
        {
            "id": "start_godot",
            "description": "Start the Godot editor for this project, then run verify.",
            "command": [godot["path"], "--editor", "--path", str(project)],
            "why": "The installed EditorPlugin must load and connect before readiness can pass.",
        },
    ]
    result["verify"] = {
        "directly_usable": False,
        "failure_stage": "verify",
        "failure_reason": "restart_required",
    }
    return INSTALL_EXIT_REQUIRES_RESTART, result


def _run_status(project: Path) -> tuple[int, dict[str, Any]]:
    state = _inspect_install(project)
    result = _plan_result(project)
    result.update(
        status="ok" if state["install_state"] == "installed" else "partial",
        install_state=state["install_state"],
        receipt_path=state["receipt_path"],
    )
    result["steps"] = [
        {
            "id": "inspect",
            "status": "ok" if state["install_state"] == "installed" else "failed",
            "message": state["receipt_error"] or state["install_state"],
        }
    ]
    result["verify"] = {
        "directly_usable": False,
        "failure_stage": "verify",
        "failure_reason": "not_verified",
    }
    if state["install_state"] != "installed":
        result["next_steps"] = [
            {
                "id": "repair_install",
                "description": "Repair the project-local Godot addon installation.",
                "command": ["dcc-mcp-godot", "install", str(project), "--yes", "--json"],
                "why": "The receipt, addon files, and enabled plugin entry are not consistent.",
            }
        ]
        return INSTALL_EXIT_INSTALL, result
    return INSTALL_EXIT_OK, result


def _confirmation_required(project: Path) -> tuple[int, dict[str, Any]]:
    result = _plan_result(project)
    result.update(status="failed")
    result["steps"] = [
        {"id": "confirmation", "status": "failed", "message": "Pass --yes to mutate files."}
    ]
    result["verify"] = {
        "directly_usable": False,
        "failure_stage": "preflight",
        "failure_reason": "confirmation_required",
    }
    return INSTALL_EXIT_PREFLIGHT, result


def _run_uninstall(project: Path) -> tuple[int, dict[str, Any]]:
    project = project.resolve()
    state = _inspect_install(project)
    receipt = state["receipt"]
    destination = project / "addons" / "dcc_mcp_godot"
    if receipt is None or Path(str(receipt.get("destination", ""))).resolve() != destination:
        result = _plan_result(project)
        result.update(status="failed")
        result["steps"] = [
            {
                "id": "receipt",
                "status": "failed",
                "message": "A valid receipt for this project is required.",
            }
        ]
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "uninstall",
            "failure_reason": "missing_or_invalid_receipt",
        }
        return INSTALL_EXIT_INSTALL, result
    project_file = project / "project.godot"
    original_config = project_file.read_text(encoding="utf-8")
    updated_config = _disable_plugin(original_config)
    backup = destination.parent / f".{destination.name}.uninstall-{uuid.uuid4().hex}"
    moved = False
    try:
        if destination.exists():
            os.replace(destination, backup)
            moved = True
        if updated_config != original_config:
            _atomic_write(project_file, updated_config)
        _receipt_path(project).unlink()
    except OSError as exc:
        _atomic_write(project_file, original_config)
        if moved and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        result = _plan_result(project)
        result.update(status="requires_restart" if isinstance(exc, PermissionError) else "failed")
        result["steps"] = [{"id": "uninstall", "status": "failed", "message": str(exc)}]
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "uninstall",
            "failure_reason": "files_locked" if isinstance(exc, PermissionError) else str(exc),
        }
        return (
            INSTALL_EXIT_REQUIRES_RESTART
            if isinstance(exc, PermissionError)
            else INSTALL_EXIT_INSTALL,
            result,
        )
    if backup.exists():
        shutil.rmtree(backup)
    result = _plan_result(project)
    result.update(status="ok", receipt_path=None, install_state="absent")
    result["steps"] = [
        {"id": "receipt", "status": "ok"},
        {"id": "uninstall", "status": "ok"},
    ]
    result["verify"] = {
        "directly_usable": False,
        "failure_stage": "uninstalled",
        "failure_reason": "adapter_not_installed",
    }
    return INSTALL_EXIT_OK, result


def _standard_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verb", choices=("install", "status", "verify", "uninstall", "upgrade"))
    parser.add_argument("project", type=Path, help="Directory containing project.godot")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dcc-path", type=Path)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--instance-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the standard lifecycle CLI or the legacy addon installer."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {"install", "status", "verify", "uninstall", "upgrade"}:
        args = _standard_parser().parse_args(arguments)
        if args.verb in {"install", "upgrade", "uninstall"} and args.dry_run:
            result = _plan_result(args.project)
            result["steps"] = [
                {"id": "preflight", "status": "planned"},
                {"id": args.verb, "status": "planned"},
            ]
            print(json.dumps(result, sort_keys=True) if args.json else result)
            return INSTALL_EXIT_OK
        if args.verb in {"install", "upgrade", "uninstall"} and not args.yes:
            exit_code, result = _confirmation_required(args.project)
            print(json.dumps(result, sort_keys=True) if args.json else result)
            return exit_code
        if args.verb in {"install", "upgrade"}:
            exit_code, result = _run_install(args)
            print(json.dumps(result, sort_keys=True) if args.json else result)
            return exit_code
        if args.verb == "status":
            exit_code, result = _run_status(args.project)
            print(json.dumps(result, sort_keys=True) if args.json else result)
            return exit_code
        if args.verb == "verify":
            exit_code, result = _run_verify(args.project, args.instance_id)
            print(json.dumps(result, sort_keys=True) if args.json else result)
            return exit_code
        if args.verb == "uninstall":
            exit_code, result = _run_uninstall(args.project)
            print(json.dumps(result, sort_keys=True) if args.json else result)
            return exit_code

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="Directory containing project.godot")
    parser.add_argument(
        "--force", action="store_true", help="Replace an existing addon installation"
    )
    args = parser.parse_args(arguments)
    print(install_addon(args.project, overwrite=args.force))
    return INSTALL_EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
