import asyncio
import json
import os
import socket
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

import pytest
from dcc_mcp_core.bridge import BridgeConnectionError, BridgeTimeoutError

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


def test_call_host_uses_the_bridge_commit_boundary_for_guarded_mutations(monkeypatch):
    claims = []

    class CommitGuard:
        def claim(self):
            claims.append("claimed")

    class GuardedBridge:
        def call_with_commit_guard(self, guard, method, **params):
            guard.claim()
            return {"method": method, "params": params}

    monkeypatch.setattr(bridge, "_bridge", GuardedBridge())
    result = bridge.call_host(
        "capability.commit_typed_action",
        {"reservation_id": "guarded-reservation"},
        commit_guard=CommitGuard(),
    )

    assert claims == ["claimed"]
    assert result == {
        "method": "capability.commit_typed_action",
        "params": {"reservation_id": "guarded-reservation"},
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
        if checks == 4:
            raise RuntimeError("cancelled-during-host-mutation")

    def call_host(method, _params, *, commit_guard=None):
        host_methods.append(method)
        if method == "capability.reserve_typed_action":
            return {"reservation_id": "review-reservation"}
        if method == "capability.commit_typed_action":
            assert commit_guard is not None
            commit_guard.claim()
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


def test_typed_action_cancelled_while_commit_is_queued_never_reaches_host_mutation(
    monkeypatch,
):
    from dcc_mcp_godot import capability_dispatch

    cancelled = threading.Event()
    commit_queued = threading.Event()
    release_commit = threading.Event()
    mutation_attempts = 0
    host_methods = []

    def check_cancelled():
        if cancelled.is_set():
            raise RuntimeError("cancelled-before-host-commit")

    def call_host(method, _params, *, commit_guard=None):
        nonlocal mutation_attempts
        host_methods.append(method)
        if method == "capability.reserve_typed_action":
            return {"reservation_id": "blocked-reservation"}
        if method == "capability.commit_typed_action":
            commit_queued.set()
            assert release_commit.wait(timeout=2.0)
            if commit_guard is not None:
                commit_guard.claim()
            mutation_attempts += 1
            return {"status": "pending_commit"}
        if method == "capability.rollback_typed_action":
            return {"status": "rolled_back"}
        raise AssertionError(f"unexpected host method: {method}")

    monkeypatch.setattr(
        capability_dispatch,
        "check_dcc_cancelled",
        check_cancelled,
        raising=False,
    )
    monkeypatch.setattr(capability_dispatch, "call_host", call_host)

    failure = []

    def dispatch_action():
        try:
            capability_dispatch.dispatch("execute_typed_action", {})
        except BaseException as exc:
            failure.append(exc)

    worker = threading.Thread(target=dispatch_action)
    worker.start()
    assert commit_queued.wait(timeout=2.0)
    cancelled.set()
    release_commit.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert len(failure) == 1
    assert "cancelled-before-host-commit" in str(failure[0])
    assert mutation_attempts == 0
    assert host_methods == [
        "capability.reserve_typed_action",
        "capability.commit_typed_action",
        "capability.rollback_typed_action",
    ]


def test_typed_action_commit_guard_keeps_the_originating_cancellation_probe():
    from dcc_mcp_core.cancellation import (
        CancelToken,
        DccMcpCancelledError,
        reset_cancel_token,
        set_cancel_token,
    )

    from dcc_mcp_godot.capability_dispatch import _TypedActionCommitGuard

    token = CancelToken(job_id="server-job-17")
    reset = set_cancel_token(token)
    try:
        guard = _TypedActionCommitGuard({})
    finally:
        reset_cancel_token(reset)
    token.cancel()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(guard.claim)
        with pytest.raises(DccMcpCancelledError, match="Request cancelled by client"):
            future.result(timeout=2.0)


def test_typed_action_finalizes_one_claimed_host_mutation(monkeypatch):
    from dcc_mcp_godot import capability_dispatch

    host_methods = []

    def call_host(method, _params, *, commit_guard=None):
        host_methods.append(method)
        if method == "capability.reserve_typed_action":
            return {"reservation_id": "review-reservation"}
        if method == "capability.commit_typed_action":
            assert commit_guard is not None
            commit_guard.claim()
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


def test_typed_action_host_commit_claim_binds_job_and_runtime_authority(monkeypatch):
    from dcc_mcp_godot import capability_dispatch

    request = {
        "project_id": "project-1",
        "session_id": "session-1",
        "runtime_id": "runtime-1",
        "authority_id": "authority-1",
        "manifest_id": "manifest-1",
        "manifest_digest": "a" * 64,
        "action": {
            "id": "press-jump",
            "kind": "input_action",
            "target": {"action": "jump"},
            "arguments": {"pressed": True, "strength": 1.0},
        },
    }
    commit_params = []

    def call_host(method, params, *, commit_guard=None):
        if method == "capability.reserve_typed_action":
            return {"reservation_id": "bound-reservation"}
        if method == "capability.commit_typed_action":
            commit_params.append(params)
            assert commit_guard is not None
            commit_guard.claim()
            return {"status": "pending_commit"}
        if method == "capability.finalize_typed_action":
            return {"status": "applied"}
        raise AssertionError(f"unexpected host method: {method}")

    monkeypatch.setattr(capability_dispatch, "check_dcc_cancelled", lambda: None)
    monkeypatch.setattr(capability_dispatch, "current_job_id", lambda: "server-job-17")
    monkeypatch.setattr(capability_dispatch, "call_host", call_host)

    capability_dispatch.dispatch("execute_typed_action", request)

    assert len(commit_params) == 1
    claim = commit_params[0]["commit_claim"]
    assert set(claim) == {
        "claim_id",
        "job_id",
        "project_id",
        "session_id",
        "runtime_id",
        "authority_id",
        "manifest_id",
        "manifest_digest",
        "action_id",
    }
    assert claim["job_id"] == "server-job-17"
    assert claim["project_id"] == request["project_id"]
    assert claim["session_id"] == request["session_id"]
    assert claim["runtime_id"] == request["runtime_id"]
    assert claim["authority_id"] == request["authority_id"]
    assert claim["manifest_id"] == request["manifest_id"]
    assert claim["manifest_digest"] == request["manifest_digest"]
    assert claim["action_id"] == request["action"]["id"]
    assert len(claim["claim_id"]) == 32


def test_typed_action_host_loss_during_commit_is_terminal_and_not_retried(monkeypatch):
    from dcc_mcp_godot import capability_dispatch

    host_methods = []

    def host_lost(method, _params, *, commit_guard=None):
        host_methods.append(method)
        if method == "capability.reserve_typed_action":
            return {"reservation_id": "review-reservation"}
        if commit_guard is not None:
            commit_guard.claim()
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


def test_guarded_bridge_claim_failure_denies_host_mutation_intent():
    with socket.socket() as port_reservation:
        port_reservation.bind(("127.0.0.1", 0))
        port = port_reservation.getsockname()[1]

    running_bridge = bridge.GodotDccBridge(host="127.0.0.1", port=port)
    running_bridge.connect(wait_for_dcc=False)
    caller_thread = threading.get_ident()
    claim_threads = []

    class CancelledGuard:
        def claim(self):
            claim_threads.append(threading.get_ident())
            raise RuntimeError("cancelled-at-websocket-boundary")

    async def connect_and_reject_commit() -> None:
        async with bridge_client(f"ws://127.0.0.1:{port}") as websocket:
            await websocket.send(
                json.dumps({"type": "hello", "client": "godot-test", "version": "4.x"})
            )
            await websocket.recv()
            deadline = time.monotonic() + 2.0
            while not running_bridge.is_connected() and time.monotonic() < deadline:
                await asyncio.sleep(0)
            caller = asyncio.create_task(
                asyncio.to_thread(
                    running_bridge.call_with_commit_guard,
                    CancelledGuard(),
                    "capability.commit_typed_action",
                    reservation_id="guarded-reservation",
                )
            )
            request = json.loads(await asyncio.wait_for(websocket.recv(), timeout=1.0))
            fence = request["params"][running_bridge._COMMIT_FENCE_PARAM]
            await websocket.send(json.dumps({"type": "commit_intent", **fence}))
            authorization = json.loads(await websocket.recv())
            assert authorization["authorized"] is False
            assert authorization["reason"] == "commit_guard_rejected"
            with pytest.raises(RuntimeError, match="cancelled-at-websocket-boundary"):
                await caller

    try:
        asyncio.run(connect_and_reject_commit())
        assert claim_threads
        assert claim_threads[0] != caller_thread
    finally:
        running_bridge.disconnect()


def test_guarded_bridge_rejects_every_non_typed_action_method():
    running_bridge = bridge.GodotDccBridge(host="127.0.0.1", port=0)
    running_bridge._connected = True

    class StableGuard:
        def claim(self):
            raise AssertionError("non-commit method must never claim mutation ownership")

    with pytest.raises(ValueError, match="must be a typed-action commit"):
        running_bridge.call_with_commit_guard(
            StableGuard(),
            "capability.execute_game_script",
            reservation_id="forbidden-guarded-method",
        )


def test_guarded_bridge_authorizes_exact_host_intent_before_accepting_result():
    with socket.socket() as port_reservation:
        port_reservation.bind(("127.0.0.1", 0))
        port = port_reservation.getsockname()[1]

    running_bridge = bridge.GodotDccBridge(host="127.0.0.1", port=port)
    running_bridge.connect(wait_for_dcc=False)
    state = {"guard_claims": 0}

    class StableGuard:
        def claim(self):
            state["guard_claims"] += 1

    async def connect_and_commit() -> None:
        async with bridge_client(f"ws://127.0.0.1:{port}") as websocket:
            await websocket.send(
                json.dumps({"type": "hello", "client": "godot-test", "version": "4.x"})
            )
            await websocket.recv()
            deadline = time.monotonic() + 2.0
            while not running_bridge.is_connected() and time.monotonic() < deadline:
                await asyncio.sleep(0)
            caller = asyncio.create_task(
                asyncio.to_thread(
                    running_bridge.call_with_commit_guard,
                    StableGuard(),
                    "capability.commit_typed_action",
                    reservation_id="authorized-reservation",
                )
            )
            request = json.loads(await asyncio.wait_for(websocket.recv(), timeout=1.0))
            fence = request["params"][running_bridge._COMMIT_FENCE_PARAM]
            await websocket.send(json.dumps({"type": "commit_intent", **fence}))
            authorization = json.loads(await websocket.recv())
            assert authorization == {
                "type": "commit_authorization",
                **fence,
                "authorized": True,
                "reason": "authorized",
            }
            await websocket.send(
                json.dumps(
                    {
                        "type": "response",
                        "id": request["id"],
                        "result": {"status": "pending_commit"},
                    }
                )
            )
            assert await caller == {"status": "pending_commit"}
            assert state["guard_claims"] == 1
            assert running_bridge._commit_guards == {}

    try:
        asyncio.run(connect_and_commit())
    finally:
        running_bridge.disconnect()


def test_guarded_bridge_commit_is_pinned_to_the_claimed_host_connection():
    running_bridge = bridge.GodotDccBridge(host="127.0.0.1", port=0)
    sent = []

    class FakeSocket:
        def __init__(self, name):
            self.name = name

        async def send(self, text):
            sent.append((self.name, json.loads(text)))

    original = FakeSocket("original")
    running_bridge._ws = original
    guard_id = "1" * 32

    class StableGuard:
        def claim(self):
            pass

    with running_bridge._commit_guards_lock:
        running_bridge._commit_guards[guard_id] = bridge._GuardedSendState(StableGuard(), 7)
    message = json.dumps(
        {
            "type": "request",
            "jsonrpc": "2.0",
            "id": 7,
            "method": "capability.commit_typed_action",
            "params": {
                "reservation_id": "host-bound-reservation",
                running_bridge._COMMIT_GUARD_PARAM: guard_id,
            },
        }
    )

    asyncio.run(running_bridge._send(message))

    assert [name for name, _message in sent] == ["original"]
    assert running_bridge._COMMIT_GUARD_PARAM not in sent[0][1]["params"]
    fence = sent[0][1]["params"][running_bridge._COMMIT_FENCE_PARAM]
    asyncio.run(running_bridge._dispatch(json.dumps({"type": "commit_intent", **fence}), original))
    assert sent[-1][1]["type"] == "commit_authorization"
    assert sent[-1][1]["authorized"] is True


def test_guarded_bridge_commit_rejects_host_replacement_before_send():
    running_bridge = bridge.GodotDccBridge(host="127.0.0.1", port=0)
    sent = []

    class FakeSocket:
        def __init__(self, name):
            self.name = name

        async def send(self, text):
            sent.append((self.name, json.loads(text)))

    original = FakeSocket("original")
    replacement = FakeSocket("replacement")
    running_bridge._ws = original
    guard_id = "2" * 32
    pending = Future()

    class ReplacingGuard:
        def claim(self):
            running_bridge._ws = replacement

    with running_bridge._commit_guards_lock:
        running_bridge._commit_guards[guard_id] = bridge._GuardedSendState(ReplacingGuard(), 8)
    with running_bridge._pending_lock:
        running_bridge._pending[8] = pending
    message = json.dumps(
        {
            "type": "request",
            "jsonrpc": "2.0",
            "id": 8,
            "method": "capability.commit_typed_action",
            "params": {
                "reservation_id": "host-bound-reservation",
                running_bridge._COMMIT_GUARD_PARAM: guard_id,
            },
        }
    )

    asyncio.run(running_bridge._send(message))

    assert [name for name, _message in sent] == ["original"]
    fence = sent[0][1]["params"][running_bridge._COMMIT_FENCE_PARAM]
    asyncio.run(running_bridge._dispatch(json.dumps({"type": "commit_intent", **fence}), original))
    assert all(message.get("authorized") is not True for _name, message in sent)
    with pytest.raises(
        BridgeConnectionError, match="connection changed at guarded commit boundary"
    ):
        pending.result()


def test_guarded_bridge_timeout_cancels_a_blocked_wire_send_before_commit():
    running_bridge = bridge.GodotDccBridge(
        host="127.0.0.1",
        port=0,
        timeout=0.05,
    )
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever)
    loop_thread.start()
    running_bridge._loop = loop
    running_bridge._connected = True
    entered = threading.Event()
    release = threading.Event()
    sent = []

    class DelayedSocket:
        async def send(self, text):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.001)
            sent.append(json.loads(text)["method"])

    class StableGuard:
        def claim(self):
            pass

    running_bridge._ws = DelayedSocket()
    try:
        with pytest.raises(BridgeTimeoutError):
            running_bridge.call_with_commit_guard(
                StableGuard(),
                "capability.commit_typed_action",
                reservation_id="blocked-send-reservation",
            )
        assert entered.is_set()
        release.set()
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0.05), loop).result()
        assert sent == []
    finally:
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join()
        loop.close()


