"""Tests for the unattended Godot host launcher.

The Windows private-desktop path is exercised only on Windows; elsewhere the
launcher must degrade to the plain mode rather than pretending to isolate.
"""

from __future__ import annotations

import sys

import pytest

from dcc_mcp_godot import unattended
from dcc_mcp_godot.unattended import (
    HIDE_WINDOW_ARG,
    MODE_PLAIN,
    MODE_PRIVATE_DESKTOP,
    LaunchRequest,
    build_editor_command,
    resolve_mode,
)


def _request(**overrides) -> LaunchRequest:
    options = {
        "godot": "godot",
        "project": "/tmp/project",
    }
    options.update(overrides)
    return LaunchRequest(**options)


def test_windowed_command_replaces_headless_with_a_hidden_window() -> None:
    command = build_editor_command(_request())

    # The whole point of route A: no --headless, because it degrades Godot to
    # rendering/dummy where nothing can be read back.
    assert "--headless" not in command
    assert command[:3] == ["godot", "--path", "/tmp/project"]
    assert "--editor" in command
    assert command[-1] == HIDE_WINDOW_ARG


def test_user_arguments_are_separated_by_a_bare_double_dash() -> None:
    # Without the separator Godot consumes them as engine arguments and the
    # host addon never sees them.
    command = build_editor_command(_request(extra_args=["--probe-mode=ci"]))

    assert "--" in command
    separator = command.index("--")
    assert "--probe-mode=ci" in command[separator:]
    assert HIDE_WINDOW_ARG in command[separator:]


def test_hide_window_can_be_disabled_for_debugging() -> None:
    command = build_editor_command(_request(hide_window=False))

    assert HIDE_WINDOW_ARG not in command


def test_private_desktop_is_only_used_where_it_is_supported(monkeypatch) -> None:
    monkeypatch.setattr(unattended, "supports_private_desktop", lambda: False)

    assert resolve_mode(_request()) == MODE_PLAIN


def test_private_desktop_can_be_declined_even_when_supported(monkeypatch) -> None:
    monkeypatch.setattr(unattended, "supports_private_desktop", lambda: True)

    assert resolve_mode(_request(private_desktop=False)) == MODE_PLAIN


def test_private_desktop_is_selected_when_supported(monkeypatch) -> None:
    monkeypatch.setattr(unattended, "supports_private_desktop", lambda: True)

    assert resolve_mode(_request()) == MODE_PRIVATE_DESKTOP


@pytest.mark.skipif(sys.platform != "win32", reason="private desktops are Windows-only")
def test_windows_reports_private_desktop_support() -> None:
    assert unattended.supports_private_desktop() is True


def test_launch_result_serializes_for_a_receipt() -> None:
    result = unattended.LaunchResult(
        mode=MODE_PLAIN, command=["godot"], exit_code=0, timed_out=False
    )

    assert result.as_dict() == {
        "mode": MODE_PLAIN,
        "command": ["godot"],
        "exit_code": 0,
        "timed_out": False,
    }


def test_plain_launch_does_not_minimize_and_reports_its_mode() -> None:
    # Minimizing under gl_compatibility reports success with a black frame, so
    # hiding is delegated to the host addon via the environment only.
    captured: dict[str, object] = {}

    class _Completed:
        returncode = 0

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return _Completed()

    request = _request(private_desktop=False)
    monkeypatch_target = unattended.subprocess.run
    try:
        unattended.subprocess.run = fake_run  # type: ignore[assignment]
        result = unattended.launch_host(request)
    finally:
        unattended.subprocess.run = monkeypatch_target  # type: ignore[assignment]

    assert result.mode == MODE_PLAIN
    assert result.exit_code == 0
    assert captured["command"] == build_editor_command(request)
    assert captured["env"][unattended.HIDE_WINDOW_ENV] == "1"


def test_cli_unattended_reports_the_mode_it_used(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_launch_host(request):
        captured["request"] = request
        return unattended.LaunchResult(mode=MODE_PLAIN, command=[], exit_code=7)

    monkeypatch.setattr(unattended, "launch_host", fake_launch_host)

    exit_code = unattended.main(
        ["--godot", "godot", "--project", "/tmp/project", "--no-private-desktop"]
    )

    assert exit_code == 7
    assert "mode=plain exit_code=7" in capsys.readouterr().out
    request = captured["request"]
    assert request.private_desktop is False
    assert request.hide_window is True
