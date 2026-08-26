"""Install the packaged Godot EditorPlugin into a project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
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
    INSTALL_EXIT_VERIFY,
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
from .install_project import ReceiptError
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
    read_project_settings as _read_project_settings,
)
from .install_project import (
    read_regular_bytes as _read_regular_bytes,
)
from .install_project import (
    receipt_path as _receipt_path,
)
from .install_project import (
    remove_empty_owned_directories as _remove_empty_owned_directories,
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
_CONFIG_BACKUP_MARKER = ".dcc-mcp-backup-"
_CONFIG_RECOVERY_SCHEMA_VERSION = 1
_CONFIG_RECOVERY_TYPE = "dcc-mcp-godot-config-recovery"
_CONFIG_RECOVERY_PHASE = "project_config_pending"
_CONFIG_PROVENANCE_SCHEMA_VERSION = 1
_CONFIG_PROVENANCE_TYPE = "dcc-mcp-godot-config-recovery-provenance"
_CONFIG_PROVENANCE_DIR = "config-recovery"


def _directory_identity(path: Path) -> tuple[int, int]:
    value = os.lstat(path)
    attributes = int(getattr(value, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    if stat.S_ISLNK(value.st_mode) or attributes & reparse_flag or not stat.S_ISDIR(value.st_mode):
        raise ReceiptError("owned_parent_changed")
    return value.st_dev, value.st_ino


def _capture_owned_parents(
    destination: Path, owned_files: Sequence[Path]
) -> dict[Path, tuple[int, int]]:
    parents = {destination}
    for owned in owned_files:
        parent = owned.parent
        while parent != destination:
            parents.add(parent)
            parent = parent.parent
    return {parent: _directory_identity(parent) for parent in parents}


def _assert_owned_parents(identities: dict[Path, tuple[int, int]]) -> None:
    if any(_directory_identity(path) != identity for path, identity in identities.items()):
        raise ReceiptError("owned_parent_changed")


def _config_backup_binding(project_file: Path, backup: Path) -> tuple[str, str]:
    prefix = f".{project_file.name}{_CONFIG_BACKUP_MARKER}"
    if backup.parent != project_file.parent or not backup.name.startswith(prefix):
        raise ReceiptError("config_recovery_name_invalid")
    suffix = backup.name[len(prefix) :]
    token, separator, claim = suffix.partition(".claim-")
    if len(token) != 32 or any(character not in "0123456789abcdef" for character in token):
        raise ReceiptError("config_recovery_name_invalid")
    if not separator:
        return token, "pending"
    if len(claim) != 32 or any(character not in "0123456789abcdef" for character in claim):
        raise ReceiptError("config_recovery_name_invalid")
    return token, "claim"


def _config_backup_paths(project_file: Path) -> list[Path]:
    backups = []
    for entry in project_file.parent.iterdir():
        try:
            _config_backup_binding(project_file, entry)
        except ReceiptError:
            continue
        backups.append(entry)
    return sorted(backups, key=lambda item: item.name)


def _config_backup_token(project_file: Path, backup: Path) -> str:
    return _config_backup_binding(project_file, backup)[0]


def _config_provenance_directory(project_file: Path, *, create: bool) -> Path:
    metadata = project_file.parent / ".dcc-mcp"
    recovery = metadata / _CONFIG_PROVENANCE_DIR
    for path in (metadata, recovery):
        if os.path.lexists(path):
            _directory_identity(path)
        elif create:
            path.mkdir()
            _directory_identity(path)
        else:
            break
    return recovery


def _config_provenance_path(project_file: Path, token: str, *, create: bool) -> Path:
    return _config_provenance_directory(project_file, create=create) / f"godot-{token}.json"


def _config_provenance_token(path: Path) -> str:
    prefix = "godot-"
    suffix = ".json"
    if not path.name.startswith(prefix) or not path.name.endswith(suffix):
        raise ReceiptError("config_provenance_name_invalid")
    token = path.name[len(prefix) : -len(suffix)]
    if len(token) != 32 or any(character not in "0123456789abcdef" for character in token):
        raise ReceiptError("config_provenance_name_invalid")
    return token


def _config_provenance_paths(project_file: Path) -> list[Path]:
    directory = _config_provenance_directory(project_file, create=False)
    if not os.path.lexists(directory):
        return []
    paths = []
    for entry in directory.iterdir():
        try:
            _config_provenance_token(entry)
        except ReceiptError:
            continue
        paths.append(entry)
    return sorted(paths, key=lambda item: item.name)


def _regular_file_identity(path: Path, code: str) -> tuple[int, int, int, int]:
    try:
        value = os.lstat(path)
    except OSError as exc:
        raise ReceiptError(code) from exc
    attributes = int(getattr(value, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    if stat.S_ISLNK(value.st_mode) or attributes & reparse_flag or not stat.S_ISREG(value.st_mode):
        raise ReceiptError(code)
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _capture_project_snapshot(project_file: Path) -> dict[str, Any]:
    before = _regular_file_identity(project_file, "project_settings_not_regular")
    content = _read_regular_bytes(project_file, "project_settings_not_regular")
    repeated = _read_regular_bytes(project_file, "project_settings_changed")
    after = _regular_file_identity(project_file, "project_settings_changed")
    if before != after or content != repeated:
        raise ReceiptError("project_settings_changed")
    return {"identity": before, "content": content, "sha256": _sha256_bytes(content)}


def _assert_project_snapshot(project_file: Path, expected: dict[str, Any]) -> dict[str, Any]:
    current = _capture_project_snapshot(project_file)
    if current["identity"] != expected["identity"] or current["content"] != expected["content"]:
        raise ReceiptError("project_settings_changed")
    return current


def _write_project_file(
    project_file: Path, content: str, expected: dict[str, Any]
) -> dict[str, Any]:
    _assert_project_snapshot(project_file, expected)
    _atomic_write(project_file, content)
    written = _capture_project_snapshot(project_file)
    if written["content"] != content.encode("utf-8"):
        raise ReceiptError("project_settings_write_mismatch")
    return written


def _load_config_provenance(
    project_file: Path,
    token: str,
    *,
    capsule: dict[str, Any] | None,
    path: Path | None = None,
) -> dict[str, Any]:
    provenance_path = path or _config_provenance_path(project_file, token, create=False)
    if _config_provenance_token(provenance_path) != token:
        raise ReceiptError("config_provenance_name_invalid")
    before = _regular_file_identity(provenance_path, "config_provenance_not_regular")
    encoded = _read_regular_bytes(provenance_path, "config_provenance_not_regular")
    repeated = _read_regular_bytes(provenance_path, "config_provenance_changed")
    after = _regular_file_identity(provenance_path, "config_provenance_changed")
    if before != after or encoded != repeated:
        raise ReceiptError("config_provenance_changed")
    try:
        payload = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptError("config_provenance_invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "type",
        "phase",
        "token",
        "project_identity",
        "project_file",
        "capsule_identity",
        "capsule_sha256",
        "final_project_sha256",
    }:
        raise ReceiptError("config_provenance_invalid")
    identity = payload.get("project_identity")
    capsule_identity = payload.get("capsule_identity")
    phase = payload.get("phase")
    final_digest = payload.get("final_project_sha256")
    if (
        payload.get("schema_version") != _CONFIG_PROVENANCE_SCHEMA_VERSION
        or isinstance(payload.get("schema_version"), bool)
        or payload.get("type") != _CONFIG_PROVENANCE_TYPE
        or phase not in {"pending", "cleanup"}
        or payload.get("token") != token
        or payload.get("project_file") != project_file.name
        or not isinstance(identity, dict)
        or set(identity) != {"device", "inode"}
        or any(isinstance(identity.get(key), bool) for key in ("device", "inode"))
        or any(not isinstance(identity.get(key), int) for key in ("device", "inode"))
        or not isinstance(capsule_identity, list)
        or len(capsule_identity) != 4
        or any(isinstance(value, bool) or not isinstance(value, int) for value in capsule_identity)
        or not isinstance(payload.get("capsule_sha256"), str)
        or (phase == "pending" and final_digest is not None)
        or (phase == "cleanup" and not isinstance(final_digest, str))
    ):
        raise ReceiptError("config_provenance_invalid")
    if (identity["device"], identity["inode"]) != _directory_identity(project_file.parent):
        raise ReceiptError("config_provenance_project_changed")
    capsule_digest = payload["capsule_sha256"]
    if len(capsule_digest) != 64 or any(
        character not in "0123456789abcdef" for character in capsule_digest
    ):
        raise ReceiptError("config_provenance_invalid")
    if final_digest is not None and (
        len(final_digest) != 64
        or any(character not in "0123456789abcdef" for character in final_digest)
    ):
        raise ReceiptError("config_provenance_invalid")
    if capsule is not None and (
        tuple(capsule_identity) != capsule["identity"]
        or capsule_digest != capsule["document_sha256"]
    ):
        raise ReceiptError("config_provenance_capsule_changed")
    return {
        "path": provenance_path,
        "identity": before,
        "document_sha256": _sha256_bytes(encoded),
        "payload": payload,
        "phase": phase,
        "final_project_sha256": final_digest,
    }


def _config_provenance_payload(
    project_file: Path,
    token: str,
    capsule: dict[str, Any],
    *,
    phase: str,
    final_project_sha256: str | None,
) -> dict[str, Any]:
    device, inode = _directory_identity(project_file.parent)
    return {
        "schema_version": _CONFIG_PROVENANCE_SCHEMA_VERSION,
        "type": _CONFIG_PROVENANCE_TYPE,
        "phase": phase,
        "token": token,
        "project_identity": {"device": device, "inode": inode},
        "project_file": project_file.name,
        "capsule_identity": list(capsule["identity"]),
        "capsule_sha256": capsule["document_sha256"],
        "final_project_sha256": final_project_sha256,
    }


def _stage_config_provenance(
    project_file: Path, token: str, capsule: dict[str, Any]
) -> dict[str, Any]:
    provenance = _config_provenance_path(project_file, token, create=True)
    if os.path.lexists(provenance):
        raise ReceiptError("config_provenance_exists")
    payload = _config_provenance_payload(
        project_file,
        token,
        capsule,
        phase="pending",
        final_project_sha256=None,
    )
    _atomic_write(provenance, json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return _load_config_provenance(project_file, token, capsule=capsule)


def _load_config_recovery(
    project_file: Path,
    backup: Path,
    *,
    expected_token: str | None = None,
    require_provenance: bool = True,
) -> dict[str, Any]:
    token = expected_token or _config_backup_token(project_file, backup)
    before = _regular_file_identity(backup, "config_backup_not_regular")
    encoded = _read_regular_bytes(backup, "config_backup_not_regular")
    repeated = _read_regular_bytes(backup, "config_backup_changed")
    after = _regular_file_identity(backup, "config_backup_changed")
    if before != after or encoded != repeated:
        raise ReceiptError("config_backup_changed")
    try:
        payload = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptError("config_recovery_invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "type",
        "phase",
        "token",
        "project_identity",
        "project_file",
        "backup",
        "updated_sha256",
    }:
        raise ReceiptError("config_recovery_invalid")
    identity = payload.get("project_identity")
    backup_record = payload.get("backup")
    if (
        payload.get("schema_version") != _CONFIG_RECOVERY_SCHEMA_VERSION
        or isinstance(payload.get("schema_version"), bool)
        or payload.get("type") != _CONFIG_RECOVERY_TYPE
        or payload.get("phase") != _CONFIG_RECOVERY_PHASE
        or payload.get("token") != token
        or payload.get("project_file") != project_file.name
        or not isinstance(identity, dict)
        or set(identity) != {"device", "inode"}
        or any(isinstance(identity.get(key), bool) for key in ("device", "inode"))
        or any(not isinstance(identity.get(key), int) for key in ("device", "inode"))
        or not isinstance(backup_record, dict)
        or set(backup_record) != {"content", "sha256"}
        or not isinstance(backup_record.get("content"), str)
        or not isinstance(backup_record.get("sha256"), str)
        or not isinstance(payload.get("updated_sha256"), str)
    ):
        raise ReceiptError("config_recovery_invalid")
    if (identity["device"], identity["inode"]) != _directory_identity(project_file.parent):
        raise ReceiptError("config_recovery_project_changed")
    original = backup_record["content"].encode("utf-8")
    if (
        len(backup_record["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in backup_record["sha256"])
        or _sha256_bytes(original) != backup_record["sha256"]
        or len(payload["updated_sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in payload["updated_sha256"])
    ):
        raise ReceiptError("config_recovery_digest_invalid")
    recovery = {
        "identity": before,
        "document_sha256": _sha256_bytes(encoded),
        "original": backup_record["content"],
        "original_sha256": backup_record["sha256"],
        "updated_sha256": payload["updated_sha256"],
    }
    if require_provenance:
        recovery["provenance"] = _load_config_provenance(project_file, token, capsule=recovery)
    return recovery


def _assert_config_recovery_unchanged(
    project_file: Path,
    backup: Path,
    expected: dict[str, Any],
    *,
    expected_token: str | None = None,
) -> None:
    current = _load_config_recovery(project_file, backup, expected_token=expected_token)
    if (
        current["identity"] != expected["identity"]
        or current["document_sha256"] != expected["document_sha256"]
    ):
        raise ReceiptError("config_backup_changed")
    current_provenance = current["provenance"]
    expected_provenance = expected["provenance"]
    if (
        current_provenance["identity"] != expected_provenance["identity"]
        or current_provenance["document_sha256"] != expected_provenance["document_sha256"]
    ):
        raise ReceiptError("config_provenance_changed")


def _mark_config_provenance_cleanup(
    project_file: Path,
    backup: Path,
    recovery: dict[str, Any],
    final_project_sha256: str,
    *,
    expected_token: str | None = None,
) -> dict[str, Any]:
    _assert_config_recovery_unchanged(project_file, backup, recovery, expected_token=expected_token)
    provenance = recovery["provenance"]
    if provenance["phase"] == "cleanup":
        if provenance["final_project_sha256"] != final_project_sha256:
            raise ReceiptError("config_provenance_project_changed")
        return recovery
    token = expected_token or _config_backup_token(project_file, backup)
    payload = _config_provenance_payload(
        project_file,
        token,
        recovery,
        phase="cleanup",
        final_project_sha256=final_project_sha256,
    )
    _atomic_write(provenance["path"], json.dumps(payload, sort_keys=True, separators=(",", ":")))
    updated = _load_config_recovery(project_file, backup, expected_token=expected_token)
    if updated["provenance"]["phase"] != "cleanup":
        raise ReceiptError("config_provenance_invalid")
    return updated


def _remove_config_provenance(
    project_file: Path,
    provenance: dict[str, Any],
    final_project_sha256: str,
) -> None:
    path = provenance["path"]
    token = _config_provenance_token(path)
    current = _load_config_provenance(project_file, token, capsule=None, path=path)
    if (
        current["identity"] != provenance["identity"]
        or current["document_sha256"] != provenance["document_sha256"]
        or current["phase"] != "cleanup"
        or current["final_project_sha256"] != final_project_sha256
    ):
        raise ReceiptError("config_provenance_changed")
    project_snapshot = _capture_project_snapshot(project_file)
    if project_snapshot["sha256"] != final_project_sha256:
        raise ReceiptError("config_provenance_project_changed")
    repeated = _load_config_provenance(project_file, token, capsule=None, path=path)
    if (
        repeated["identity"] != current["identity"]
        or repeated["document_sha256"] != current["document_sha256"]
    ):
        raise ReceiptError("config_provenance_changed")
    path.unlink()


def _remove_orphaned_config_provenance(project_file: Path, path: Path) -> None:
    token = _config_provenance_token(path)
    provenance = _load_config_provenance(project_file, token, capsule=None, path=path)
    if provenance["phase"] != "cleanup" or provenance["final_project_sha256"] is None:
        raise ReceiptError("config_provenance_orphaned")
    _remove_config_provenance(project_file, provenance, provenance["final_project_sha256"])


def _stage_config_backup(project_file: Path, original: str, updated: str) -> Path:
    token = uuid.uuid4().hex
    backup = project_file.with_name(f".{project_file.name}{_CONFIG_BACKUP_MARKER}{token}")
    device, inode = _directory_identity(project_file.parent)
    payload = {
        "schema_version": _CONFIG_RECOVERY_SCHEMA_VERSION,
        "type": _CONFIG_RECOVERY_TYPE,
        "phase": _CONFIG_RECOVERY_PHASE,
        "token": token,
        "project_identity": {"device": device, "inode": inode},
        "project_file": project_file.name,
        "backup": {
            "content": original,
            "sha256": _sha256_bytes(original.encode("utf-8")),
        },
        "updated_sha256": _sha256_bytes(updated.encode("utf-8")),
    }
    _atomic_write(backup, json.dumps(payload, sort_keys=True, separators=(",", ":")))
    capsule = _load_config_recovery(project_file, backup, require_provenance=False)
    _stage_config_provenance(project_file, token, capsule)
    _load_config_recovery(project_file, backup)
    return backup


def _restore_config_backup(
    project_file: Path, backup: Path, expected_project: dict[str, Any]
) -> None:
    recovery = _load_config_recovery(project_file, backup)
    current = _assert_project_snapshot(project_file, expected_project)
    current_digest = current["sha256"]
    if current_digest == recovery["updated_sha256"]:
        _write_project_file(project_file, recovery["original"], current)
    elif current_digest != recovery["original_sha256"]:
        raise ReceiptError("config_recovery_project_changed")
    _remove_config_backup(project_file, backup)


def _remove_config_backup(project_file: Path, backup: Path) -> None:
    recovery = _load_config_recovery(project_file, backup)
    _assert_config_recovery_unchanged(project_file, backup, recovery)
    current_digest = _capture_project_snapshot(project_file)["sha256"]
    if current_digest not in {
        recovery["original_sha256"],
        recovery["updated_sha256"],
    }:
        raise ReceiptError("config_recovery_project_changed")
    token = _config_backup_token(project_file, backup)
    recovery = _mark_config_provenance_cleanup(project_file, backup, recovery, current_digest)
    claimed = backup.with_name(f"{backup.name}.claim-{uuid.uuid4().hex}")
    os.replace(backup, claimed)
    try:
        claimed_recovery = _load_config_recovery(project_file, claimed, expected_token=token)
        if (
            claimed_recovery["identity"] != recovery["identity"]
            or claimed_recovery["document_sha256"] != recovery["document_sha256"]
        ):
            raise ReceiptError("config_backup_changed")
        _assert_config_recovery_unchanged(project_file, claimed, recovery, expected_token=token)
        claimed.unlink()
        _remove_config_provenance(project_file, claimed_recovery["provenance"], current_digest)
    except BaseException:
        try:
            if os.path.lexists(claimed) and not os.path.lexists(backup):
                os.replace(claimed, backup)
        except BaseException:
            pass
        raise


def _reclaim_config_backup(project_file: Path, backup: Path) -> Path:
    token, state = _config_backup_binding(project_file, backup)
    if state == "pending":
        return backup
    recovery = _load_config_recovery(project_file, backup, expected_token=token)
    pending = project_file.with_name(f".{project_file.name}{_CONFIG_BACKUP_MARKER}{token}")
    if os.path.lexists(pending):
        raise ReceiptError("config_backup_ambiguous")
    os.replace(backup, pending)
    try:
        _assert_config_recovery_unchanged(project_file, pending, recovery)
    except BaseException:
        try:
            if os.path.lexists(pending) and not os.path.lexists(backup):
                os.replace(pending, backup)
        except BaseException:
            pass
        raise
    return pending


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
    _read_project_settings(project / "project.godot")
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


def _run_dry_run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    """Run bounded preflight and ownership checks without mutating filesystem state."""
    if args.verb in {"install", "upgrade"}:
        try:
            project, godot, python_info = _preflight_install(args)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            result = _plan_result(args.project)
            result.update(status="failed")
            result["steps"] = [
                {
                    "id": "preflight",
                    "status": "failed",
                    "message": "Install preflight failed.",
                    "error_type": type(exc).__name__,
                }
            ]
            result["verify"] = {
                "directly_usable": False,
                "failure_stage": "preflight",
                "failure_reason": "preflight_failed",
            }
            return INSTALL_EXIT_PREFLIGHT, result
        state = _inspect_install(project)
        destination = project / "addons" / "dcc_mcp_godot"
        target_receipt = _receipt_path(project)
        if (os.path.lexists(destination) or os.path.lexists(target_receipt)) and not state[
            "ownership_valid"
        ]:
            result = _plan_result(project)
            result.update(status="failed", install_state=state["install_state"])
            result["steps"] = [
                {
                    "id": "ownership",
                    "status": "failed",
                    "message": "Existing addon ownership could not be validated.",
                }
            ]
            result["verify"] = {
                "directly_usable": False,
                "failure_stage": "install",
                "failure_reason": "ownership_conflict",
            }
            return INSTALL_EXIT_INSTALL, result
        result = _plan_result(project)
        result.update(
            install_mode="upgrade"
            if args.verb == "upgrade"
            else ("fresh" if state["install_state"] == "absent" else "repair"),
            core_version=python_info["core"],
            host={"path": godot["path"], "version": godot["version"]},
        )
        result["steps"] = [
            {"id": "preflight", "status": "ok"},
            {"id": "ownership", "status": "ok"},
            {"id": args.verb, "status": "planned"},
        ]
        return INSTALL_EXIT_OK, result

    project = args.project.resolve()
    state = _inspect_install(project)
    if state["receipt"] is None or not state["ownership_valid"]:
        result = _plan_result(project)
        result.update(status="failed", install_state=state["install_state"])
        result["steps"] = [
            {
                "id": "ownership",
                "status": "failed",
                "message": "A valid receipt for this project is required.",
            }
        ]
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "uninstall",
            "failure_reason": "ownership_conflict",
        }
        return INSTALL_EXIT_INSTALL, result
    result = _plan_result(project)
    result.update(install_state=state["install_state"])
    result["steps"] = [
        {"id": "preflight", "status": "ok"},
        {"id": "ownership", "status": "ok"},
        {"id": "uninstall", "status": "planned"},
    ]
    return INSTALL_EXIT_OK, result


def _run_install(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    try:
        project, godot, python_info = _preflight_install(args)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        result = _plan_result(args.project)
        result.update(status="failed")
        result["steps"][0] = {
            "id": "preflight",
            "status": "failed",
            "message": "Install preflight failed.",
            "error_type": type(exc).__name__,
        }
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "preflight",
            "failure_reason": "preflight_failed",
        }
        return INSTALL_EXIT_PREFLIGHT, result

    destination = project / "addons" / "dcc_mcp_godot"
    state = _inspect_install(project)
    project_file = project / "project.godot"
    config_backups = _config_backup_paths(project_file)
    config_provenances = _config_provenance_paths(project_file)
    backup_tokens = {_config_backup_token(project_file, path) for path in config_backups}
    provenance_tokens = {_config_provenance_token(path) for path in config_provenances}
    if (
        len(config_backups) > 1
        or len(config_provenances) > 1
        or (backup_tokens and provenance_tokens and backup_tokens != provenance_tokens)
    ):
        result = _plan_result(project)
        result.update(status="failed", install_state=state["install_state"])
        result["steps"][1] = {
            "id": "install_addon",
            "status": "failed",
            "message": "Project settings recovery state is ambiguous.",
        }
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "install",
            "failure_reason": "config_backup_ambiguous",
        }
        return INSTALL_EXIT_INSTALL, result
    if config_provenances and not config_backups:
        try:
            _remove_orphaned_config_provenance(project_file, config_provenances[0])
        except (OSError, ValueError) as exc:
            locked = isinstance(exc, PermissionError)
            result = _plan_result(project)
            result.update(
                status="requires_restart" if locked else "failed",
                install_state=state["install_state"],
            )
            result["steps"][1] = {
                "id": "install_addon",
                "status": "failed",
                "message": "Project settings recovery is still pending.",
                "error_type": type(exc).__name__,
            }
            result["verify"] = {
                "directly_usable": False,
                "failure_stage": "install",
                "failure_reason": (
                    "config_recovery_locked" if locked else "config_recovery_failed"
                ),
            }
            return (
                INSTALL_EXIT_REQUIRES_RESTART if locked else INSTALL_EXIT_INSTALL,
                result,
            )
        state = _inspect_install(project)
    if config_backups:
        pending_config = config_backups[0]
        try:
            pending_config = _reclaim_config_backup(project_file, pending_config)
            recovery = _load_config_recovery(project_file, pending_config)
            current_snapshot = _capture_project_snapshot(project_file)
            current_digest = current_snapshot["sha256"]
            if current_digest not in {
                recovery["original_sha256"],
                recovery["updated_sha256"],
            }:
                raise ReceiptError("config_recovery_project_changed")
            if state["install_state"] == "installed" and state["ownership_valid"]:
                if current_digest != recovery["updated_sha256"]:
                    raise ReceiptError("config_recovery_state_mismatch")
                _remove_config_backup(project_file, pending_config)
            elif current_digest == recovery["original_sha256"]:
                _remove_config_backup(project_file, pending_config)
            else:
                _restore_config_backup(project_file, pending_config, current_snapshot)
        except (OSError, ValueError) as exc:
            locked = isinstance(exc, PermissionError)
            result = _plan_result(project)
            result.update(
                status="requires_restart" if locked else "failed",
                install_state=state["install_state"],
            )
            result["steps"][1] = {
                "id": "install_addon",
                "status": "failed",
                "message": "Project settings recovery is still pending.",
                "error_type": type(exc).__name__,
            }
            result["verify"] = {
                "directly_usable": False,
                "failure_stage": "install",
                "failure_reason": "config_recovery_locked" if locked else "config_recovery_failed",
            }
            return (
                INSTALL_EXIT_REQUIRES_RESTART if locked else INSTALL_EXIT_INSTALL,
                result,
            )
        state = _inspect_install(project)
    before = state["install_state"]
    previous_receipt = _receipt_path(project)
    if (os.path.lexists(destination) or os.path.lexists(previous_receipt)) and not state[
        "ownership_valid"
    ]:
        result = _plan_result(project)
        result.update(status="failed", install_state=before)
        result["steps"][1] = {
            "id": "install_addon",
            "status": "failed",
            "message": "Existing addon ownership could not be validated.",
        }
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "install",
            "failure_reason": "ownership_conflict",
        }
        return INSTALL_EXIT_INSTALL, result
    install_mode = (
        "upgrade" if args.verb == "upgrade" else ("fresh" if before == "absent" else "repair")
    )
    original_snapshot = _capture_project_snapshot(project_file)
    try:
        original_config = original_snapshot["content"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReceiptError("project_file_unreadable") from exc
    updated_config, config_action = _enable_plugin(original_config)
    previous_receipt_bytes = (
        _read_regular_bytes(previous_receipt, "receipt_not_regular")
        if os.path.lexists(previous_receipt)
        else None
    )
    backup: Path | None = None
    config_backup: Path | None = None
    applied_config_snapshot: dict[str, Any] | None = None
    staged = False
    try:
        backup = _stage_addon(destination, state["owned_files"])
        staged = True
        if updated_config != original_config:
            config_backup = _stage_config_backup(project_file, original_config, updated_config)
            applied_config_snapshot = _write_project_file(
                project_file, updated_config, original_snapshot
            )
            if not _inspect_install(project)["plugin_enabled"]:
                raise OSError("project settings readback failed")
        receipt = _write_receipt(
            project,
            destination,
            plugin_config_action=config_action,
            godot=godot,
            python=args.python,
        )
        installed = _inspect_install(project)
        if installed["install_state"] != "installed" or installed["receipt"] is None:
            raise ReceiptError("install_readback_failed")
    except (OSError, ValueError) as exc:
        rollback_errors: list[str] = []
        rollback_locked = False
        if config_backup is not None:
            try:
                _restore_config_backup(
                    project_file,
                    config_backup,
                    applied_config_snapshot or original_snapshot,
                )
            except BaseException as rollback_exc:
                rollback_errors.append(type(rollback_exc).__name__)
                rollback_locked = rollback_locked or isinstance(rollback_exc, PermissionError)
        if staged:
            try:
                _rollback_addon(destination, backup)
            except BaseException as rollback_exc:
                rollback_errors.append(type(rollback_exc).__name__)
                rollback_locked = rollback_locked or isinstance(rollback_exc, PermissionError)
        try:
            if previous_receipt_bytes is None:
                previous_receipt.unlink(missing_ok=True)
            else:
                _atomic_write(previous_receipt, previous_receipt_bytes.decode("utf-8"))
        except BaseException as rollback_exc:
            rollback_errors.append(type(rollback_exc).__name__)
            rollback_locked = rollback_locked or isinstance(rollback_exc, PermissionError)
        result = _plan_result(project)
        locked = isinstance(exc, PermissionError) or rollback_locked
        reason = (
            "rollback_locked"
            if rollback_locked
            else "rollback_incomplete"
            if rollback_errors
            else ("files_locked" if locked else "filesystem_error")
        )
        result.update(status="requires_restart" if locked else "failed")
        result["steps"][1] = {
            "id": "install_addon",
            "status": "failed",
            "message": "Install transaction did not commit.",
            "error_type": type(exc).__name__,
            "rollback": (
                "deferred" if rollback_locked else ("incomplete" if rollback_errors else "restored")
            ),
        }
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "install",
            "failure_reason": reason,
        }
        return (
            INSTALL_EXIT_REQUIRES_RESTART if locked else INSTALL_EXIT_INSTALL,
            result,
        )

    if config_backup is not None:
        try:
            _remove_config_backup(project_file, config_backup)
        except OSError as exc:
            result = _plan_result(project)
            result.update(
                status="requires_restart",
                receipt_path=str(receipt),
                install_state="installed",
                install_mode=install_mode,
                core_version=python_info["core"],
                host={"path": godot["path"], "version": godot["version"]},
            )
            result["steps"] = [
                {"id": "preflight", "status": "ok"},
                {"id": "install_addon", "status": "ok"},
                {"id": "enable_plugin", "status": "ok"},
                {
                    "id": "cleanup_backup",
                    "status": "requires_restart",
                    "message": "Committed project settings cleanup is deferred.",
                    "error_type": type(exc).__name__,
                },
            ]
            result["verify"] = {
                "directly_usable": False,
                "failure_stage": "install_cleanup",
                "failure_reason": "cleanup_locked",
            }
            return INSTALL_EXIT_REQUIRES_RESTART, result

    if backup is not None:
        try:
            shutil.rmtree(backup)
        except OSError as exc:
            result = _plan_result(project)
            result.update(
                status="requires_restart",
                receipt_path=str(receipt),
                install_state="installed",
                install_mode=install_mode,
                core_version=python_info["core"],
                host={"path": godot["path"], "version": godot["version"]},
            )
            result["steps"] = [
                {"id": "preflight", "status": "ok"},
                {"id": "install_addon", "status": "ok"},
                {"id": "enable_plugin", "status": "ok"},
                {
                    "id": "cleanup_backup",
                    "status": "requires_restart",
                    "message": "Committed install cleanup is deferred.",
                    "error_type": type(exc).__name__,
                },
            ]
            result["verify"] = {
                "directly_usable": False,
                "failure_stage": "install_cleanup",
                "failure_reason": "cleanup_locked",
            }
            return INSTALL_EXIT_REQUIRES_RESTART, result

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
    owned_files: list[Path] = state["owned_files"]
    if receipt is None or not state["ownership_valid"] or not owned_files:
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
    original_config = _read_project_settings(project_file)
    updated_config = _disable_plugin(original_config, receipt["plugin_config_action"])
    target_receipt = _receipt_path(project)
    receipt_bytes = _read_regular_bytes(target_receipt, "receipt_not_regular")
    parent_identities = _capture_owned_parents(destination, owned_files)
    backup = destination.parent / f".{destination.name}.uninstall-{uuid.uuid4().hex}"
    moved: list[tuple[Path, Path]] = []
    receipt_backup = backup / "receipt" / "godot.json"
    try:
        backup.mkdir(parents=False)
        receipt_entries = {entry["path"]: entry["sha256"] for entry in receipt["owned_files"]}
        for owned in owned_files:
            _assert_owned_parents(parent_identities)
            relative = owned.relative_to(destination)
            staged = backup / "owned" / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            os.replace(owned, staged)
            moved.append((staged, owned))
            value = os.lstat(staged)
            attributes = int(getattr(value, "st_file_attributes", 0))
            reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
            if (
                stat.S_ISLNK(value.st_mode)
                or attributes & reparse_flag
                or not stat.S_ISREG(value.st_mode)
            ):
                raise ReceiptError("owned_file_changed_during_uninstall")
            digest = hashlib.sha256(
                _read_regular_bytes(staged, "owned_file_changed_during_uninstall")
            ).hexdigest()
            if digest != receipt_entries[owned.relative_to(project).as_posix()]:
                raise ReceiptError("owned_file_changed_during_uninstall")
            _assert_owned_parents(parent_identities)
        if updated_config != original_config:
            _atomic_write(project_file, updated_config)
            if _inspect_install(project)["plugin_enabled"]:
                raise OSError("project settings readback failed")
        receipt_backup.parent.mkdir(parents=True)
        os.replace(target_receipt, receipt_backup)
        if _read_regular_bytes(receipt_backup, "receipt_changed_during_uninstall") != receipt_bytes:
            raise ReceiptError("receipt_changed_during_uninstall")
    except (OSError, ValueError) as exc:
        rollback_errors: list[str] = []
        try:
            _atomic_write(project_file, original_config)
        except BaseException as rollback_exc:
            rollback_errors.append(type(rollback_exc).__name__)
        if receipt_backup.exists():
            try:
                target_receipt.parent.mkdir(parents=True, exist_ok=True)
                os.replace(receipt_backup, target_receipt)
            except BaseException as rollback_exc:
                rollback_errors.append(type(rollback_exc).__name__)
        for staged, owned in reversed(moved):
            if not staged.exists():
                continue
            try:
                owned.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, owned)
            except BaseException as rollback_exc:
                rollback_errors.append(type(rollback_exc).__name__)
        cleanup_deferred = False
        if not rollback_errors and backup.exists():
            try:
                shutil.rmtree(backup)
            except OSError:
                cleanup_deferred = True
        result = _plan_result(project)
        locked = isinstance(exc, PermissionError)
        result.update(status="requires_restart" if locked else "failed")
        result["steps"] = [
            {
                "id": "uninstall",
                "status": "failed",
                "message": "Uninstall transaction did not commit.",
                "error_type": type(exc).__name__,
                "rollback": "incomplete" if rollback_errors else "restored",
                "cleanup": "deferred" if cleanup_deferred else "complete",
            }
        ]
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "uninstall",
            "failure_reason": "rollback_incomplete"
            if rollback_errors
            else ("files_locked" if locked else "filesystem_error"),
        }
        return (
            INSTALL_EXIT_REQUIRES_RESTART if locked else INSTALL_EXIT_INSTALL,
            result,
        )
    _remove_empty_owned_directories(destination, owned_files)
    try:
        shutil.rmtree(backup)
    except OSError as exc:
        result = _plan_result(project)
        result.update(status="requires_restart", receipt_path=None, install_state="absent")
        result["steps"] = [
            {
                "id": "cleanup_backup",
                "status": "requires_restart",
                "message": "Committed uninstall cleanup is deferred.",
                "error_type": type(exc).__name__,
            }
        ]
        result["verify"] = {
            "directly_usable": False,
            "failure_stage": "uninstall_cleanup",
            "failure_reason": "cleanup_locked",
        }
        return INSTALL_EXIT_REQUIRES_RESTART, result
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


def _run_standard(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    if args.verb in {"install", "upgrade", "uninstall"} and args.dry_run:
        return _run_dry_run(args)
    if args.verb in {"install", "upgrade", "uninstall"} and not args.yes:
        return _confirmation_required(args.project)
    if args.verb in {"install", "upgrade"}:
        return _run_install(args)
    if args.verb == "status":
        return _run_status(args.project)
    if args.verb == "verify":
        return _run_verify(args.project, args.instance_id)
    if args.verb == "uninstall":
        return _run_uninstall(args.project)
    raise AssertionError("unsupported lifecycle verb")


def _unexpected_failure(args: argparse.Namespace, exc: Exception) -> tuple[int, dict[str, Any]]:
    locked = isinstance(exc, PermissionError)
    stage = (
        "verify" if args.verb == "verify" else ("preflight" if args.verb == "status" else args.verb)
    )
    result = _plan_result(args.project)
    result.update(status="requires_restart" if locked else "failed")
    result["steps"] = [
        {
            "id": stage,
            "status": "failed",
            "message": "Lifecycle operation failed safely.",
            "error_type": type(exc).__name__,
        }
    ]
    result["verify"] = {
        "directly_usable": False,
        "failure_stage": stage,
        "failure_reason": "files_locked" if locked else "lifecycle_error",
    }
    if locked:
        return INSTALL_EXIT_REQUIRES_RESTART, result
    return (
        INSTALL_EXIT_PREFLIGHT
        if args.verb == "status"
        else (INSTALL_EXIT_INSTALL if args.verb != "verify" else INSTALL_EXIT_VERIFY),
        result,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the standard lifecycle CLI or the legacy addon installer."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {"install", "status", "verify", "uninstall", "upgrade"}:
        args = _standard_parser().parse_args(arguments)
        try:
            exit_code, result = _run_standard(args)
        except Exception as exc:
            exit_code, result = _unexpected_failure(args, exc)
        print(json.dumps(result, sort_keys=True))
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
