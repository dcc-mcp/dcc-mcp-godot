"""Regressions for Core bounds in source, lock metadata, and wheel METADATA."""

import subprocess
import sys
from zipfile import ZipFile

import pytest
from packaging.requirements import Requirement

from tools.check_core_dependency import (
    ROOT,
    CoreDependencyError,
    check_core_range,
    check_wheel,
    core_requirement,
    project_metadata,
    tomllib,
)


def test_project_core_dependency_stays_within_one_minor():
    check_core_range(core_requirement(project_metadata()["dependencies"]))


def test_lock_core_dependency_matches_project():
    project = project_metadata()
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    adapter = next(package for package in lock["package"] if package["name"] == project["name"])
    core = next(
        dependency
        for dependency in adapter["metadata"]["requires-dist"]
        if dependency["name"] == "dcc-mcp-core"
    )
    declared = core_requirement(project["dependencies"])
    assert Requirement("dcc-mcp-core" + core["specifier"]).specifier == declared.specifier
    locked_core = next(package for package in lock["package"] if package["name"] == "dcc-mcp-core")
    assert locked_core["version"] in declared.specifier


@pytest.mark.parametrize(
    "specifier",
    [">=0.20.41,<1.0.0", ">=0.20.41", "<0.21.0", ">=0.20.41,<=0.21.0", ">=0.21.0,<0.21.0"],
)
def test_contract_rejects_missing_wide_or_inverted_bounds(specifier):
    with pytest.raises(CoreDependencyError):
        check_core_range(Requirement("dcc-mcp-core" + specifier))


@pytest.mark.parametrize("mutation", [None, "wide", "missing", "different-floor"])
def test_wheel_metadata_check_detects_drift(tmp_path, mutation):
    project = project_metadata()
    declared = core_requirement(project["dependencies"])
    dependency = str(declared)
    if mutation == "wide":
        dependency = "dcc-mcp-core>=0.20.0,<1.0.0"
    elif mutation == "different-floor":
        dependency = "dcc-mcp-core>=0.20.1,<0.21.0"
    metadata = f"Metadata-Version: 2.1\nName: {project['name']}\nVersion: {project['version']}\n"
    if mutation != "missing":
        metadata += f"Requires-Dist: {dependency}\n"
    wheel = tmp_path / "contract.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("adapter.dist-info/METADATA", metadata)
    if mutation is None:
        check_wheel(wheel)
    else:
        with pytest.raises(CoreDependencyError):
            check_wheel(wheel)


@pytest.mark.parametrize(
    ("dependency", "message"),
    [
        ("dcc-mcp-core>=0.20.0,<1.0.0", "within one minor line"),
        (None, "Expected one unconditional Core dependency"),
    ],
)
def test_optimized_python_rejects_invalid_wheel_metadata(tmp_path, dependency, message):
    project = project_metadata()
    metadata = f"Metadata-Version: 2.1\nName: {project['name']}\nVersion: {project['version']}\n"
    if dependency is not None:
        metadata += f"Requires-Dist: {dependency}\n"
    wheel = tmp_path / "invalid.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("adapter.dist-info/METADATA", metadata)
    result = subprocess.run(
        [sys.executable, "-O", str(ROOT / "tools/check_core_dependency.py"), str(wheel)],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert message in result.stderr
    assert "contract passed" not in result.stdout


def test_checker_dependencies_are_declared_for_development():
    dev = [Requirement(item) for item in project_metadata()["optional-dependencies"]["dev"]]
    assert any(item.name == "packaging" and item.marker is None for item in dev)
    assert any(
        item.name == "tomli"
        and (item.marker is None or item.marker.evaluate({"python_version": "3.10"}))
        for item in dev
    )
