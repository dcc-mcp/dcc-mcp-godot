import asyncio
import json
import os
import socket
import time

import pytest

from dcc_mcp_godot import bridge
from dcc_mcp_godot.readiness import BridgeReadinessMonitor


class FakeBridge:
    def call(self, method, **params):
        return {"method": method, "params": params}


def test_call_host_uses_typed_method_and_parameters(monkeypatch):
    monkeypatch.setattr(bridge, "_bridge", FakeBridge())
    assert bridge.call_host("scene.inspect", {"depth": 2}) == {
        "method": "scene.inspect",
        "params": {"depth": 2},
    }


def test_call_host_preserves_public_target_method_without_colliding_with_bridge_method(
    monkeypatch,
):
    monkeypatch.setattr(bridge, "_bridge", FakeBridge())

    assert bridge.call_host(
        "capability.execute_editor_script", {"method": "run", "arguments": {}}
    ) == {
        "method": "capability.execute_editor_script",
        "params": {"__method__": "run", "arguments": {}},
    }


def test_typed_action_observes_cancellation_before_host_dispatch(monkeypatch):
    from dcc_mcp_godot import capability_dispatch

    host_calls = []

    def cancelled():
        raise RuntimeError("cancelled-before-host-dispatch")

    monkeypatch.setattr(capability_dispatch, "check_dcc_cancelled", cancelled, raising=False)
    monkeypatch.setattr(
        capability_dispatch,
        "call_host",
        lambda *args, **kwargs: host_calls.append((args, kwargs)) or {},
    )

    with pytest.raises(RuntimeError, match="cancelled-before-host-dispatch"):
        capability_dispatch.dispatch("execute_typed_action", {})
    assert host_calls == []


def test_typed_action_rechecks_cancellation_before_reserved_mutation(monkeypatch):
    from dcc_mcp_godot import capability_dispatch

    checks = 0
    host_methods = []

    def cancelled_at_boundary():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise RuntimeError("cancelled-at-host-boundary")

    def call_host(method, _params):
        host_methods.append(method)
        return {"reservation_id": "review-reservation"}

    monkeypatch.setattr(
        capability_dispatch,
        "check_dcc_cancelled",
        cancelled_at_boundary,
        raising=False,
    )
    monkeypatch.setattr(capability_dispatch, "call_host", call_host)

    with pytest.raises(RuntimeError, match="cancelled-at-host-boundary"):
        capability_dispatch.dispatch("execute_typed_action", {})
    assert host_methods == [
        "capability.reserve_typed_action",
        "capability.rollback_typed_action",
    ]


def test_typed_action_rechecks_cancellation_before_parsing_host_boundary_result(monkeypatch):
    from dcc_mcp_godot import capability_dispatch

    cancelled = False
    host_methods = []

    def check_cancelled():
        if cancelled:
            raise RuntimeError("cancelled-at-host-boundary")

    def call_host(method, _params):
        nonlocal cancelled
        host_methods.append(method)
        cancelled = True
        return {"status": "legacy-result-without-reservation"}

    monkeypatch.setattr(
        capability_dispatch,
        "check_dcc_cancelled",
        check_cancelled,
        raising=False,
    )
    monkeypatch.setattr(capability_dispatch, "call_host", call_host)

    with pytest.raises(RuntimeError, match="cancelled-at-host-boundary"):
        capability_dispatch.dispatch("execute_typed_action", {})
    assert host_methods == ["capability.reserve_typed_action"]


def test_typed_action_rolls_back_when_cancelled_during_reserved_mutation(monkeypatch):
    from dcc_mcp_godot import capability_dispatch

    checks = 0
    host_methods = []

    def cancelled_after_commit():
        nonlocal checks
        checks += 1
        if checks == 3:
            raise RuntimeError("cancelled-during-host-mutation")

    def call_host(method, _params):
        host_methods.append(method)
        if method == "capability.reserve_typed_action":
            return {"reservation_id": "review-reservation"}
        if method == "capability.commit_typed_action":
            return {
                "reservation_id": "review-reservation",
                "status": "pending_commit",
            }
        if method == "capability.rollback_typed_action":
            return {"status": "rolled_back"}
        raise AssertionError(f"unexpected host method: {method}")

    monkeypatch.setattr(
        capability_dispatch,
        "check_dcc_cancelled",
        cancelled_after_commit,
        raising=False,
    )
    monkeypatch.setattr(capability_dispatch, "call_host", call_host)

    with pytest.raises(RuntimeError, match="cancelled-during-host-mutation"):
        capability_dispatch.dispatch("execute_typed_action", {})
    assert host_methods == [
        "capability.reserve_typed_action",
        "capability.commit_typed_action",
        "capability.rollback_typed_action",
    ]


def test_typed_action_finalizes_one_claimed_host_mutation(monkeypatch):
    from dcc_mcp_godot import capability_dispatch

    host_methods = []

    def call_host(method, _params):
        host_methods.append(method)
        if method == "capability.reserve_typed_action":
            return {"reservation_id": "review-reservation"}
        if method == "capability.commit_typed_action":
            return {"status": "pending_commit"}
        if method == "capability.finalize_typed_action":
            return {"status": "applied"}
        raise AssertionError(f"unexpected host method: {method}")

    monkeypatch.setattr(capability_dispatch, "check_dcc_cancelled", lambda: None, raising=False)
    monkeypatch.setattr(capability_dispatch, "call_host", call_host)

    result = capability_dispatch.dispatch("execute_typed_action", {})

    assert result["context"]["status"] == "applied"
    assert host_methods == [
        "capability.reserve_typed_action",
        "capability.commit_typed_action",
        "capability.finalize_typed_action",
    ]


