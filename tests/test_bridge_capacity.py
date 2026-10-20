"""Wire budgets count complete encoded messages and survive rejection."""

import asyncio
import json
import socket
import time
from concurrent.futures import Future
from pathlib import Path

import pytest
from dcc_mcp_core.bridge import BridgeRpcError

from dcc_mcp_godot import bridge, capability_dispatch


class Socket:
    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)


def request(source="", request_id=1):
    return json.dumps(
        {"type": "request", "id": request_id, "method": "test", "params": {"source": source}},
        separators=(",", ":"),
        ensure_ascii=False,
    )


@pytest.mark.parametrize("limit", [65535, bridge.MAX_BRIDGE_MESSAGE_BYTES])
@pytest.mark.parametrize("extra", [-1, 0, 1])
def test_final_wire_byte_boundary_and_recovery(limit, extra):
    host = bridge.GodotDccBridge()
    target = Socket()
    host._ws = target
    host._peer_message_limits[target] = limit
    payload = request("x" * (limit - len(request().encode()) + extra))
    pending = Future()
    host._pending[1] = pending
    asyncio.run(host._send(payload))
    if extra <= 0:
        assert target.sent == [payload]
        assert not pending.done()
    else:
        assert target.sent == []
        error = pending.exception()
        assert isinstance(error, BridgeRpcError)
        assert error.code == bridge.BRIDGE_MESSAGE_TOO_LARGE
        assert error.data == {
            "direction": "request",
            "actual_bytes": limit + 1,
            "max_bytes": limit,
            "outcome": "not_dispatched",
        }
        assert not host._pending
    asyncio.run(host._send(request("small", request_id=2)))
    assert target.sent[-1] == request("small", request_id=2)


@pytest.mark.parametrize(
    "source",
    ["雪" * 30000, "😀" * 20000, '\\"' * 20000],
    ids=["utf8-multibyte", "utf8-astral", "json-escaped"],
)
def test_counts_utf8_and_json_escaping_not_source_characters(source):
    host = bridge.GodotDccBridge()
    host._ws = Socket()
    pending = Future()
    host._pending[1] = pending
    payload = request(source)
    assert len(source) < bridge.LEGACY_BRIDGE_MESSAGE_BYTES
    assert len(payload.encode("utf-8")) > bridge.LEGACY_BRIDGE_MESSAGE_BYTES
    asyncio.run(host._send(payload))
    assert host._ws.sent == []
    assert pending.exception().data["actual_bytes"] == len(payload.encode("utf-8"))


@pytest.mark.parametrize("advertised", [None, True, "1048576", -1, 65534, 1048577, 1.5])
def test_invalid_capacity_keeps_legacy_budget(advertised):
    host = bridge.GodotDccBridge()
    target = Socket()
    asyncio.run(
        host._handle_hello(
            {"type": "hello", "transport": {"max_message_bytes": advertised}}, target
        )
    )
    assert host._peer_message_limits[target] == bridge.LEGACY_BRIDGE_MESSAGE_BYTES


def test_capacity_is_bound_to_each_connection_not_latest_hello():
    host = bridge.GodotDccBridge()
    modern, legacy = Socket(), Socket()
    asyncio.run(
        host._handle_hello(
            {"type": "hello", "transport": {"max_message_bytes": bridge.MAX_BRIDGE_MESSAGE_BYTES}},
            modern,
        )
    )
    asyncio.run(host._handle_hello({"type": "hello"}, legacy))
    assert host._peer_message_limits[modern] == bridge.MAX_BRIDGE_MESSAGE_BYTES
    assert host._peer_message_limits[legacy] == bridge.LEGACY_BRIDGE_MESSAGE_BYTES
    modern.sent.clear()
    legacy.sent.clear()
    pending = Future()
    host._pending[1] = pending
    asyncio.run(host._send(request("x" * 66000)))
    assert not modern.sent and not legacy.sent
    assert pending.exception().data["max_bytes"] == bridge.LEGACY_BRIDGE_MESSAGE_BYTES
    asyncio.run(host._send(request("x" * 66000), modern))
    assert len(modern.sent) == 1


