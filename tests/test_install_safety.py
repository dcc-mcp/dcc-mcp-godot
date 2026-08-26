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
    real_atomic_write = install_module._atomic_write

    def fail_restore(path: Path, content: str) -> None:
        if path == project_file and PLUGIN_PATH not in content:
            raise PermissionError("restore locked")
        real_atomic_write(path, content)

    monkeypatch.setattr(install_module, "_atomic_write", fail_restore)
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
    godot = tmp_path / "godot"
    godot.touch()
    _allow_preflight(monkeypatch, godot)
    real_replace = install_module.os.replace
    real_write_receipt = install_module._write_receipt
    locked = True

    def lock_config_restore(source: object, destination: object) -> None:
        candidate = Path(source)
        if (
            locked
            and candidate.name.startswith(".project.godot.dcc-mcp-backup-")
            and Path(destination) == project_file
        ):
            raise PermissionError("config restore locked")
        real_replace(source, destination)

    monkeypatch.setattr(install_module.os, "replace", lock_config_restore)
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
    assert backups[0].read_text(encoding="utf-8") == original

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
    assert backups[0].read_text(encoding="utf-8") == original

    locked = False
    assert main(command) == 50
    capsys.readouterr()
    assert not list(tmp_path.glob(".project.godot.dcc-mcp-backup-*"))
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
    real_rmtree = install_module.shutil.rmtree

    def lock_backup(path: object, *args: object, **kwargs: object) -> None:
        if ".backup-" in str(path):
            raise PermissionError("cleanup locked")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(install_module.shutil, "rmtree", lock_backup)

    exit_code = main(["upgrade", *command])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 50
    assert payload["status"] == "requires_restart"
    assert payload["install_state"] == "installed"
    assert payload["verify"]["failure_reason"] == "cleanup_locked"
    assert (tmp_path / ".dcc-mcp" / "receipts" / "godot.json").is_file()
    assert (tmp_path / "addons" / "dcc_mcp_godot" / "plugin.cfg").is_file()
    assert list((tmp_path / "addons").glob(".dcc_mcp_godot.backup-*"))
