from __future__ import annotations

import json
from pathlib import Path

from dcc_mcp_godot.build_optimization import make_plan, measure_artifacts, scan_project, write_plan


def _project(tmp_path: Path, *, body: str, features: str = "4.5") -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "project.godot").write_text(
        f'[application]\nconfig/features=PackedStringArray("{features}")\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n',
        encoding="utf-8",
    )
    (project / "main.gd").write_text(body, encoding="utf-8")
    return project


def test_scan_and_plan_preserves_3d_and_non_latin_features(tmp_path: Path):
    project = _project(
        tmp_path,
        body='extends CharacterBody3D\nvar label = "你好"\nvar camera: Camera3D\n',
    )

    scan = scan_project(project)
    plan = make_plan(scan, target="windows")

    assert scan["signals"]["3d"] is True
    assert scan["signals"]["non_latin_text"] is True
    assert scan["signals"]["text"] is True
    assert "disable_3d" not in plan["options"]
    assert "module_text_server_adv_enabled" not in plan["options"]
    assert "graphite" not in plan["options"]
    assert plan["options"]["optimize"] == "size_extra"
    assert plan["options"]["vulkan"] == "no"


def test_generate_writes_deterministic_profile_and_minimal_modules(tmp_path: Path):
    project = _project(tmp_path, body='extends CharacterBody2D\nvar icon = "res://ui.svg"\n')
    (project / "ui.svg").write_text("<svg/>", encoding="utf-8")
    plan = make_plan(scan_project(project), target="web", minimal_modules=True)
    outputs = write_plan(plan, tmp_path / "generated")

    profile = Path(outputs["profile"]).read_text(encoding="utf-8")
    build_profile = json.loads(Path(outputs["build_profile"]).read_text(encoding="utf-8"))
    report = json.loads(Path(outputs["report"]).read_text(encoding="utf-8"))

    assert "optimize = 'size_extra'" in profile
    assert "modules_enabled_by_default = 'no'" in profile
    assert "module_svg_enabled = 'yes'" in profile
    assert build_profile["type"] == "build_profile"
    assert build_profile["disabled_build_options"]["disable_3d"] is True
    assert report["outputs"]["profile"] == outputs["profile"]


def test_measure_artifacts_reports_directory_digest_and_baseline(tmp_path: Path):
    artifact = tmp_path / "export"
    artifact.mkdir()
    (artifact / "game.pck").write_bytes(b"pck")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"total_bytes": 1}), encoding="utf-8")

    result = measure_artifacts([artifact], baseline)

    assert result["total_bytes"] == 3
    assert len(result["artifacts"][0]["sha256"]) == 64
    assert result["delta_bytes"] == 2


def test_legacy_engine_uses_legacy_flags_and_keeps_navigation_options(tmp_path: Path):
    project = _project(tmp_path, body="extends Node2D\n", features="4.4")

    plan = make_plan(scan_project(project), target="linux")

    assert plan["options"]["optimize"] == "size"
    assert plan["options"]["openxr"] == "no"
    assert plan["options"]["minizip"] == "no"
    assert "disable_navigation_2d" not in plan["options"]
    assert plan["platform"] == "linuxbsd"


def test_forced_dynamic_features_are_enabled_in_minimal_module_mode(tmp_path: Path):
    project = _project(tmp_path, body="extends Node2D\n")

    plan = make_plan(
        scan_project(project),
        target="web",
        minimal_modules=True,
        force=["advanced-text", "graphite", "navigation", "zip"],
    )

    assert plan["options"]["module_text_server_adv_enabled"] == "yes"
    assert plan["options"]["module_navigation_2d_enabled"] == "yes"
    assert plan["options"]["module_navigation_3d_enabled"] == "yes"
    assert plan["options"]["module_zip_enabled"] == "yes"
    assert "graphite" not in plan["options"]
    assert "module_zip_enabled" not in plan["disabled_build_options"]
