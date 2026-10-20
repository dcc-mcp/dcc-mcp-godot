"""Short adapter contracts; none of these tests starts an export child."""

from unittest.mock import Mock

import pytest

from dcc_mcp_godot import capability_dispatch as dispatch


def test_start_obtains_short_native_context_only(monkeypatch):
    context = {"project_path": "/fixture"}
    host = Mock(return_value=context)
    manager = Mock()
    manager.start.return_value = {"status": "queued", "job_id": "a" * 32}
    monkeypatch.setattr(dispatch, "call_host", host)
    monkeypatch.setattr(dispatch, "export_job_manager", lambda: manager)
    params = {"request_id": "a" * 32, "preset": "Web", "path": "output/index.html"}
    dispatch.dispatch("start_export_job", params)
    host.assert_called_once_with("capability.get_export_job_context", {})
    manager.start.assert_called_once_with(params, context)


@pytest.mark.parametrize(
    "action,method", [("get_export_job", "get"), ("cancel_export_job", "cancel")]
)
def test_status_and_cancel_do_not_require_connected_editor(monkeypatch, action, method):
    host = Mock(side_effect=AssertionError("must not call editor"))
    manager = Mock()
    getattr(manager, method).return_value = {"status": "unknown", "job_id": "a" * 32}
    monkeypatch.setattr(dispatch, "call_host", host)
    monkeypatch.setattr(dispatch, "export_job_manager", lambda: manager)
    dispatch.dispatch(action, {"job_id": "a" * 32})
    getattr(manager, method).assert_called_once_with("a" * 32)
    host.assert_not_called()
    with pytest.raises(ValueError, match="Only job_id"):
        dispatch.dispatch(action, {"job_id": "a" * 32, "pid": 123})


def test_native_context_error_never_starts_child(monkeypatch):
    manager = Mock()
    monkeypatch.setattr(dispatch, "export_job_manager", lambda: manager)
    monkeypatch.setattr(dispatch, "call_host", lambda *args: {"error": "scan active"})
    with pytest.raises(ValueError, match="scan active"):
        dispatch.dispatch("start_export_job", {})
    manager.start.assert_not_called()


def test_configuration_failure_cleans_started_bridge_not_foreign_manager(monkeypatch):
    from types import SimpleNamespace

    from dcc_mcp_godot import server

    instance = object.__new__(server.GodotMcpServer)
    instance._export_jobs_directory = "/fixture/journal"
    instance._context_monitor = SimpleNamespace(stop=Mock())
    instance._readiness_monitor = SimpleNamespace(stop=Mock())
    instance._host_driver = SimpleNamespace(stop=Mock())
    start = Mock()
    stop = Mock()
    shutdown = Mock()
    monkeypatch.setattr(server, "start_bridge", start)
    monkeypatch.setattr(server, "stop_bridge", stop)
    monkeypatch.setattr(server, "shutdown_export_jobs", shutdown)
    monkeypatch.setattr(server, "configure_export_jobs", Mock(side_effect=RuntimeError("injected")))
    with pytest.raises(RuntimeError, match="injected"):
        instance.start()
    start.assert_called_once()
    stop.assert_called_once()
    shutdown.assert_not_called()
