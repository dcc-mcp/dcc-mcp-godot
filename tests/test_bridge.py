import asyncio
import json
import socket
import time

from dcc_mcp_godot import bridge


class FakeBridge:
    def call(self, method, **params):
        return {"method": method, "params": params}


def test_call_host_uses_typed_method_and_parameters(monkeypatch):
    monkeypatch.setattr(bridge, "_bridge", FakeBridge())
    assert bridge.call_host("scene.inspect", {"depth": 2}) == {
        "method": "scene.inspect",
        "params": {"depth": 2},
    }


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


def test_bridge_fails_closed_when_editor_connection_closes():
    with socket.socket() as port_reservation:
        port_reservation.bind(("127.0.0.1", 0))
        port = port_reservation.getsockname()[1]

    running_bridge = bridge.GodotDccBridge(host="127.0.0.1", port=port)
    running_bridge.connect(wait_for_dcc=False)

    async def connect_and_close() -> None:
        async with bridge_client(f"ws://127.0.0.1:{port}") as websocket:
            await websocket.send(
                json.dumps({"type": "hello", "client": "godot-test", "version": "4.x"})
            )
            acknowledgement = json.loads(await websocket.recv())
            assert acknowledgement["type"] == "hello_ack"
            assert running_bridge.is_connected() is True

    try:
        asyncio.run(connect_and_close())
        deadline = time.monotonic() + 2.0
        while running_bridge.is_connected() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert running_bridge.is_connected() is False
    finally:
        running_bridge.disconnect()


def bridge_client(endpoint):
    import websockets

    return websockets.connect(endpoint)
