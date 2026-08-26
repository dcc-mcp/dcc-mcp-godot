import importlib
import json
from pathlib import Path

import pytest

from dcc_mcp_godot import install as install_module
from dcc_mcp_godot.install import install_addon, main


def test_standard_install_dry_run_returns_plan_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")

    exit_code = main(["install", str(tmp_path), "--dry-run", "--yes", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["dcc_type"] == "godot"
    assert payload["status"] == "planned"
    assert payload["verify"]["directly_usable"] is False
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()


def test_canonical_console_routes_standard_lifecycle_verbs(monkeypatch: pytest.MonkeyPatch):
    cli = importlib.import_module("dcc_mcp_godot.cli")
    received: list[list[str]] = []

    def run_install(arguments: list[str]) -> int:
        received.append(arguments)
        return 40

    monkeypatch.setattr(install_module, "main", run_install)

    assert cli.main(["verify", "project", "--json"]) == 40
    assert received == [["verify", "project", "--json"]]


def test_standard_install_enables_plugin_and_records_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    project_file = tmp_path / "project.godot"
    project_file.write_text('[application]\nconfig/name="Install test"\n', encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {"path": str(godot), "version": "4.4.1", "version_tuple": (4, 4, 1)},
        raising=False,
    )

    exit_code = main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])

    assert exit_code == 50
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "requires_restart"
    assert payload["verify"]["directly_usable"] is False
    assert (tmp_path / "addons" / "dcc_mcp_godot" / "plugin.cfg").is_file()
    assert "res://addons/dcc_mcp_godot/plugin.cfg" in project_file.read_text(encoding="utf-8")
    assert Path(payload["receipt_path"]).is_file()


def test_install_addon_copies_packaged_plugin(tmp_path: Path):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")

    destination = install_addon(tmp_path)

    assert (destination / "plugin.cfg").is_file()
    assert (destination / "commands.gd").is_file()
    with pytest.raises(FileExistsError):
        install_addon(tmp_path)


def test_install_addon_requires_godot_project(tmp_path: Path):
    with pytest.raises(ValueError, match="project.godot"):
        install_addon(tmp_path)
