from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from dcc_mcp_godot.asset_packages import (
    AssetPackageError,
    install_asset_package,
    plan_asset_install,
)


def _archive(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def _package(path: Path, package_type: str = "auto") -> dict[str, str]:
    return {
        "asset_id": "godot-store:test/example@1",
        "archive_path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "package_type": package_type,
        "license": "MIT",
    }


def test_plan_detects_prefixed_addon_and_plugin(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    archive = _archive(
        tmp_path / "addon.zip",
        {
            "release/addons/phantom_camera/plugin.cfg": "[plugin]\n",
            "release/addons/phantom_camera/plugin.gd": "@tool\n",
            "release/README.md": "ignored for addon installs",
        },
    )

    plan = plan_asset_install(_package(archive), str(project))

    assert plan["detected_type"] == "addon"
    assert plan["strip_prefix"] == "release"
    assert plan["plugin_names"] == ["phantom_camera"]
    assert plan["file_count"] == 2


def test_install_addon_writes_files_and_attribution_manifest(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    archive = _archive(
        tmp_path / "addon.zip",
        {"addons/example/plugin.cfg": "[plugin]\n", "addons/example/plugin.gd": "@tool\n"},
    )

    result = install_asset_package(_package(archive), str(project))

    assert (project / "addons" / "example" / "plugin.cfg").is_file()
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["asset_id"] == "godot-store:test/example@1"
    assert manifest["sha256"] == result["sha256"]


def test_install_refuses_collisions_without_overwrite(tmp_path: Path):
    project = tmp_path / "project"
    target = project / "addons" / "example"
    target.mkdir(parents=True)
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    (target / "plugin.cfg").write_text("old", encoding="utf-8")
    archive = _archive(tmp_path / "addon.zip", {"addons/example/plugin.cfg": "new"})

    with pytest.raises(AssetPackageError, match="overwrite"):
        install_asset_package(_package(archive), str(project))


def test_plan_rejects_archive_path_traversal(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    archive = _archive(tmp_path / "unsafe.zip", {"../escape.txt": "bad"})

    with pytest.raises(AssetPackageError, match="Unsafe archive path"):
        plan_asset_install(_package(archive), str(project))


def test_project_package_requires_explicit_destination(tmp_path: Path):
    project = tmp_path / "current"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    archive = _archive(
        tmp_path / "project.zip",
        {"demo/project.godot": "[application]\n", "demo/main.tscn": "[gd_scene]\n"},
    )

    with pytest.raises(AssetPackageError, match="explicit destination"):
        plan_asset_install(_package(archive), str(project))

    destination = tmp_path / "new-project"
    result = install_asset_package(_package(archive), str(project), str(destination))
    assert (destination / "project.godot").is_file()
    assert result["package_type"] == "project"