def test_guarded_final_envelope_is_checked_before_claim_or_send():
    host = bridge.GodotDccBridge()
    host._ws = Socket()
    guard_id = "a" * 32
    claims = []

    class Guard:
        def claim(self):
            claims.append(True)

    host._commit_guards[guard_id] = bridge._GuardedSendState(Guard(), 1)
    message = {
        "type": "request",
        "id": 1,
        "method": "capability.commit_typed_action",
        "params": {host._COMMIT_GUARD_PARAM: guard_id, "padding": ""},
    }
    wire = json.dumps(message, separators=(",", ":"))
    message["params"]["padding"] = "x" * (65535 - len(wire.encode()))
    wire = json.dumps(message, separators=(",", ":"))
    assert len(wire.encode()) == 65535
    pending = Future()
    host._pending[1] = pending
    asyncio.run(host._send(wire))
    assert not claims and not host._ws.sent
    assert pending.exception().data["actual_bytes"] > 65535


def test_guarded_size_rejection_cleans_up_and_next_guarded_call_succeeds():
    import websockets

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    host = bridge.GodotDccBridge(host="127.0.0.1", port=port, timeout=2)
    host.connect(wait_for_dcc=False)
    claims = []

    class Guard:
        def claim(self):
            claims.append(True)

    async def exercise():
        async with websockets.connect(f"ws://127.0.0.1:{port}") as peer:
            await peer.send(json.dumps({"type": "hello"}))
            await peer.recv()
            with pytest.raises(BridgeRpcError) as rejected:
                await asyncio.to_thread(
                    host.call_with_commit_guard,
                    Guard(),
                    "capability.commit_typed_action",
                    padding="x" * 65535,
                )
            assert rejected.value.data["outcome"] == "not_dispatched"
            assert not claims and not host._commit_guards and not host._pending
            caller = asyncio.create_task(
                asyncio.to_thread(
                    host.call_with_commit_guard,
                    Guard(),
                    "capability.commit_typed_action",
                    reservation_id="small",
                )
            )
            message = json.loads(await asyncio.wait_for(peer.recv(), 2))
            fence = message["params"][host._COMMIT_FENCE_PARAM]
            await peer.send(json.dumps({"type": "commit_intent", **fence}))
            authorization = json.loads(await peer.recv())
            assert authorization["authorized"] is True
            await peer.send(
                json.dumps({"type": "response", "id": message["id"], "result": {"ok": True}})
            )
            assert await caller == {"ok": True}
            assert claims == [True]
            assert not host._commit_guards and not host._pending

    try:
        asyncio.run(exercise())
        deadline = time.monotonic() + 2
        while host._peer_message_limits and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not host._peer_message_limits
    finally:
        host.disconnect()


def test_size_error_remains_structured_at_the_public_skill_boundary(monkeypatch):
    data = {
        "direction": "response",
        "actual_bytes": 1200000,
        "max_bytes": 1048576,
        "outcome": "unknown",
    }

    def too_large(*args, **kwargs):
        raise BridgeRpcError(bridge.BRIDGE_MESSAGE_TOO_LARGE, "Response too large", data)

    monkeypatch.setattr(capability_dispatch, "call_host", too_large)
    result = capability_dispatch.dispatch("read_script", {"path": "res://large.gd"})
    assert result["success"] is False
    assert result["error"] == "bridge_message_too_large"
    assert result["context"] == {"code": bridge.BRIDGE_MESSAGE_TOO_LARGE, **data}


def test_guarded_commit_terminal_error_is_not_mislabeled_as_capacity(monkeypatch):
    def terminal(*args, **kwargs):
        raise BridgeRpcError(-32004, "typed_action_commit_terminal")

    monkeypatch.setattr(capability_dispatch, "call_host", terminal)
    with pytest.raises(BridgeRpcError, match="typed_action_commit_terminal"):
        capability_dispatch.dispatch("read_script", {"path": "res://large.gd"})


def test_host_and_python_budgets_match_and_send_failures_are_not_ignored():
    plugin = (
        Path(__file__).parents[1] / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot/plugin.gd"
    ).read_text(encoding="utf-8")
    assert f"const MAX_BRIDGE_MESSAGE_BYTES := {bridge.MAX_BRIDGE_MESSAGE_BYTES}" in plugin
    assert f"const BRIDGE_MESSAGE_TOO_LARGE := {bridge.BRIDGE_MESSAGE_TOO_LARGE}" in plugin
    assert "_socket.inbound_buffer_size = BRIDGE_BUFFER_BYTES" in plugin
    assert "_socket.outbound_buffer_size = BRIDGE_BUFFER_BYTES" in plugin
    assert '"transport": {"max_message_bytes": MAX_BRIDGE_MESSAGE_BYTES}' in plugin
    assert "var error := _socket.send_text(text)" in plugin
    assert "if error != OK:" in plugin
    assert '"outcome": "unknown"' in plugin