def test_guarded_bridge_terminal_fence_denies_a_cancellation_swallowing_late_send():
    running_bridge = bridge.GodotDccBridge(
        host="127.0.0.1",
        port=0,
        timeout=0.05,
    )
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever)
    loop_thread.start()
    running_bridge._loop = loop
    running_bridge._connected = True
    entered = threading.Event()
    release = threading.Event()
    authorization_seen = threading.Event()
    wire_messages = []
    authorizations = []

    class CancellationSwallowingSocket:
        async def send(self, text):
            message = json.loads(text)
            if message.get("type") == "commit_authorization":
                authorizations.append(message)
                authorization_seen.set()
                return
            entered.set()
            while not release.is_set():
                try:
                    await asyncio.to_thread(release.wait)
                except asyncio.CancelledError:
                    continue
            wire_messages.append(message)
            fence = message["params"][running_bridge._COMMIT_FENCE_PARAM]
            await running_bridge._dispatch(
                json.dumps(
                    {
                        "type": "commit_intent",
                        **fence,
                    }
                ),
                self,
            )

    class StableGuard:
        def claim(self):
            raise AssertionError("a terminal request must not transfer mutation ownership")

    running_bridge._ws = CancellationSwallowingSocket()
    try:
        with pytest.raises(BridgeTimeoutError):
            running_bridge.call_with_commit_guard(
                StableGuard(),
                "capability.commit_typed_action",
                reservation_id="adversarial-reservation",
            )
        assert entered.is_set()
        with pytest.raises(BridgeConnectionError, match="commit fence is still unresolved"):
            running_bridge.call_with_commit_guard(
                StableGuard(),
                "capability.commit_typed_action",
                reservation_id="must-not-bypass-terminal-fence",
            )
        release.set()
        assert authorization_seen.wait(1.0)
        assert [message["method"] for message in wire_messages] == [
            "capability.commit_typed_action"
        ]
        assert len(authorizations) == 1
        assert authorizations[0]["authorized"] is False
        assert authorizations[0]["reason"] == "request_terminal"
        assert running_bridge._commit_guards == {}
    finally:
        release.set()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join()
        loop.close()


