import hashlib
import json
import os
from pathlib import Path

import pytest

from dcc_mcp_godot import install as install_module
from dcc_mcp_godot.install import PLUGIN_PATH, main
from dcc_mcp_godot.install_project import plugin_enabled


def _allow_preflight(monkeypatch: pytest.MonkeyPatch, godot: Path) -> None:
    monkeypatch.setattr(
        install_module,
        "_probe_godot",
        lambda _path: {
            "path": str(godot),
            "version": "4.4.1",
            "version_tuple": (4, 4, 1),
        },
    )


def _recovery_original(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload["backup"]["content"])


def test_install_and_uninstall_edit_only_editor_plugins_enabled(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    original = (
        "; res://addons/dcc_mcp_godot/plugin.cfg is documentation only\r\n"
        "[application]\r\n"
        'config/name="Keep"\r\n'
        "\r\n"
        "[editor_plugins] ; keep this section comment\r\n"
        'note = "keep this unrelated field"\r\n'
        'enabled = PackedStringArray("res://addons/user/plugin.cfg") ; keep list comment\r\n'
        "\r\n"
        "[rendering]\r\n"
        'renderer/rendering_method="gl_compatibility"\r\n'
    )
    project_file.write_bytes(original.encode("utf-8"))
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)

    install_exit = main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    install_payload = json.loads(capsys.readouterr().out)

    assert install_exit == 50
    assert install_payload["status"] == "requires_restart"
    installed = project_file.read_bytes().decode("utf-8")
    assert "\n" not in installed.replace("\r\n", "")
    assert 'note = "keep this unrelated field"' in installed
    assert "; keep list comment" in installed
    assert '"res://addons/user/plugin.cfg"' in installed
    assert f'"{PLUGIN_PATH}"' in installed

    uninstall_exit = main(["uninstall", str(tmp_path), "--yes", "--json"])
    uninstall_payload = json.loads(capsys.readouterr().out)

    assert uninstall_exit == 0
    assert uninstall_payload["status"] == "ok"
    assert project_file.read_bytes().decode("utf-8") == original


