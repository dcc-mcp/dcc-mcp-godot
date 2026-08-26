"""Project-owned filesystem transactions for the Godot addon lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .__version__ import __version__

PLUGIN_PATH = "res://addons/dcc_mcp_godot/plugin.cfg"
RECEIPT_SCHEMA_VERSION = 1
RECEIPT_TYPE = "dcc-mcp-install-receipt"

_SECTION_RE = re.compile(r"(?m)^[ \t]*\[([^\]\r\n]+)\][ \t]*(?:[;#].*)?\r?$")
_ENABLED_RE = re.compile(
    r"(?m)^(?P<prefix>[ \t]*enabled[ \t]*=[ \t]*PackedStringArray[ \t]*\()"
    r"(?P<values>[^\r\n]*)"
    r"(?P<suffix>\)[ \t]*(?:[;#].*)?)(?P<newline>\r?\n|$)"
)
_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ReceiptError(ValueError):
    """A stable, public-safe receipt validation failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def addon_source() -> Path:
    """Return the packaged addon directory."""
    return Path(__file__).resolve().parent / "godot_addon" / "addons" / "dcc_mcp_godot"


def _is_reparse(stat_result: os.stat_result) -> bool:
    attributes = int(getattr(stat_result, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return stat.S_ISLNK(stat_result.st_mode) or bool(attributes & reparse_flag)


def _lstat_regular_file(path: Path, code: str) -> os.stat_result:
    try:
        value = os.lstat(path)
    except OSError as exc:
        raise ReceiptError(code) from exc
    if _is_reparse(value) or not stat.S_ISREG(value.st_mode):
        raise ReceiptError(code)
    return value


def _lstat_directory(path: Path, code: str) -> os.stat_result:
    try:
        value = os.lstat(path)
    except OSError as exc:
        raise ReceiptError(code) from exc
    if _is_reparse(value) or not stat.S_ISDIR(value.st_mode):
        raise ReceiptError(code)
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        before = _lstat_regular_file(path, "owned_file_not_regular")
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise ReceiptError("owned_file_changed")
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ReceiptError("owned_file_unreadable") from exc
    return digest.hexdigest()


def read_regular_bytes(path: Path, code: str) -> bytes:
    """Read bytes only when lstat and the opened handle identify the same regular file."""
    before = _lstat_regular_file(path, code)
    try:
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise ReceiptError(code)
            return stream.read()
    except OSError as exc:
        raise ReceiptError(code) from exc


def _ensure_safe_directory_path(root: Path, target: Path) -> None:
    """Create a directory chain without traversing symlinks or reparse points."""
    root = root.resolve()
    _lstat_directory(root, "project_root_not_regular")
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ReceiptError("path_outside_project") from exc
    current = root
    for part in relative.parts:
        current /= part
        if os.path.lexists(current):
            _lstat_directory(current, "directory_not_regular")
        else:
            current.mkdir()
            _lstat_directory(current, "directory_not_regular")


def _ensure_tree_safe(root: Path) -> None:
    _lstat_directory(root, "destination_not_regular")
    try:
        entries = list(root.rglob("*"))
    except OSError as exc:
        raise ReceiptError("destination_unreadable") from exc
    for entry in entries:
        try:
            value = os.lstat(entry)
        except OSError as exc:
            raise ReceiptError("destination_unreadable") from exc
        if _is_reparse(value) or not (stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode)):
            raise ReceiptError("destination_contains_unsafe_entry")


def _capture_tree_binding(root: Path) -> dict[str, Any]:
    root_stat = _lstat_directory(root, "addon_backup_not_directory")
    _ensure_tree_safe(root)
    entries: list[tuple[Any, ...]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        value = os.lstat(path)
        if stat.S_ISDIR(value.st_mode):
            entries.append((relative, "directory", value.st_dev, value.st_ino))
        else:
            entries.append(
                (
                    relative,
                    "file",
                    value.st_dev,
                    value.st_ino,
                    value.st_size,
                    value.st_mtime_ns,
                    _sha256(path),
                )
            )
    return {
        "root_identity": (root_stat.st_dev, root_stat.st_ino),
        "entries": tuple(entries),
    }


def _assert_tree_binding(root: Path, expected: dict[str, Any]) -> None:
    if _capture_tree_binding(root) != expected:
        raise ReceiptError("addon_backup_changed")


def _addon_backup_binding(destination: Path, backup: Path) -> tuple[str, str]:
    if backup.parent != destination.parent:
        raise ReceiptError("addon_backup_name_invalid")
    states = {
        f".{destination.name}.backup-": "backup",
        f".{destination.name}.cleanup-pending-": "cleanup_pending",
    }
    for prefix, state in states.items():
        if backup.name.startswith(prefix):
            token = backup.name[len(prefix) :]
            if len(token) == 32 and all(character in "0123456789abcdef" for character in token):
                return token, state
    raise ReceiptError("addon_backup_name_invalid")


def pending_addon_backups(destination: Path) -> list[Path]:
    """Discover bounded installer backup state without trusting or deleting it."""
    parent = destination.parent
    if not os.path.lexists(parent):
        return []
    _lstat_directory(parent, "addon_parent_not_directory")
    pending: list[Path] = []
    for entry in parent.iterdir():
        try:
            _addon_backup_binding(destination, entry)
        except ReceiptError:
            continue
        _lstat_directory(entry, "addon_backup_not_directory")
        pending.append(entry)
        if len(pending) > 1:
            raise ReceiptError("addon_cleanup_ambiguous")
    return pending


def _editor_plugins_bodies(content: str) -> list[tuple[int, int]]:
    sections = list(_SECTION_RE.finditer(content))
    bodies = []
    for index, section in enumerate(sections):
        if section.group(1).strip() != "editor_plugins":
            continue
        bodies.append(
            (
                section.end(),
                sections[index + 1].start() if index + 1 < len(sections) else len(content),
            )
        )
    return bodies


def _editor_plugins_body(content: str) -> tuple[int, int] | None:
    bodies = _editor_plugins_bodies(content)
    return bodies[-1] if bodies else None


def _enabled_assignment(content: str) -> re.Match[str] | None:
    assignments = [
        assignment
        for start, end in _editor_plugins_bodies(content)
        for assignment in _ENABLED_RE.finditer(content, start, end)
    ]
    return assignments[-1] if assignments else None


def _enabled_tokens(match: re.Match[str]) -> list[tuple[str, int, int]]:
    tokens: list[tuple[str, int, int]] = []
    values_start = match.start("values")
    for token in _STRING_RE.finditer(match.group("values")):
        try:
            value = json.loads(token.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError("editor_plugins enabled contains an invalid string") from exc
        if not isinstance(value, str):
            raise ValueError("editor_plugins enabled entries must be strings")
        tokens.append((value, values_start + token.start(), values_start + token.end()))
    residue = _STRING_RE.sub("", match.group("values"))
    if residue.strip(" \t,"):
        raise ValueError("editor_plugins enabled must be a string array")
    if tokens and residue.count(",") != len(tokens) - 1:
        raise ValueError("editor_plugins enabled has invalid separators")
    return tokens


def plugin_enabled(content: str) -> bool:
    """Return whether the semantic editor_plugins enabled array owns this plugin."""
    match = _enabled_assignment(content)
    return match is not None and any(value == PLUGIN_PATH for value, _, _ in _enabled_tokens(match))


def enable_plugin(content: str) -> tuple[str, str]:
    """Return project settings with the adapter plugin enabled exactly once."""
    match = _enabled_assignment(content)
    if match is not None:
        tokens = _enabled_tokens(match)
        if any(value == PLUGIN_PATH for value, _, _ in tokens):
            return content, "preexisting"
        insertion = (", " if tokens else "") + json.dumps(PLUGIN_PATH)
        at = match.end("values")
        return content[:at] + insertion + content[at:], "entry_added"

    newline = "\r\n" if "\r\n" in content else "\n"
    bounds = _editor_plugins_body(content)
    assignment = f"enabled=PackedStringArray({json.dumps(PLUGIN_PATH)}){newline}"
    if bounds is not None:
        at = bounds[0]
        if content[at : at + len(newline)] == newline:
            at += len(newline)
        return content[:at] + assignment + content[at:], "assignment_added"

    prefix = content
    action = "section_added"
    if prefix and not prefix.endswith(("\n", "\r")):
        prefix += newline
        action = "section_added_with_newline"
    return f"{prefix}[editor_plugins]{newline}{assignment}", action


def disable_plugin(content: str, action: str = "entry_added") -> str:
    """Remove only the adapter entry from Godot's enabled plugin list."""
    if action == "preexisting":
        return content
    enabled = _enabled_assignment(content)
    if enabled is None:
        return content
    tokens = _enabled_tokens(enabled)
    owned_index = next(
        (index for index, token in enumerate(tokens) if token[0] == PLUGIN_PATH), None
    )
    if owned_index is None:
        return content
    _, start, end = tokens[owned_index]
    if len(tokens) == 1:
        updated = content[:start] + content[end:]
    elif owned_index < len(tokens) - 1:
        next_start = tokens[owned_index + 1][1]
        comma = content.find(",", end, next_start)
        if comma < 0:
            raise ValueError("editor_plugins enabled has invalid separators")
        end = comma + 1
        while end < next_start and content[end] in " \t":
            end += 1
        updated = content[:start] + content[end:]
    else:
        previous_end = tokens[owned_index - 1][2]
        comma = content.rfind(",", previous_end, start)
        if comma < 0:
            raise ValueError("editor_plugins enabled has invalid separators")
        start = comma
        while start > previous_end and content[start - 1] in " \t":
            start -= 1
        updated = content[:start] + content[end:]

    if action not in {"assignment_added", "section_added", "section_added_with_newline"}:
        return updated
    remaining_assignment = _enabled_assignment(updated)
    if remaining_assignment is None or _enabled_tokens(remaining_assignment):
        return updated
    updated = updated[: remaining_assignment.start()] + updated[remaining_assignment.end() :]
    if action == "assignment_added":
        return updated
    bounds = _editor_plugins_body(updated)
    if bounds is None:
        return updated
    section_start, section_end = bounds
    section = next(
        match
        for match in _SECTION_RE.finditer(updated)
        if match.group(1).strip() == "editor_plugins"
    )
    if updated[section_start:section_end].strip():
        return updated
    remove_start = section.start()
    if action == "section_added_with_newline" and remove_start > 0:
        if updated[:remove_start].endswith("\r\n"):
            remove_start -= 2
        elif updated[:remove_start].endswith("\n"):
            remove_start -= 1
    return updated[:remove_start] + updated[section_end:]


def read_project_settings(project_file: Path) -> str:
    try:
        return read_regular_bytes(project_file, "project_file_not_regular").decode("utf-8")
    except (OSError, UnicodeError, ReceiptError) as exc:
        raise ReceiptError("project_file_unreadable") from exc


def atomic_write(
    path: Path,
    content: str,
    *,
    expected_identity: tuple[int, int, int, int] | None = None,
    expected_content: bytes | None = None,
) -> None:
    """Replace one text file only after its complete staged write succeeds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.stage-{uuid.uuid4().hex}")
    claimed: Path | None = None
    try:
        with staged.open("w", encoding="utf-8", newline="") as stream:
            stream.write(content)
        if expected_identity is None and expected_content is None:
            os.replace(staged, path)
            return
        if expected_identity is None or expected_content is None:
            raise ReceiptError("atomic_write_binding_invalid")
        claimed = path.with_name(f".{path.name}.write-claim-{uuid.uuid4().hex}")
        os.replace(path, claimed)
        claimed_stat = _lstat_regular_file(claimed, "atomic_target_changed")
        claimed_identity = (
            claimed_stat.st_dev,
            claimed_stat.st_ino,
            claimed_stat.st_size,
            claimed_stat.st_mtime_ns,
        )
        if (
            claimed_identity != expected_identity
            or read_regular_bytes(claimed, "atomic_target_changed") != expected_content
        ):
            raise ReceiptError("atomic_target_changed")
        os.link(staged, path)
        staged.unlink()
        claimed.unlink()
    except BaseException:
        try:
            staged.unlink(missing_ok=True)
        except OSError:
            pass
        if claimed is not None and os.path.lexists(claimed) and not os.path.lexists(path):
            try:
                os.link(claimed, path)
                claimed.unlink()
            except OSError:
                pass
        raise


def install_addon(project: Path, *, overwrite: bool = False) -> Path:
    """Copy the EditorPlugin for the legacy install-only entry point."""
    project = project.resolve()
    try:
        read_project_settings(project / "project.godot")
    except ReceiptError as exc:
        raise ValueError(f"Godot project.godot is missing or unsafe: {exc.code}") from exc
    destination = project / "addons" / "dcc_mcp_godot"
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Addon already exists: {destination}; pass --force to replace it")
    shutil.copytree(addon_source(), destination, dirs_exist_ok=overwrite)
    return destination


def stage_addon(
    destination: Path,
    owned_files: Iterable[Path] = (),
    *,
    backup_binding: dict[str, Any] | None = None,
) -> Path | None:
    """Swap a complete staged addon tree while preserving every unowned file."""
    project = destination.parents[1]
    _ensure_safe_directory_path(project, destination.parent)
    staged = destination.parent / f".{destination.name}.stage-{uuid.uuid4().hex}"
    backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}"
    had_destination = destination.exists()
    try:
        if had_destination:
            _ensure_tree_safe(destination)
            shutil.copytree(destination, staged)
            for owned in owned_files:
                relative = owned.relative_to(destination)
                staged_owned = staged / relative
                _lstat_regular_file(staged_owned, "owned_file_not_regular")
                staged_owned.unlink()
            for directory in sorted(
                staged.rglob("*"), key=lambda item: len(item.parts), reverse=True
            ):
                if directory.is_dir():
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
            shutil.copytree(addon_source(), staged, dirs_exist_ok=True)
        else:
            shutil.copytree(addon_source(), staged)
        if had_destination:
            os.replace(destination, backup)
            if backup_binding is not None:
                backup_binding.update(_capture_tree_binding(backup))
        os.replace(staged, destination)
    except BaseException:
        try:
            if staged.exists():
                shutil.rmtree(staged)
        except OSError:
            pass
        if had_destination and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    return backup if had_destination else None


def _merge_late_unowned_files(destination: Path, backup: Path) -> None:
    source = addon_source()
    packaged = {path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()}
    _ensure_tree_safe(destination)
    _ensure_tree_safe(backup)
    for path in sorted(destination.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir() or path.relative_to(destination).as_posix() in packaged:
            continue
        relative = path.relative_to(destination)
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, target)


def rollback_addon(
    destination: Path,
    backup: Path | None,
    backup_binding: dict[str, Any] | None = None,
) -> None:
    """Restore owned content while retaining files created after staging."""
    if backup is not None:
        if not backup.exists():
            raise OSError("addon rollback backup is unavailable")
        if backup_binding is not None:
            _assert_tree_binding(backup, backup_binding)
        if destination.exists():
            _merge_late_unowned_files(destination, backup)
    if destination.exists():
        shutil.rmtree(destination)
    if backup is not None:
        os.replace(backup, destination)


def defer_addon_backup(destination: Path, backup: Path, binding: dict[str, Any]) -> Path:
    """Preserve a whole transaction backup when final deletion cannot be identity-bound."""
    token, state = _addon_backup_binding(destination, backup)
    if state != "backup":
        raise ReceiptError("addon_backup_state_invalid")
    _assert_tree_binding(backup, binding)
    pending = backup.with_name(f".{destination.name}.cleanup-pending-{token}")
    if os.path.lexists(pending):
        raise ReceiptError("addon_cleanup_ambiguous")
    os.replace(backup, pending)
    try:
        _assert_tree_binding(pending, binding)
    except BaseException:
        try:
            if os.path.lexists(pending) and not os.path.lexists(backup):
                os.replace(pending, backup)
        except BaseException:
            pass
        raise
    return pending


def receipt_path(project: Path) -> Path:
    return project / ".dcc-mcp" / "receipts" / "godot.json"


def _owned_relative_path(project: Path, destination: Path, raw: object) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise ReceiptError("owned_path_invalid")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ReceiptError("owned_path_invalid")
    if pure.as_posix() != raw:
        raise ReceiptError("owned_path_invalid")
    candidate = project.joinpath(*pure.parts)
    try:
        candidate.relative_to(destination)
    except ValueError as exc:
        raise ReceiptError("owned_path_outside_destination") from exc
    return candidate


def write_receipt(
    project: Path,
    destination: Path,
    *,
    plugin_config_action: str,
    godot: dict[str, Any],
    python: Path,
) -> Path:
    """Commit a typed, versioned, content-bound ownership receipt."""
    project = project.resolve()
    destination = destination.resolve()
    _ensure_tree_safe(destination)
    owned_files: list[dict[str, str]] = []
    source = addon_source()
    for source_path in sorted(source.rglob("*")):
        if source_path.is_dir():
            continue
        relative = source_path.relative_to(source)
        path = destination / relative
        _lstat_regular_file(path, "owned_file_not_regular")
        owned_files.append({"path": path.relative_to(project).as_posix(), "sha256": _sha256(path)})
    if not owned_files:
        raise ReceiptError("owned_files_empty")
    target = receipt_path(project)
    _ensure_safe_directory_path(project, target.parent)
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_type": RECEIPT_TYPE,
        "dcc_type": "godot",
        "adapter_version": __version__,
        "project_root": str(project),
        "destination": str(destination),
        "owned_files": owned_files,
        "plugin_config_action": plugin_config_action,
        "godot": {"path": str(godot["path"]), "version": str(godot["version"])},
        "python": str(python.resolve()),
    }
    atomic_write(target, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return target


def validate_receipt(project: Path) -> tuple[dict[str, Any], list[Path]]:
    """Validate receipt identity, types, owned paths, links, and content hashes."""
    project = project.resolve()
    destination = project / "addons" / "dcc_mcp_godot"
    target = receipt_path(project)
    _lstat_directory(project, "project_root_not_regular")
    _ensure_tree_safe(destination)
    try:
        loaded = json.loads(read_regular_bytes(target, "receipt_not_regular").decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReceiptError("receipt_unreadable") from exc
    if not isinstance(loaded, dict):
        raise ReceiptError("receipt_not_object")
    required_types = {
        "schema_version": int,
        "receipt_type": str,
        "dcc_type": str,
        "adapter_version": str,
        "project_root": str,
        "destination": str,
        "owned_files": list,
        "plugin_config_action": str,
        "godot": dict,
        "python": str,
    }
    if set(loaded) != set(required_types):
        raise ReceiptError("receipt_fields_invalid")
    if any(type(loaded.get(key)) is not value for key, value in required_types.items()):
        raise ReceiptError("receipt_field_type_invalid")
    if loaded["schema_version"] != RECEIPT_SCHEMA_VERSION:
        raise ReceiptError("receipt_schema_unsupported")
    if loaded["receipt_type"] != RECEIPT_TYPE or loaded["dcc_type"] != "godot":
        raise ReceiptError("receipt_identity_invalid")
    if loaded["project_root"] != str(project) or loaded["destination"] != str(destination):
        raise ReceiptError("receipt_root_mismatch")
    if not loaded["adapter_version"] or not loaded["python"]:
        raise ReceiptError("receipt_field_value_invalid")
    if loaded["plugin_config_action"] not in {
        "preexisting",
        "entry_added",
        "assignment_added",
        "section_added",
        "section_added_with_newline",
    }:
        raise ReceiptError("receipt_plugin_action_invalid")
    godot = loaded["godot"]
    if set(godot) != {"path", "version"} or not all(
        isinstance(godot.get(key), str) and godot[key] for key in ("path", "version")
    ):
        raise ReceiptError("receipt_host_invalid")
    raw_owned = loaded["owned_files"]
    if not raw_owned or len(raw_owned) > 4096:
        raise ReceiptError("owned_files_invalid")
    owned: list[Path] = []
    seen: set[str] = set()
    for entry in raw_owned:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise ReceiptError("owned_entry_invalid")
        raw_path = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise ReceiptError("owned_hash_invalid")
        candidate = _owned_relative_path(project, destination, raw_path)
        normalized = candidate.relative_to(project).as_posix()
        if normalized in seen:
            raise ReceiptError("owned_path_duplicate")
        seen.add(normalized)
        _lstat_regular_file(candidate, "owned_file_not_regular")
        if _sha256(candidate) != digest:
            raise ReceiptError("owned_file_tampered")
        owned.append(candidate)
    return loaded, owned


def inspect_install(project: Path) -> dict[str, Any]:
    """Classify absent, partial, and validated receipt-owned installs."""
    project = project.resolve()
    project_file = project / "project.godot"
    destination = project / "addons" / "dcc_mcp_godot"
    target = receipt_path(project)
    receipt: dict[str, Any] | None = None
    owned_files: list[Path] = []
    receipt_error: str | None = None
    marker_present = False
    try:
        marker_present = plugin_enabled(read_project_settings(project_file))
    except (OSError, UnicodeError, ValueError) as exc:
        receipt_error = exc.code if isinstance(exc, ReceiptError) else "project_settings_invalid"
    if os.path.lexists(target):
        try:
            receipt, owned_files = validate_receipt(project)
        except (OSError, ValueError) as exc:
            receipt_error = exc.code if isinstance(exc, ReceiptError) else "receipt_invalid"
    addon_present = False
    if os.path.lexists(destination):
        try:
            _ensure_tree_safe(destination)
            addon_present = (destination / "plugin.cfg").exists()
        except ReceiptError as exc:
            receipt_error = exc.code
    complete = receipt is not None and bool(owned_files) and addon_present and marker_present
    any_present = os.path.lexists(target) or os.path.lexists(destination) or marker_present
    return {
        "install_state": "installed" if complete else ("partial" if any_present else "absent"),
        "receipt_path": str(target),
        "receipt": receipt,
        "receipt_error": receipt_error,
        "owned_files": owned_files,
        "ownership_valid": receipt is not None,
        "addon_present": addon_present,
        "plugin_enabled": marker_present,
        "files_present": receipt is not None and bool(owned_files),
    }


def remove_empty_owned_directories(destination: Path, owned_files: Iterable[Path]) -> None:
    """Remove only directories made empty by deleting owned files."""
    directories = {
        parent
        for owned in owned_files
        for parent in owned.parents
        if parent == destination or destination in parent.parents
    }
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass


__all__ = [
    "PLUGIN_PATH",
    "RECEIPT_SCHEMA_VERSION",
    "ReceiptError",
    "addon_source",
    "atomic_write",
    "defer_addon_backup",
    "disable_plugin",
    "enable_plugin",
    "inspect_install",
    "install_addon",
    "plugin_enabled",
    "pending_addon_backups",
    "read_regular_bytes",
    "read_project_settings",
    "receipt_path",
    "remove_empty_owned_directories",
    "rollback_addon",
    "stage_addon",
    "validate_receipt",
    "write_receipt",
]