def test_typed_action_host_loss_during_commit_is_terminal_and_not_retried(monkeypatch):
    from dcc_mcp_godot import capability_dispatch

    host_methods = []

    def host_lost(method, _params):
        host_methods.append(method)
        if method == "capability.reserve_typed_action":
            return {"reservation_id": "review-reservation"}
        raise ConnectionError("runtime host lost during claimed mutation")

    monkeypatch.setattr(capability_dispatch, "check_dcc_cancelled", lambda: None, raising=False)
    monkeypatch.setattr(capability_dispatch, "call_host", host_lost)

    with pytest.raises(ConnectionError, match="runtime host lost during claimed mutation"):
        capability_dispatch.dispatch("execute_typed_action", {})
    assert host_methods == [
        "capability.reserve_typed_action",
        "capability.commit_typed_action",
    ]


def test_typed_action_host_loss_is_terminal_and_not_retried(monkeypatch):
    from dcc_mcp_godot import capability_dispatch

    host_calls = []

    def host_lost(*args, **kwargs):
        host_calls.append((args, kwargs))
        raise ConnectionError("runtime host lost")

    monkeypatch.setattr(capability_dispatch, "check_dcc_cancelled", lambda: None, raising=False)
    monkeypatch.setattr(capability_dispatch, "call_host", host_lost)

    with pytest.raises(ConnectionError, match="runtime host lost"):
        capability_dispatch.dispatch("execute_typed_action", {})
    assert len(host_calls) == 1


class RecordingBinder:
    def __init__(self):
        self.states = []

    def mark_dispatcher_ready(self, ready, **kwargs):
        self.states.append({"dispatcher": ready, **kwargs})


def test_bridge_disables_passive_keepalive_for_idle_editor(monkeypatch):
    """An idle Godot main loop must not be evicted for missing a transport ping."""
    import websockets

    serve_options = {}

    class FakeWebSocketServer:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return False

    def fake_serve(_handler, _host, _port, **kwargs):
        serve_options.update(kwargs)
        return FakeWebSocketServer()

    monkeypatch.setattr(websockets, "serve", fake_serve)
    monkeypatch.setattr(bridge, "_bridge", None)

    running_bridge = bridge.start_bridge()
    try:
        assert running_bridge.is_connected() is False
        assert serve_options["ping_interval"] is None
    finally:
        bridge.stop_bridge()


def test_tcp_disconnect_fails_all_bridge_readiness_bits_closed():
    with socket.socket() as port_reservation:
        port_reservation.bind(("127.0.0.1", 0))
        port = port_reservation.getsockname()[1]

    running_bridge = bridge.GodotDccBridge(host="127.0.0.1", port=port)
    running_bridge.connect(wait_for_dcc=False)
    binder = RecordingBinder()
    monitor = BridgeReadinessMonitor(binder, running_bridge.is_connected)

    async def connect_and_close() -> None:
        async with bridge_client(f"ws://127.0.0.1:{port}") as websocket:
            await websocket.send(
                json.dumps({"type": "hello", "client": "godot-test", "version": "4.x"})
            )
            acknowledgement = json.loads(await websocket.recv())
            assert acknowledgement["type"] == "hello_ack"
            deadline = time.monotonic() + 2.0
            while not running_bridge.is_connected() and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert monitor.refresh() is True
            assert binder.states[-1] == {
                "dispatcher": True,
                "dcc_ready": True,
                "host_execution_bridge_ready": True,
                "main_thread_executor_ready": True,
            }

    try:
        asyncio.run(connect_and_close())
        deadline = time.monotonic() + 2.0
        while running_bridge.is_connected() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert monitor.refresh() is False
        assert binder.states[-1] == {
            "dispatcher": True,
            "dcc_ready": False,
            "host_execution_bridge_ready": False,
            "main_thread_executor_ready": False,
        }
    finally:
        running_bridge.disconnect()


def test_bridge_uses_default_port_and_publishes_default_url(monkeypatch):
    monkeypatch.setattr(bridge, "_bridge", None)
    monkeypatch.delenv("DCC_MCP_GODOT_BRIDGE_PORT", raising=False)
    monkeypatch.delenv("DCC_MCP_GODOT_BRIDGE_URL", raising=False)

    running_bridge = bridge.get_bridge()

    assert running_bridge.endpoint == "ws://127.0.0.1:3847"
    assert os.environ["DCC_MCP_GODOT_BRIDGE_URL"] == "ws://127.0.0.1:3847"


def test_bridge_honors_explicit_dynamic_port_and_preserves_explicit_url(monkeypatch):
    with socket.socket() as port_reservation:
        port_reservation.bind(("127.0.0.1", 0))
        port = port_reservation.getsockname()[1]

    explicit_url = f"ws://127.0.0.1:{port}?owner=operator"
    monkeypatch.setattr(bridge, "_bridge", None)
    monkeypatch.setenv("DCC_MCP_GODOT_BRIDGE_PORT", str(port))
    monkeypatch.setenv("DCC_MCP_GODOT_BRIDGE_URL", explicit_url)

    running_bridge = bridge.get_bridge()

    assert running_bridge.endpoint == f"ws://127.0.0.1:{port}"
    assert os.environ["DCC_MCP_GODOT_BRIDGE_URL"] == explicit_url


def bridge_client(endpoint):
    import websockets

    return websockets.connect(endpoint)
