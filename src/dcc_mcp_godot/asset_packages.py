"""Safe installation helpers for downloaded Godot asset packages."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Optional

MAX_ARCHIVE_FILES = int(os.environ.get("DCC_MCP_GODOT_MAX_ARCHIVE_FILES", "10000"))
MAX_UNCOMPRESSED_BYTES = int(
    os.environ.get("DCC_MCP_GODOT_MAX_UNCOMPRESSED_BYTES", str(2 * 1024**3))
)
PACKAGE_TYPES = {"auto", "addon", "asset_pack", "project"}


class AssetPackageError(ValueError):
    """Raised when a package cannot be installed safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(raw_name: str) -> PurePosixPath:
    name = PurePosixPath(raw_name.replace("\\", "/"))
    if name.is_absolute() or not name.parts or ".." in name.parts:
        raise AssetPackageError(f"Unsafe archive path: {raw_name}")
    if ":" in name.parts[0]:
        raise AssetPackageError(f"Unsafe archive path: {raw_name}")
    return name


def _archive_members(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    total_size = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        mode = info.external_attr >> 16
        if stat.S_IFMT(mode) == stat.S_IFLNK:
            raise AssetPackageError(f"Archive symlinks are not supported: {info.filename}")
        total_size += info.file_size
        members.append((info, _safe_name(info.filename)))

    if not members:
        raise AssetPackageError("Archive contains no files")
    if len(members) > MAX_ARCHIVE_FILES:
        raise AssetPackageError(
            f"Archive contains {len(members)} files; limit is {MAX_ARCHIVE_FILES}"
        )
    if total_size > MAX_UNCOMPRESSED_BYTES:
        raise AssetPackageError(
            f"Archive expands to {total_size} bytes; limit is {MAX_UNCOMPRESSED_BYTES}"
        )
    return members


def _strip_prefix(names: list[PurePosixPath]) -> Optional[str]:
    first_parts = {name.parts[0] for name in names if len(name.parts) > 1}
    if len(first_parts) != 1 or any(len(name.parts) == 1 for name in names):
        return None
    prefix = next(iter(first_parts))
    stripped = [PurePosixPath(*name.parts[1:]) for name in names]
    if any(name == PurePosixPath("project.godot") for name in stripped) or any(
        name.parts and name.parts[0] == "addons" for name in stripped
    ):
        return prefix
    return None


def _logical_name(name: PurePosixPath, prefix: Optional[str]) -> PurePosixPath:
    return PurePosixPath(*name.parts[1:]) if prefix else name


def _plugin_names(names: list[PurePosixPath]) -> list[str]:
    plugins = []
    for name in names:
        if len(name.parts) >= 3 and name.parts[0] == "addons" and name.name == "plugin.cfg":
            plugins.append("/".join(name.parts[1:-1]))
    return sorted(set(plugins))


def _detect_type(names: list[PurePosixPath]) -> str:
    if PurePosixPath("project.godot") in names:
        return "project"
    if _plugin_names(names):
        return "addon"
    return "asset_pack"


def _package_value(package: Mapping[str, Any], key: str, default: Any = None) -> Any:
    value = package.get(key, default)
    return value if value not in (None, "") else default


def _target_root(package_type: str, project_path: Path, destination: Optional[str]) -> Path:
    if package_type == "project":
        if not destination:
            raise AssetPackageError("Project packages require an explicit destination")
        return Path(destination).expanduser().resolve()
    if not (project_path / "project.godot").is_file():
        raise AssetPackageError(f"Godot project file not found: {project_path / 'project.godot'}")
    return project_path


def _selected_members(
    members: list[tuple[zipfile.ZipInfo, PurePosixPath]],
    prefix: Optional[str],
    package_type: str,
) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    selected = []
    for info, stored_name in members:
        name = _logical_name(stored_name, prefix)
        if package_type == "addon" and (not name.parts or name.parts[0] != "addons"):
            continue
        selected.append((info, name))
    if not selected:
        raise AssetPackageError(f"Archive contains no installable files for type {package_type}")
    return selected


def plan_asset_install(
    package: Mapping[str, Any],
    project_path: str,
    destination: Optional[str] = None,
) -> dict[str, Any]:
    """Inspect a package without changing the target filesystem."""
    archive_path = Path(str(_package_value(package, "archive_path", ""))).expanduser().resolve()
    asset_id = str(_package_value(package, "asset_id", "")).strip()
    if not asset_id:
        raise AssetPackageError("package.asset_id is required")
    if not archive_path.is_file():
        raise AssetPackageError(f"Package archive not found: {archive_path}")
    if not zipfile.is_zipfile(archive_path):
        raise AssetPackageError(f"Package is not a ZIP archive: {archive_path}")

    actual_sha256 = _sha256(archive_path)
    expected_sha256 = str(_package_value(package, "sha256", "")).removeprefix("sha256:")
    if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
        raise AssetPackageError(
            f"Package checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    requested_type = str(_package_value(package, "package_type", "auto"))
    if requested_type not in PACKAGE_TYPES:
        raise AssetPackageError(f"Unsupported package_type: {requested_type}")

    with zipfile.ZipFile(archive_path) as archive:
        members = _archive_members(archive)
        prefix = _strip_prefix([name for _, name in members])
        logical_names = [_logical_name(name, prefix) for _, name in members]
        detected_type = _detect_type(logical_names)
        package_type = detected_type if requested_type == "auto" else requested_type
        target_root = _target_root(
            package_type, Path(project_path).expanduser().resolve(), destination
        )
        selected = _selected_members(members, prefix, package_type)

    files = [name.as_posix() for _, name in selected]
    collisions = [name for name in files if (target_root / Path(name)).exists()]
    return {
        "asset_id": asset_id,
        "archive_path": str(archive_path),
        "sha256": actual_sha256,
        "requested_type": requested_type,
        "detected_type": detected_type,
        "package_type": package_type,
        "strip_prefix": prefix,
        "target_root": str(target_root),
        "file_count": len(files),
        "total_uncompressed_bytes": sum(info.file_size for info, _ in selected),
        "plugin_names": _plugin_names([name for _, name in selected]),
        "collisions": collisions[:200],
        "collision_count": len(collisions),
        "files": files[:200],
        "files_truncated": len(files) > 200,
    }


def _manifest_name(asset_id: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_." else "-" for character in asset_id
    )
    return safe.strip("-.") or hashlib.sha256(asset_id.encode("utf-8")).hexdigest()[:16]


def install_asset_package(
    package: Mapping[str, Any],
    project_path: str,
    destination: Optional[str] = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Install a previously downloaded package after validating its archive."""
    plan = plan_asset_install(package, project_path, destination)
    if plan["collision_count"] and not overwrite:
        raise AssetPackageError(
            f"Installation would overwrite {plan['collision_count']} files; set overwrite=true"
        )

    archive_path = Path(plan["archive_path"])
    target_root = Path(plan["target_root"])
    target_root.mkdir(parents=True, exist_ok=True)
    installed = []
    with zipfile.ZipFile(archive_path) as archive:
        members = _archive_members(archive)
        selected = _selected_members(members, plan["strip_prefix"], plan["package_type"])
        for info, name in selected:
            target = (target_root / Path(name.as_posix())).resolve()
            if os.path.commonpath([str(target_root), str(target)]) != str(target_root):
                raise AssetPackageError(f"Unsafe install target: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            installed.append(name.as_posix())

    manifest_dir = target_root / ".dcc-mcp" / "assets"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{_manifest_name(plan['asset_id'])}.json"
    manifest = dict(package)
    manifest.update(
        {
            "archive_path": str(archive_path),
            "sha256": plan["sha256"],
            "package_type": plan["package_type"],
            "installed_files": installed,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    return {
        **plan,
        "installed": True,
        "installed_files": installed[:200],
        "installed_files_truncated": len(installed) > 200,
        "manifest_path": str(manifest_path),
        "overwrite": overwrite,
    }