@pytest.mark.parametrize(
    ("original", "initially_enabled"),
    [
        (
            f'[editor_plugins]\nenabled=PackedStringArray("{PLUGIN_PATH}")\n'
            "enabled=PackedStringArray()\n",
            False,
        ),
        (
            "[editor_plugins]\nenabled=PackedStringArray()\n"
            f'enabled=PackedStringArray("{PLUGIN_PATH}")\n',
            True,
        ),
        (
            f'[editor_plugins]\nenabled=PackedStringArray("{PLUGIN_PATH}")\n'
            '[application]\nconfig/name="Keep"\n'
            "[editor_plugins]\nenabled=PackedStringArray()\n",
            False,
        ),
        (
            "[editor_plugins]\nenabled=PackedStringArray()\n"
            '[application]\nconfig/name="Keep"\n'
            f'[editor_plugins]\nenabled=PackedStringArray("{PLUGIN_PATH}")\n',
            True,
        ),
    ],
)
def test_duplicate_enabled_assignments_follow_godot_last_write_semantics(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    original: str,
    initially_enabled: bool,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text(original, encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)

    assert plugin_enabled(original) is initially_enabled
    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    install_payload = json.loads(capsys.readouterr().out)
    assert install_payload["status"] == "requires_restart"
    assert plugin_enabled(project_file.read_text(encoding="utf-8")) is True

    assert main(["status", str(tmp_path), "--json"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["install_state"] == "installed"

    assert main(["uninstall", str(tmp_path), "--yes", "--json"]) == 0
    capsys.readouterr()
    assert project_file.read_text(encoding="utf-8") == original


def test_uninstall_removes_only_receipt_owned_files_and_preserves_extras(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    extra = tmp_path / "addons" / "dcc_mcp_godot" / "user_notes.txt"
    extra.write_text("not owned by the adapter", encoding="utf-8")

    exit_code = main(["uninstall", str(tmp_path), "--yes", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert extra.read_text(encoding="utf-8") == "not owned by the adapter"
    assert not (extra.parent / "plugin.cfg").exists()


def test_uninstall_dry_run_rejects_traversal_receipt_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    receipt = tmp_path / ".dcc-mcp" / "receipts" / "godot.json"
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["owned_files"][0]["path"] = "../../foreign.txt"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    exit_code = main(["uninstall", str(tmp_path), "--dry-run", "--yes", "--json"])
    result = json.loads(capsys.readouterr().out)
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert exit_code == 30
    assert result["status"] == "failed"
    assert result["verify"]["failure_reason"] == "ownership_conflict"
    assert after == before


def test_upgrade_stage_lock_does_not_rollback_an_unstarted_transaction(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    command = [str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(["install", *command]) == 50
    capsys.readouterr()
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(
        install_module,
        "_stage_addon",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("locked")),
    )

    exit_code = main(["upgrade", *command])
    payload = json.loads(capsys.readouterr().out)
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert exit_code == 50
    assert payload["status"] == "requires_restart"
    assert payload["verify"]["failure_reason"] == "files_locked"
    assert after == before


@pytest.mark.parametrize(
    "corruption",
    (
        "schema_type",
        "schema_version",
        "project_root",
        "destination",
        "traversal",
        "hash",
        "file_tamper",
        "file_missing",
    ),
)
def test_uninstall_fails_closed_for_typed_stale_or_tampered_receipt(
    corruption: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    receipt = tmp_path / ".dcc-mcp" / "receipts" / "godot.json"
    data = json.loads(receipt.read_text(encoding="utf-8"))
    owned = tmp_path / Path(data["owned_files"][0]["path"])
    if corruption == "schema_type":
        data["schema_version"] = "1"
    elif corruption == "schema_version":
        data["schema_version"] = 2
    elif corruption == "project_root":
        data["project_root"] = str(tmp_path / "other-project")
    elif corruption == "destination":
        data["destination"] = str(tmp_path / "addons" / "other")
    elif corruption == "traversal":
        data["owned_files"][0]["path"] = "../../foreign.txt"
    elif corruption == "hash":
        data["owned_files"][0]["sha256"] = "0" * 64
    elif corruption == "file_tamper":
        owned.write_bytes(owned.read_bytes() + b"\ntampered")
    elif corruption == "file_missing":
        owned.unlink()
    if corruption not in {"file_tamper", "file_missing"}:
        receipt.write_text(json.dumps(data), encoding="utf-8")
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    exit_code = main(["uninstall", str(tmp_path), "--yes", "--json"])
    payload = json.loads(capsys.readouterr().out)
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert exit_code == 30
    assert payload["status"] == "failed"
    assert payload["verify"]["failure_reason"] == "missing_or_invalid_receipt"
    assert after == before


def test_uninstall_preserves_preexisting_plugin_enablement(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    original = f'[editor_plugins]\nenabled=PackedStringArray("{PLUGIN_PATH}")\n'
    project_file.write_text(original, encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)

    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    assert main(["uninstall", str(tmp_path), "--yes", "--json"]) == 0
    capsys.readouterr()

    assert project_file.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    "original",
    (
        '[editor_plugins]\nnote="keep"\n',
        "[application]\n",
        "[application]",
    ),
)
def test_install_uninstall_round_trip_restores_created_plugin_structure(
    original: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_bytes(original.encode("utf-8"))
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)

    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    assert main(["uninstall", str(tmp_path), "--yes", "--json"]) == 0
    capsys.readouterr()

    assert project_file.read_bytes() == original.encode("utf-8")


def test_uninstall_preserves_plugin_added_by_user_after_install(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    content = project_file.read_text(encoding="utf-8")
    content = content.replace(
        f'"{PLUGIN_PATH}"',
        f'"{PLUGIN_PATH}", "res://addons/user/plugin.cfg"',
    )
    project_file.write_text(content, encoding="utf-8")

    assert main(["uninstall", str(tmp_path), "--yes", "--json"]) == 0
    capsys.readouterr()

    remaining = project_file.read_text(encoding="utf-8")
    assert PLUGIN_PATH not in remaining
    assert '"res://addons/user/plugin.cfg"' in remaining


def test_uninstall_rejects_receipt_symlink_without_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    receipt = tmp_path / ".dcc-mcp" / "receipts" / "godot.json"
    foreign = tmp_path / "foreign-receipt.json"
    receipt.replace(foreign)
    try:
        os.symlink(foreign, receipt)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    addon = tmp_path / "addons" / "dcc_mcp_godot" / "plugin.cfg"

    exit_code = main(["uninstall", str(tmp_path), "--yes", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 30
    assert payload["verify"]["failure_reason"] == "missing_or_invalid_receipt"
    assert addon.is_file()
    assert receipt.is_symlink()


def test_uninstall_rejects_destination_symlink_without_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    destination = tmp_path / "addons" / "dcc_mcp_godot"
    foreign = tmp_path / "foreign-addon"
    destination.replace(foreign)
    try:
        os.symlink(foreign, destination, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")
    receipt = tmp_path / ".dcc-mcp" / "receipts" / "godot.json"
    before_receipt = receipt.read_bytes()

    exit_code = main(["uninstall", str(tmp_path), "--yes", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 30
    assert payload["verify"]["failure_reason"] == "missing_or_invalid_receipt"
    assert destination.is_symlink()
    assert (foreign / "plugin.cfg").is_file()
    assert receipt.read_bytes() == before_receipt


def test_uninstall_detects_owned_file_swap_before_delete_and_preserves_foreign_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    foreign = tmp_path / "foreign-secret.txt"
    foreign.write_text("must survive", encoding="utf-8")
    held = tmp_path / "attacker-held-file"
    real_replace = install_module.os.replace
    swapped = False

    def swap_before_move(source: object, destination: object) -> None:
        nonlocal swapped
        if not swapped and ".uninstall-" in str(destination) and "owned" in str(destination):
            swapped = True
            real_replace(source, held)
            try:
                os.symlink(foreign, source)
            except OSError as exc:
                real_replace(held, source)
                pytest.skip(f"symlink creation is unavailable: {exc}")
        real_replace(source, destination)

    monkeypatch.setattr(install_module.os, "replace", swap_before_move)

    exit_code = main(["uninstall", str(tmp_path), "--yes", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 30
    assert payload["steps"][0]["error_type"] == "ReceiptError"
    assert foreign.read_text(encoding="utf-8") == "must survive"
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()


def test_upgrade_dry_run_runs_preflight_and_ownership_with_zero_writes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    command = [str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(["install", *command]) == 50
    capsys.readouterr()
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    exit_code = main(["upgrade", *command, "--dry-run"])
    payload = json.loads(capsys.readouterr().out)
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert exit_code == 0
    assert payload["status"] == "planned"
    assert {step["id"]: step["status"] for step in payload["steps"]} == {
        "preflight": "ok",
        "ownership": "ok",
        "upgrade": "planned",
    }
    assert after == before


def test_lifecycle_lock_error_is_json_even_without_json_flag(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    monkeypatch.setattr(
        install_module,
        "_run_install",
        lambda _args: (_ for _ in ()).throw(PermissionError("private path must not leak")),
    )

    exit_code = main(["install", str(tmp_path), "--yes"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 50
    assert payload["status"] == "requires_restart"
    assert payload["verify"]["failure_reason"] == "files_locked"
    assert "private path" not in output


def test_install_rollback_failure_is_structured_and_does_not_mask_primary_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    original = "[application]\n"
    project_file.write_text(original, encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    monkeypatch.setattr(
        install_module,
        "_write_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("primary receipt failure")),
    )

    exit_code = main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert "primary receipt failure" not in output
    assert payload["status"] == "failed"
    assert payload["steps"][1]["error_type"] == "OSError"
    assert payload["steps"][1]["rollback"] == "restored"
    assert payload["verify"]["failure_reason"] == "filesystem_error"
    assert project_file.read_text(encoding="utf-8") == original
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()
    assert not (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").exists()
    assert not list(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))


def test_install_locked_config_restore_is_deferred_with_recoverable_original(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    original = '[application]\nconfig/name="Keep"\n'
    project_file.write_text(original, encoding="utf-8")
    original_on_disk = project_file.read_bytes().decode("utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_restore = install_module._restore_config_backup
    real_write_receipt = install_module._write_receipt
    locked = True

    def lock_config_restore(
        target: Path, backup: Path, expected_project: dict[str, object]
    ) -> None:
        if locked:
            raise PermissionError("config restore locked")
        real_restore(target, backup, expected_project)

    monkeypatch.setattr(install_module, "_restore_config_backup", lock_config_restore)
    monkeypatch.setattr(
        install_module,
        "_write_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("primary receipt failure")),
    )

    exit_code = main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 50
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert "primary receipt failure" not in output
    assert payload["status"] == "requires_restart"
    assert payload["steps"][1]["error_type"] == "OSError"
    assert payload["steps"][1]["rollback"] == "deferred"
    assert payload["verify"]["failure_reason"] == "rollback_locked"
    assert PLUGIN_PATH in project_file.read_text(encoding="utf-8")
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()
    assert not (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").exists()
    backups = list(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    assert len(backups) == 1
    assert _recovery_original(backups[0]) == original_on_disk

    locked = False
    monkeypatch.setattr(install_module, "_write_receipt", real_write_receipt)
    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    assert not list(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()


def test_install_config_backup_cleanup_lock_converges_on_retry(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    original = "[application]\n"
    project_file.write_text(original, encoding="utf-8")
    original_on_disk = project_file.read_bytes().decode("utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_unlink = install_module.Path.unlink
    locked = True

    def lock_config_backup_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        candidate = Path(path)
        if locked and candidate.name.startswith(".project.godot.dcc-mcp-backup-"):
            raise PermissionError("config backup cleanup locked")
        real_unlink(candidate, *args, **kwargs)

    monkeypatch.setattr(install_module.Path, "unlink", lock_config_backup_cleanup)
    command = ["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]

    assert main(command) == 50
    output = capsys.readouterr().out
    first = json.loads(output)
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert first["status"] == "requires_restart"
    assert first.get("install_state") == "installed", first
    assert first["verify"]["failure_reason"] == "cleanup_locked"
    backups = list(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    assert len(backups) == 1
    assert _recovery_original(backups[0]) == original_on_disk

    locked = False
    assert main(command) == 50
    capsys.readouterr()
    assert not list(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()


def test_install_rejects_unbound_foreign_config_backup_without_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    original = '[application]\nconfig/name="Keep"\n'
    project_file.write_text(original, encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    foreign = tmp_path / f".project.godot.dcc-mcp-backup-{'a' * 32}"
    foreign.write_text("USER_FOREIGN_DATA", encoding="utf-8")

    exit_code = main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert payload["status"] == "failed"
    assert payload["verify"]["failure_reason"] == "config_recovery_failed"
    assert project_file.read_text(encoding="utf-8") == original
    assert foreign.read_text(encoding="utf-8") == "USER_FOREIGN_DATA"
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()
    assert not (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").exists()


def test_install_rejects_self_consistent_foreign_recovery_capsule_without_provenance(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text('[application]\nconfig/name="Keep"\n', encoding="utf-8")
    current = project_file.read_bytes()
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    token = "a" * 32
    foreign = "USER_FOREIGN_DATA"
    root_stat = os.lstat(tmp_path)
    payload = {
        "schema_version": 1,
        "type": "dcc-mcp-godot-config-recovery",
        "phase": "project_config_pending",
        "token": token,
        "project_identity": {"device": root_stat.st_dev, "inode": root_stat.st_ino},
        "project_file": "project.godot",
        "backup": {
            "content": foreign,
            "sha256": hashlib.sha256(foreign.encode("utf-8")).hexdigest(),
        },
        "updated_sha256": hashlib.sha256(current).hexdigest(),
    }
    capsule = tmp_path / f".project.godot.dcc-mcp-backup-{token}"
    capsule.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    exit_code = main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    output = capsys.readouterr().out
    result = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert result["status"] == "failed"
    assert result["verify"]["failure_reason"] == "config_recovery_failed"
    assert project_file.read_bytes() == current
    assert capsule.read_text(encoding="utf-8") == json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    )
    assert not list((tmp_path / ".dcc-mcp" / "config-recovery").glob("godot-*.json"))
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()
    assert not (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").exists()


@pytest.mark.parametrize("swap_after_validation", [False, True])
def test_install_rejects_changed_bound_config_backup_without_restoring_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    swap_after_validation: bool,
) -> None:
    project_file = tmp_path / "project.godot"
    original = '[application]\nconfig/name="Keep"\n'
    project_file.write_text(original, encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_restore = install_module._restore_config_backup
    real_write_receipt = install_module._write_receipt
    locked = True

    def lock_config_restore(
        target: Path, backup: Path, expected_project: dict[str, object]
    ) -> None:
        if locked:
            raise PermissionError("config restore locked")
        real_restore(target, backup, expected_project)

    monkeypatch.setattr(install_module, "_restore_config_backup", lock_config_restore)
    monkeypatch.setattr(
        install_module,
        "_write_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("primary receipt failure")),
    )
    command = ["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]

    assert main(command) == 50
    capsys.readouterr()
    backup = next(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    locked = False
    monkeypatch.setattr(install_module, "_write_receipt", real_write_receipt)
    if swap_after_validation:
        real_read = install_module._read_regular_bytes
        swapped = False

        def swap_once_after_read(path: Path, code: str) -> bytes:
            nonlocal swapped
            content = real_read(path, code)
            if path == backup and not swapped:
                backup.write_text("ATTACKER", encoding="utf-8")
                swapped = True
            return content

        monkeypatch.setattr(install_module, "_read_regular_bytes", swap_once_after_read)
    else:
        backup.write_text("ATTACKER", encoding="utf-8")

    exit_code = main(command)
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert payload["status"] == "failed"
    assert payload["verify"]["failure_reason"] == "config_recovery_failed"
    assert PLUGIN_PATH in project_file.read_text(encoding="utf-8")
    assert "ATTACKER" not in project_file.read_text(encoding="utf-8")
    assert backup.read_text(encoding="utf-8") == "ATTACKER"
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()
    assert not (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").exists()


@pytest.mark.parametrize("tamper", ["project_identity", "phase", "backup_digest"])
def test_install_rejects_config_recovery_metadata_binding_tamper(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text('[application]\nconfig/name="Keep"\n', encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_restore = install_module._restore_config_backup
    real_write_receipt = install_module._write_receipt
    monkeypatch.setattr(
        install_module,
        "_restore_config_backup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("restore locked")),
    )
    monkeypatch.setattr(
        install_module,
        "_write_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("primary receipt failure")),
    )
    command = ["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(command) == 50
    capsys.readouterr()
    backup = next(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    payload = json.loads(backup.read_text(encoding="utf-8"))
    if tamper == "project_identity":
        payload["project_identity"]["inode"] += 1
    elif tamper == "phase":
        payload["phase"] = "committed"
    else:
        payload["backup"]["sha256"] = "0" * 64
    backup.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(install_module, "_restore_config_backup", real_restore)
    monkeypatch.setattr(install_module, "_write_receipt", real_write_receipt)

    exit_code = main(command)
    output = capsys.readouterr().out
    result = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert result["status"] == "failed"
    assert result["verify"]["failure_reason"] == "config_recovery_failed"
    assert PLUGIN_PATH in project_file.read_text(encoding="utf-8")
    assert backup.is_file()
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()
    assert not (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").exists()


def test_install_revalidates_project_content_at_recovery_mutation_boundary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text('[application]\nconfig/name="Keep"\n', encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_restore = install_module._restore_config_backup
    real_write_receipt = install_module._write_receipt
    monkeypatch.setattr(
        install_module,
        "_restore_config_backup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("restore locked")),
    )
    monkeypatch.setattr(
        install_module,
        "_write_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("primary receipt failure")),
    )
    command = ["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(command) == 50
    capsys.readouterr()
    backup = next(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    monkeypatch.setattr(install_module, "_restore_config_backup", real_restore)
    monkeypatch.setattr(install_module, "_write_receipt", real_write_receipt)
    real_read = install_module._read_regular_bytes
    swapped = False

    def swap_project_after_initial_read(path: Path, code: str) -> bytes:
        nonlocal swapped
        content = real_read(path, code)
        if path == project_file and not swapped:
            project_file.write_text("USER_FOREIGN_PROJECT", encoding="utf-8")
            swapped = True
        return content

    monkeypatch.setattr(install_module, "_read_regular_bytes", swap_project_after_initial_read)

    exit_code = main(command)
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert payload["status"] == "failed"
    assert payload["verify"]["failure_reason"] == "config_recovery_failed"
    assert project_file.read_text(encoding="utf-8") == "USER_FOREIGN_PROJECT"
    assert backup.is_file()
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()
    assert not (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").exists()


def test_install_rejects_same_bytes_project_identity_swap_after_backup_stage(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text('[application]\nconfig/name="Keep"\n', encoding="utf-8")
    original = project_file.read_bytes()
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_stage = install_module._stage_config_backup
    real_replace = install_module.os.replace

    def stage_then_swap_identity(target: Path, before: str, after: str) -> Path:
        backup = real_stage(target, before, after)
        replacement = target.with_name(".project.godot.foreign-same-bytes")
        replacement.write_bytes(target.read_bytes())
        real_replace(replacement, target)
        return backup

    monkeypatch.setattr(install_module, "_stage_config_backup", stage_then_swap_identity)

    exit_code = main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert payload["status"] == "failed"
    assert project_file.read_bytes() == original
    assert len(list(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))) == 1
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()
    assert not (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").exists()


def test_install_rejects_same_bytes_project_identity_swap_before_restore_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text('[application]\nconfig/name="Keep"\n', encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_restore = install_module._restore_config_backup
    real_write_receipt = install_module._write_receipt
    monkeypatch.setattr(
        install_module,
        "_restore_config_backup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("restore locked")),
    )
    monkeypatch.setattr(
        install_module,
        "_write_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("primary receipt failure")),
    )
    command = ["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(command) == 50
    capsys.readouterr()
    updated = project_file.read_bytes()
    backup = next(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    monkeypatch.setattr(install_module, "_write_receipt", real_write_receipt)
    real_replace = install_module.os.replace

    def swap_identity_then_restore(*args: object, **kwargs: object) -> None:
        replacement = project_file.with_name(".project.godot.foreign-same-bytes")
        replacement.write_bytes(project_file.read_bytes())
        real_replace(replacement, project_file)
        real_restore(*args, **kwargs)

    monkeypatch.setattr(install_module, "_restore_config_backup", swap_identity_then_restore)

    exit_code = main(command)
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert payload["status"] == "failed"
    assert payload["verify"]["failure_reason"] == "config_recovery_failed"
    assert project_file.read_bytes() == updated
    assert backup.is_file()
    assert not (tmp_path / "addons" / "dcc_mcp_godot").exists()
    assert not (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").exists()


def test_install_cleanup_claim_rejects_swap_after_validation_without_deleting_foreign_data(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_unlink = install_module.Path.unlink
    cleanup_locked = True

    def lock_initial_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        if cleanup_locked and path.name.startswith(".project.godot.dcc-mcp-backup-"):
            raise PermissionError("config backup cleanup locked")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(install_module.Path, "unlink", lock_initial_cleanup)
    command = ["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(command) == 50
    capsys.readouterr()
    backup = next(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    cleanup_locked = False
    real_replace = install_module.os.replace
    swapped = False

    def swap_at_cleanup_claim(source: object, destination: object) -> None:
        nonlocal swapped
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path == backup and ".claim-" in destination_path.name and not swapped:
            backup.write_text("USER_FOREIGN_DATA", encoding="utf-8")
            swapped = True
        real_replace(source, destination)

    monkeypatch.setattr(install_module.os, "replace", swap_at_cleanup_claim)

    exit_code = main(command)
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert payload["status"] == "failed"
    assert payload["verify"]["failure_reason"] == "config_recovery_failed"
    assert PLUGIN_PATH in project_file.read_text(encoding="utf-8")
    assert backup.read_text(encoding="utf-8") == "USER_FOREIGN_DATA"
    assert (tmp_path / "addons" / "dcc_mcp_godot").is_dir()
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()
    assert not list(tmp_path.glob("*.claim-*"))


def test_install_cleanup_recaptures_claim_before_unlink(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_unlink = install_module.Path.unlink
    cleanup_locked = True

    def lock_initial_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        if cleanup_locked and path.name.startswith(".project.godot.dcc-mcp-backup-"):
            raise PermissionError("config backup cleanup locked")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(install_module.Path, "unlink", lock_initial_cleanup)
    command = ["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(command) == 50
    capsys.readouterr()
    backup = next(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    cleanup_locked = False
    real_load = install_module._load_config_recovery
    swapped = False

    def swap_claim_after_first_validation(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal swapped
        record = real_load(*args, **kwargs)
        candidate = Path(args[1])
        if ".claim-" in candidate.name and not swapped:
            candidate.write_text("USER_FOREIGN_DATA", encoding="utf-8")
            swapped = True
        return record

    monkeypatch.setattr(install_module, "_load_config_recovery", swap_claim_after_first_validation)

    exit_code = main(command)
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert len(output) < 4096
    assert payload["status"] == "failed"
    assert payload["verify"]["failure_reason"] == "config_recovery_failed"
    assert backup.read_text(encoding="utf-8") == "USER_FOREIGN_DATA"
    assert not list(tmp_path.glob("*.claim-*"))
    assert (tmp_path / "addons" / "dcc_mcp_godot").is_dir()
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()


def test_install_cleanup_claim_preserves_exact_hostile_base_exception(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HostileSystemExit(SystemExit):
        def __str__(self) -> str:
            raise AssertionError("must not render")

    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_unlink = install_module.Path.unlink
    cleanup_locked = True

    def cleanup_boundary(path: Path, *args: object, **kwargs: object) -> None:
        if path.name.startswith(".project.godot.dcc-mcp-backup-"):
            if cleanup_locked:
                raise PermissionError("config backup cleanup locked")
            raise primary
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(install_module.Path, "unlink", cleanup_boundary)
    command = ["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(command) == 50
    capsys.readouterr()
    backup = next(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    cleanup_locked = False
    primary = HostileSystemExit()
    real_replace = install_module.os.replace

    def fail_claim_rollback(source: object, destination: object) -> None:
        if ".claim-" in Path(source).name and Path(destination) == backup:
            raise KeyboardInterrupt("secondary rollback failure")
        real_replace(source, destination)

    monkeypatch.setattr(install_module.os, "replace", fail_claim_rollback)

    with pytest.raises(HostileSystemExit) as raised:
        main(command)

    assert raised.value is primary
    assert capsys.readouterr().out == ""
    claims = list(tmp_path.glob(".project.godot.dcc-mcp-backup-*.claim-*"))
    assert len(claims) == 1
    assert not backup.exists()
    provenance = list((tmp_path / ".dcc-mcp" / "config-recovery").glob("godot-*.json"))
    assert len(provenance) == 1

    monkeypatch.setattr(install_module.Path, "unlink", real_unlink)
    monkeypatch.setattr(install_module.os, "replace", real_replace)
    assert main(command) == 50
    capsys.readouterr()
    assert not list(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    assert not list((tmp_path / ".dcc-mcp" / "config-recovery").glob("godot-*.json"))


def test_uninstall_rejects_user_project_save_before_disable_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    command = [str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(["install", *command]) == 50
    capsys.readouterr()
    installed = project_file.read_text(encoding="utf-8")
    user_saved = installed + "\n[display]\nwindow/size/viewport_width=1440\n"
    real_disable = install_module._disable_plugin

    def disable_after_user_save(content: str, action: str) -> str:
        updated = real_disable(content, action)
        project_file.write_text(user_saved, encoding="utf-8")
        return updated

    monkeypatch.setattr(install_module, "_disable_plugin", disable_after_user_save)

    exit_code = main(["uninstall", str(tmp_path), "--yes", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert payload["status"] == "failed"
    assert project_file.read_text(encoding="utf-8") == user_saved
    assert plugin_enabled(user_saved)
    assert (tmp_path / "addons" / "dcc_mcp_godot" / "plugin.cfg").is_file()
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()


def test_uninstall_rejects_user_save_after_validation_before_replace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    command = [str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(["install", *command]) == 50
    capsys.readouterr()
    installed = project_file.read_text(encoding="utf-8")
    user_saved = installed + "\n[display]\nwindow/size/viewport_width=1728\n"
    real_atomic_write = install_module._atomic_write
    injected = False

    def save_at_real_mutation_boundary(path: Path, content: str, **kwargs: object) -> None:
        nonlocal injected
        if path == project_file and not injected:
            project_file.write_text(user_saved, encoding="utf-8")
            injected = True
        real_atomic_write(path, content, **kwargs)

    monkeypatch.setattr(install_module, "_atomic_write", save_at_real_mutation_boundary)

    exit_code = main(["uninstall", str(tmp_path), "--yes", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert injected
    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert payload["status"] == "failed"
    assert project_file.read_text(encoding="utf-8") == user_saved
    assert (tmp_path / "addons" / "dcc_mcp_godot" / "plugin.cfg").is_file()
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()


def test_uninstall_rollback_preserves_user_project_save_after_disable_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    command = [str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(["install", *command]) == 50
    capsys.readouterr()
    receipt = tmp_path / ".dcc-mcp" / "receipts" / "godot.json"
    real_replace = install_module.os.replace
    user_saved = ""

    def save_then_fail_receipt_move(source: object, destination: object) -> None:
        nonlocal user_saved
        if Path(source) == receipt and ".uninstall-" in str(destination):
            user_saved = (
                project_file.read_text(encoding="utf-8")
                + "\n[display]\nwindow/size/viewport_height=900\n"
            )
            project_file.write_text(user_saved, encoding="utf-8")
            raise OSError("receipt move failed")
        real_replace(source, destination)

    monkeypatch.setattr(install_module.os, "replace", save_then_fail_receipt_move)

    exit_code = main(["uninstall", str(tmp_path), "--yes", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert payload["status"] == "failed"
    assert payload["steps"][0]["rollback"] == "incomplete"
    assert project_file.read_text(encoding="utf-8") == user_saved
    assert receipt.is_file()
    assert (tmp_path / "addons" / "dcc_mcp_godot" / "plugin.cfg").is_file()


def test_upgrade_rollback_preserves_user_file_created_after_staging(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    command = [str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(["install", *command]) == 50
    capsys.readouterr()
    destination = tmp_path / "addons" / "dcc_mcp_godot"
    late_file = destination / "USER_LATE_NOTES.txt"

    def fail_receipt_after_user_file(*_args: object, **_kwargs: object) -> Path:
        late_file.write_text("USER_LATE_DATA", encoding="utf-8")
        raise OSError("receipt write failed")

    monkeypatch.setattr(install_module, "_write_receipt", fail_receipt_after_user_file)

    exit_code = main(["upgrade", *command])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert payload["status"] == "failed"
    assert payload["steps"][1]["rollback"] == "restored"
    assert late_file.read_text(encoding="utf-8") == "USER_LATE_DATA"
    assert (destination / "plugin.cfg").is_file()
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()


def test_committed_install_cleanup_preserves_later_user_project_save(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_unlink = install_module.Path.unlink
    cleanup_locked = True

    def lock_config_capsule(path: Path, *args: object, **kwargs: object) -> None:
        if cleanup_locked and path.name.startswith(".project.godot.dcc-mcp-backup-"):
            raise PermissionError("config cleanup locked")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(install_module.Path, "unlink", lock_config_capsule)
    command = ["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(command) == 50
    first = json.loads(capsys.readouterr().out)
    assert first["verify"]["failure_reason"] == "cleanup_locked"
    assert list(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    user_saved = (
        project_file.read_text(encoding="utf-8") + "\n[display]\nwindow/size/viewport_width=1600\n"
    )
    project_file.write_text(user_saved, encoding="utf-8")
    cleanup_locked = False

    exit_code = main(command)
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 50
    assert len(output.splitlines()) == 1
    assert payload["status"] == "requires_restart"
    assert project_file.read_text(encoding="utf-8") == user_saved
    assert not list(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
    assert not list((tmp_path / ".dcc-mcp" / "config-recovery").glob("godot-*.json"))
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()


def test_upgrade_cleanup_rejects_same_name_backup_replacement(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    command = [str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(["install", *command]) == 50
    capsys.readouterr()
    addons = tmp_path / "addons"
    real_rmtree = install_module.shutil.rmtree
    real_replace = install_module.os.replace
    real_backup: Path | None = None
    foreign_backup: Path | None = None
    swapped = False

    def swap_backup(path: Path) -> None:
        nonlocal real_backup, foreign_backup, swapped
        if swapped:
            return
        real_backup = path.with_name(f".{path.name}.recoverable")
        real_replace(path, real_backup)
        path.mkdir()
        (path / "USER_FOREIGN_DATA.txt").write_text("USER_FOREIGN_DATA", encoding="utf-8")
        foreign_backup = path
        swapped = True

    def swap_before_path_cleanup(path: object, *args: object, **kwargs: object) -> None:
        candidate = Path(path)
        if candidate.parent == addons and ".backup-" in candidate.name:
            swap_backup(candidate)
        real_rmtree(candidate, *args, **kwargs)

    def swap_before_cleanup_claim(source: object, destination: object) -> None:
        candidate = Path(source)
        if (
            candidate.parent == addons
            and ".backup-" in candidate.name
            and ".cleanup-" in Path(destination).name
        ):
            swap_backup(candidate)
        real_replace(source, destination)

    monkeypatch.setattr(install_module.shutil, "rmtree", swap_before_path_cleanup)
    monkeypatch.setattr(install_module.os, "replace", swap_before_cleanup_claim)

    exit_code = main(["upgrade", *command])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert swapped
    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert payload["status"] == "failed"
    assert payload["verify"]["failure_reason"] == "cleanup_failed"
    assert foreign_backup is not None
    assert (foreign_backup / "USER_FOREIGN_DATA.txt").read_text(encoding="utf-8") == (
        "USER_FOREIGN_DATA"
    )
    assert real_backup is not None and (real_backup / "plugin.cfg").is_file()
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()


def test_upgrade_cleanup_rejects_claim_replacement_after_second_validation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "project.godot"
    project_file.write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    command = [str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(["install", *command]) == 50
    capsys.readouterr()
    real_assert = install_module._cleanup_addon_backup.__globals__["_assert_tree_binding"]
    real_replace = install_module.os.replace
    real_backup: Path | None = None
    foreign_claim: Path | None = None
    swapped = False

    def swap_after_claim_validation(path: Path, expected: dict[str, object]) -> None:
        nonlocal real_backup, foreign_claim, swapped
        real_assert(path, expected)
        if ".cleanup-" not in path.name or swapped:
            return
        real_backup = path.with_name(f".{path.name}.recoverable")
        real_replace(path, real_backup)
        path.mkdir()
        (path / "USER_FOREIGN_DATA.txt").write_text("USER_FOREIGN_DATA", encoding="utf-8")
        foreign_claim = path
        swapped = True

    monkeypatch.setitem(
        install_module._cleanup_addon_backup.__globals__,
        "_assert_tree_binding",
        swap_after_claim_validation,
    )

    exit_code = main(["upgrade", *command])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert swapped
    assert exit_code == 30
    assert len(output.splitlines()) == 1
    assert payload["status"] == "failed"
    assert payload["verify"]["failure_reason"] == "cleanup_failed"
    assert foreign_claim is not None
    preserved_foreign = [
        path
        for path in (tmp_path / "addons").iterdir()
        if (path / "USER_FOREIGN_DATA.txt").is_file()
    ]
    assert len(preserved_foreign) == 1
    assert (preserved_foreign[0] / "USER_FOREIGN_DATA.txt").read_text(
        encoding="utf-8"
    ) == "USER_FOREIGN_DATA"
    assert real_backup is not None and (real_backup / "plugin.cfg").is_file()
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()


def test_uninstall_lock_rolls_back_and_returns_json_restart_deferral(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    real_replace = install_module.os.replace

    def lock_first_owned(source: object, destination: object) -> None:
        if ".uninstall-" in str(destination) and "owned" in str(destination):
            raise PermissionError("locked")
        real_replace(source, destination)

    monkeypatch.setattr(install_module.os, "replace", lock_first_owned)

    exit_code = main(["uninstall", str(tmp_path), "--yes", "--json"])
    payload = json.loads(capsys.readouterr().out)
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert exit_code == 50
    assert payload["status"] == "requires_restart"
    assert payload["verify"]["failure_reason"] == "files_locked"
    assert after == before


def test_uninstall_cleanup_lock_reports_committed_absent_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    assert main(["install", str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]) == 50
    capsys.readouterr()
    real_rmtree = install_module.shutil.rmtree

    def lock_backup(path: object, *args: object, **kwargs: object) -> None:
        if ".uninstall-" in str(path):
            raise PermissionError("cleanup locked")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(install_module.shutil, "rmtree", lock_backup)

    exit_code = main(["uninstall", str(tmp_path), "--yes", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 50
    assert payload["status"] == "requires_restart"
    assert payload["install_state"] == "absent"
    assert payload["verify"]["failure_reason"] == "cleanup_locked"
    assert not (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").exists()
    assert not (tmp_path / "addons" / "dcc_mcp_godot" / "plugin.cfg").exists()
    assert list((tmp_path / "addons").glob(".dcc_mcp_godot.uninstall-*"))


def test_upgrade_cleanup_lock_reports_committed_installed_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    command = [str(tmp_path), "--dcc-path", str(godot), "--yes", "--json"]
    assert main(["install", *command]) == 50
    capsys.readouterr()
    cleanup_globals = install_module._cleanup_addon_backup.__globals__
    real_remove_bound_tree = cleanup_globals["_remove_bound_tree"]

    def lock_backup(path: Path, binding: dict[str, object]) -> None:
        if ".cleanup-" in path.name:
            raise PermissionError("cleanup locked")
        real_remove_bound_tree(path, binding)

    monkeypatch.setitem(cleanup_globals, "_remove_bound_tree", lock_backup)

    exit_code = main(["upgrade", *command])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 50
    assert payload["status"] == "requires_restart"
    assert payload["install_state"] == "installed"
    assert payload["verify"]["failure_reason"] == "cleanup_locked"
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()
    assert (tmp_path / "addons" / "dcc_mcp_godot" / "plugin.cfg").is_file()
    assert list((tmp_path / "addons").glob(".dcc_mcp_godot.backup-*"))
