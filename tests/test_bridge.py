import asyncio
import json
import os
import socket
import time

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