def test_guarded_bridge_real_websocket_denies_commit_received_after_terminal_timeout():
    with socket.socket() as port_reservation:
        port_reservation.bind(("127.0.0.1", 0))
        port = port_reservation.getsockname()[1]

    running_bridge = bridge.GodotDccBridge(
        host="127.0.0.1",
        port=port,
        timeout=0.05,
    )
    running_bridge.connect(wait_for_dcc=False)
    state = {"guard_claims": 0, "error": None}

    class StableGuard:
        def claim(self):
            state["guard_claims"] += 1

    def call_commit():
        try:
            running_bridge.call_with_commit_guard(
                StableGuard(),
                "capability.commit_typed_action",
                reservation_id="paused-godot-reservation",
            )
        except BaseException as exc:
            state["error"] = type(exc).__name__

    async def paused_host_probe():
        async with bridge_client(f"ws://127.0.0.1:{port}") as websocket:
            await websocket.send(
                json.dumps({"type": "hello", "client": "godot-test", "version": "4.x"})
            )
            await websocket.recv()
            deadline = time.monotonic() + 2.0
            while not running_bridge.is_connected() and time.monotonic() < deadline:
                await asyncio.sleep(0)

            worker = threading.Thread(target=call_commit)
            worker.start()
            worker.join(timeout=1.0)
            assert not worker.is_alive()
            assert state["error"] == "BridgeTimeoutError"

            request = json.loads(await asyncio.wait_for(websocket.recv(), timeout=1.0))
            fence = request["params"][running_bridge._COMMIT_FENCE_PARAM]
            await websocket.send(json.dumps({"type": "commit_intent", **fence}))
            authorization = json.loads(await asyncio.wait_for(websocket.recv(), timeout=1.0))
            assert authorization == {
                "type": "commit_authorization",
                **fence,
                "authorized": False,
                "reason": "request_terminal",
            }
            assert state["guard_claims"] == 0
            assert running_bridge._commit_guards == {}

    try:
        asyncio.run(paused_host_probe())
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
