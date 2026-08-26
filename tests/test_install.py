import importlib
import json
import subprocess
from pathlib import Path

import pytest

from dcc_mcp_godot import install as install_module
from dcc_mcp_godot import install_verify
from dcc_mcp_godot.install import PLUGIN_PATH, install_addon, main


def test_standard_install_dry_run_returns_plan_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {"path": str(godot), "version": "4.4.1", "version_tuple": (4, 4, 1)},
    )

    exit_code = main(
        [
            "install",
            str(tmp_path),
            "--dcc-path",
            str(godot),
            "--dry-run",
            "--yes",
            "--json",
        ]
    )

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


def test_status_reports_a_complete_receipt_owned_install(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {"path": str(godot), "version": "4.4.1", "version_tuple": (4, 4, 1)},
    )
    main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    capsys.readouterr()

    exit_code = main(["status", str(tmp_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["install_state"] == "installed"
    assert payload["verify"]["directly_usable"] is False


def test_verify_fails_closed_when_no_live_godot_instance_is_ready(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {"path": str(godot), "version": "4.4.1", "version_tuple": (4, 4, 1)},
    )
    main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    capsys.readouterr()

    monkeypatch.setattr(
        install_verify,
        "run_probe_command",
        lambda command: subprocess.CompletedProcess(command, 0, "", ""),
    )
    monkeypatch.setattr(
        install_verify,
        "query_runtime_state",
        lambda *_args, **_kwargs: {
            "entries": [
                {
                    "dcc_type": "godot",
                    "instance_id": "idle-instance",
                    "mcp_url": "http://idle-instance/mcp",
                }
            ]
        },
    )
    monkeypatch.setattr(
        install_verify,
        "_call_core_tool",
        lambda *_args, **_kwargs: {
            "success": False,
            "status": "probe_failed",
            "message": "no ready instance",
        },
    )

    exit_code = main(["verify", str(tmp_path), "--json"])

    assert exit_code == 40
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["verify"] == {
        "directly_usable": False,
        "failure_stage": "readiness",
        "failure_reason": "no ready instance",
    }


def test_verify_binds_the_typed_ping_to_the_matching_project_instance(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {"path": str(godot), "version": "4.4.1", "version_tuple": (4, 4, 1)},
    )
    main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    capsys.readouterr()

    monkeypatch.setattr(
        install_verify,
        "run_probe_command",
        lambda command: subprocess.CompletedProcess(command, 0, "", ""),
    )
    monkeypatch.setattr(
        install_verify,
        "query_runtime_state",
        lambda *_args, **_kwargs: {
            "entries": [
                {
                    "dcc_type": "godot",
                    "instance_id": "wrong-instance",
                    "mcp_url": "http://wrong-instance/mcp",
                },
                {
                    "dcc_type": "godot",
                    "instance_id": "right-instance",
                    "mcp_url": "http://right-instance/mcp",
                },
            ]
        },
    )

    def probe(url: str, tool: str, _arguments: object, **_kwargs: object) -> dict[str, object]:
        if tool.endswith("get_project_info"):
            project_path = str(tmp_path if "right-instance" in url else tmp_path / "other")
            return {
                "success": True,
                "result": {"structuredContent": {"context": {"project_path": project_path}}},
            }
        return {"success": True, "result": {}}

    monkeypatch.setattr(install_verify, "_call_core_tool", probe, raising=False)

    exit_code = main(["verify", str(tmp_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verify"]["directly_usable"] is True
    assert payload["instance_id"] == "right-instance"


def test_verify_uses_core_readiness_when_external_cli_is_absent(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {"path": str(godot), "version": "4.4.1", "version_tuple": (4, 4, 1)},
    )
    main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    capsys.readouterr()
    monkeypatch.setattr(
        install_verify,
        "run_probe_command",
        lambda command: subprocess.CompletedProcess(command, 0, "", ""),
    )
    registry_attempts: list[int] = []

    def query_registry(*_args: object, **_kwargs: object) -> dict[str, object]:
        registry_attempts.append(1)
        if len(registry_attempts) == 1:
            raise PermissionError("registry is briefly locked")
        return {
            "entries": [
                {
                    "dcc_type": "godot",
                    "role": "runtime",
                    "instance_id": "godot-instance",
                    "mcp_url": "http://127.0.0.1:1/mcp",
                }
            ]
        }

    monkeypatch.setattr(install_verify, "query_runtime_state", query_registry)

    def probe(_url: str, tool: str, _arguments: object, **_kwargs: object) -> dict[str, object]:
        if tool.endswith("get_project_info"):
            return {
                "success": True,
                "result": {"structuredContent": {"context": {"project_path": str(tmp_path)}}},
            }
        return {"success": True, "result": {}}

    monkeypatch.setattr(install_verify, "_call_core_tool", probe, raising=False)

    exit_code = main(["verify", str(tmp_path), "--instance-id", "godot-instance", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verify"]["directly_usable"] is True
    assert payload["instance_id"] == "godot-instance"
    assert len(registry_attempts) == 2


def test_uninstall_consumes_receipt_and_preserves_unowned_project_content(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    project_file = tmp_path / "project.godot"
    project_file.write_text('[application]\nconfig/name="Keep me"\n', encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {"path": str(godot), "version": "4.4.1", "version_tuple": (4, 4, 1)},
    )
    main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    capsys.readouterr()
    unrelated = tmp_path / "addons" / "user_addon" / "plugin.cfg"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("[plugin]\n", encoding="utf-8")

    exit_code = main(["uninstall", str(tmp_path), "--yes", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()
    assert not (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").exists()
    assert unrelated.is_file()
    config = project_file.read_text(encoding="utf-8")
    assert 'config/name="Keep me"' in config
    assert PLUGIN_PATH not in config


def test_upgrade_replaces_owned_files_while_preserving_unowned_extras(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {"path": str(godot), "version": "4.4.1", "version_tuple": (4, 4, 1)},
    )
    command = [str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    main(["install", *command])
    capsys.readouterr()
    stale = tmp_path / "addons" / "dcc_mcp_godot" / "removed_in_upgrade.gd"
    stale.write_text("stale", encoding="utf-8")

    exit_code = main(["upgrade", *command])

    assert exit_code == 50
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "requires_restart"
    assert stale.read_text(encoding="utf-8") == "stale"
    assert (tmp_path / "addons" / "dcc_mcp_godot" / "plugin.cfg").is_file()


def test_mutating_lifecycle_requires_explicit_yes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")

    exit_code = main(["install", str(tmp_path), "--json"])

    assert exit_code == 10
    payload = json.loads(capsys.readouterr().out)
    assert payload["verify"]["failure_reason"] == "confirmation_required"
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()


def test_uninstall_dry_run_is_zero_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {"path": str(godot), "version": "4.4.1", "version_tuple": (4, 4, 1)},
    )
    main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    capsys.readouterr()

    exit_code = main(["uninstall", str(tmp_path), "--dry-run", "--yes", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "planned"
    assert (tmp_path / "addons" / "dcc_mcp_godot" / "plugin.cfg").is_file()
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()


def test_unowned_partial_install_fails_closed_without_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    partial = tmp_path / "addons" / "dcc_mcp_godot"
    partial.mkdir(parents=True)
    (partial / "stale.gd").write_text("stale", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {"path": str(godot), "version": "4.4.1", "version_tuple": (4, 4, 1)},
    )

    exit_code = main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])

    assert exit_code == 30
    payload = json.loads(capsys.readouterr().out)
    assert payload["verify"]["failure_reason"] == "ownership_conflict"
    assert (partial / "stale.gd").read_text(encoding="utf-8") == "stale"
    assert not (partial / "plugin.cfg").exists()


def test_preflight_checks_the_selected_python_floor_before_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    python = tmp_path / "python"
    godot.touch()
    python.touch()

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == str(godot.resolve()):
            return subprocess.CompletedProcess(command, 0, "4.4.1.stable\n", "")
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"python": "3.8.18", "core": "0.20.11"}) + "\n",
            "",
        )

    monkeypatch.setattr(install_module.subprocess, "run", run)

    exit_code = main(
        [
            "install",
            str(tmp_path),
            "--dcc-path",
            str(godot),
            "--python",
            str(python),
            "--yes",
            "--json",
        ]
    )

    assert exit_code == 10
    payload = json.loads(capsys.readouterr().out)
    assert payload["verify"]["failure_reason"] == "preflight_failed"
    assert payload["steps"][0]["error_type"] == "ValueError"
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()


def test_failed_receipt_commit_rolls_back_addon_and_project_settings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    project_file = tmp_path / "project.godot"
    original = '[application]\nconfig/name="Rollback"\n'
    project_file.write_text(original, encoding="utf-8")
    destination = tmp_path / "addons" / "dcc_mcp_godot"
    destination.mkdir(parents=True)
    legacy = destination / "legacy.gd"
    legacy.write_text("keep", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {"path": str(godot), "version": "4.4.1", "version_tuple": (4, 4, 1)},
    )
    monkeypatch.setattr(
        install_module,
        "_write_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("receipt failed")),
    )

    exit_code = main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])

    assert exit_code == 30
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert legacy.read_text(encoding="utf-8") == "keep"
    assert not (destination / "plugin.cfg").exists()
    assert project_file.read_text(encoding="utf-8") == original


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
