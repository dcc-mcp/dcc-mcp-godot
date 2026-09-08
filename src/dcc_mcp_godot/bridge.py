"""Loopback WebSocket bridge shared by the MCP server and Godot plugin."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import threading
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Protocol

from dcc_mcp_core.bridge import BridgeConnectionError, BridgeTimeoutError, DccBridge

logger = logging.getLogger(__name__)

_bridge: DccBridge | None = None
_lock = threading.Lock()


class HostCommitGuard(Protocol):
    """One-shot cancellation claim evaluated where a host mutation is sent."""

    def claim(self) -> None: ...


class _GuardedSendState:
    """Arbitrate a terminal timeout against host-side mutation authorization."""

    def __init__(self, guard: HostCommitGuard, request_id: str | int) -> None:
        self.guard = guard
        self.request_id = request_id
        self._lock = threading.Lock()
        self._terminal = False
        self._authorized = False
        self._task: asyncio.Task[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._target: Any = None
        self._request_digest = ""

    def bind(
        self,
        task: asyncio.Task[Any],
        loop: asyncio.AbstractEventLoop,
        target: Any,
        request_digest: str,
    ) -> bool:
        with self._lock:
            if self._terminal:
                return False
            self._task = task
            self._loop = loop
            self._target = target
            self._request_digest = request_digest
            return True

    def authorize(
        self,
        target: Any,
        request_id: str | int,
        request_digest: str,
    ) -> tuple[bool, str, BaseException | None]:
        """Atomically claim ownership only after the host asks to mutate."""
        with self._lock:
            if self._terminal:
                return False, "request_terminal", None
            if (
                self._target is not target
                or self.request_id != request_id
                or self._request_digest != request_digest
            ):
                return False, "request_identity_mismatch", None
            if self._authorized:
                return False, "request_already_authorized", None
            try:
                self.guard.claim()
            except BaseException as exc:
                self._terminal = True
                return False, "commit_guard_rejected", exc
            self._authorized = True
            return True, "authorized", None

    def terminate_if_unclaimed(self) -> bool:
        """Make an unclaimed request terminal, or preserve an owned commit."""
        task: asyncio.Task[Any] | None
        loop: asyncio.AbstractEventLoop | None
        with self._lock:
            if self._authorized:
                return False
            if self._terminal:
                return True
            self._terminal = True
            task = self._task
            loop = self._loop
        if task is not None and loop is not None and not task.done():
            loop.call_soon_threadsafe(task.cancel)
        return True

    @property
    def authorized(self) -> bool:
        with self._lock:
            return self._authorized

    def belongs_to(self, target: Any) -> bool:
        with self._lock:
            return self._target is target

    @property
    def needs_terminal_fence(self) -> bool:
        with self._lock:
            return self._target is not None

    def reject_authorization(self) -> None:
        with self._lock:
            self._authorized = False
            self._terminal = True


class GodotDccBridge(DccBridge):
    """Core bridge configured for an editor that may stop polling while idle."""

    _COMMIT_GUARD_PARAM = "__dcc_mcp_commit_guard_id"
    _COMMIT_FENCE_PARAM = "__dcc_mcp_commit_fence"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._commit_guards: dict[str, _GuardedSendState | HostCommitGuard] = {}
        self._commit_guards_lock = threading.Lock()

    def call_with_commit_guard(
        self,
        guard: HostCommitGuard,
        method: str,
        **params: Any,
    ) -> Any:
        """Authorize one exact typed-action commit at the host mutation boundary."""
        if method != "capability.commit_typed_action":
            raise ValueError("A guarded Godot call must be a typed-action commit")
        if not self._connected:
            raise BridgeConnectionError("No DCC plugin is connected.")
        guard_id = secrets.token_hex(16)
        request_id = self._next_request_id()
        state = _GuardedSendState(guard, request_id)
        with self._commit_guards_lock:
            if self._commit_guards:
                raise BridgeConnectionError("A previous Godot commit fence is still unresolved")
            self._commit_guards[guard_id] = state
        pending = Future()
        with self._pending_lock:
            self._pending[request_id] = pending
        params[self._COMMIT_GUARD_PARAM] = guard_id
        message = {
            "type": "request",
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        send_future: Future | None = None
        terminal_timeout = False
        try:
            send_future = asyncio.run_coroutine_threadsafe(
                self._send(json.dumps(message, separators=(",", ":"))),
                self._loop,
            )
            try:
                result = pending.result(timeout=self._timeout)
            except FutureTimeoutError as exc:
                if state.terminate_if_unclaimed():
                    terminal_timeout = True
                    raise BridgeTimeoutError(
                        f"Method '{method}' (id={request_id}) timed out after "
                        f"{self._timeout}s before host commit authorization."
                    ) from exc
                # The host won the atomic authorization race. Cancellation no
                # longer owns this mutation, so wait for its definitive result
                # or for the pinned connection to be lost.
                result = pending.result()
            if not state.authorized:
                raise BridgeConnectionError(
                    "Godot host returned a guarded result without commit authorization"
                )
            return result
        finally:
            if terminal_timeout:
                if send_future is not None:
                    send_future.cancel()
                # Keep the exact terminal fence until the pinned host presents
                # its late intent (which is denied) or that connection closes.
                if not state.needs_terminal_fence:
                    with self._commit_guards_lock:
                        self._commit_guards.pop(guard_id, None)
            else:
                state.terminate_if_unclaimed()
                with self._commit_guards_lock:
                    self._commit_guards.pop(guard_id, None)
            with self._pending_lock:
                self._pending.pop(request_id, None)

    async def _send(self, text: str, ws: Any = None) -> None:
        if ws is not None:
            await super()._send(text, ws)
            return
        try:
            message = json.loads(text)
        except (TypeError, ValueError):
            await super()._send(text, ws)
            return
        params = message.get("params")
        guard_id = params.pop(self._COMMIT_GUARD_PARAM, None) if isinstance(params, dict) else None
        if not isinstance(guard_id, str):
            await super()._send(text, ws)
            return
        with self._commit_guards_lock:
            stored = self._commit_guards.get(guard_id)
        state: _GuardedSendState | None
        if isinstance(stored, _GuardedSendState):
            state = stored
        else:
            state = None
        target = self._ws
        request_digest = self._guarded_request_digest(message)
        current_task = asyncio.current_task()
        if state is not None and (
            current_task is None
            or target is None
            or not state.bind(
                current_task,
                asyncio.get_running_loop(),
                target,
                request_digest,
            )
        ):
            return
        params[self._COMMIT_FENCE_PARAM] = {
            "guard_id": guard_id,
            "request_id": message.get("id"),
            "request_digest": request_digest,
        }
        try:
            if state is None:
                raise RuntimeError("Godot host commit guard is missing")
            if target is None:
                raise BridgeConnectionError("Godot host disconnected before guarded commit")
            if self._ws is not target:
                raise BridgeConnectionError(
                    "Godot host connection changed before guarded commit intent"
                )
        except BaseException as exc:
            self._fail_guarded_request(message, exc)
            return
        try:
            await target.send(json.dumps(message, separators=(",", ":")))
        except Exception as exc:
            self._fail_guarded_request(
                message,
                BridgeConnectionError("Godot host disconnected during guarded commit"),
            )
            logger.debug("Failed to send guarded Godot commit: %s", exc)

    @staticmethod
    def _guarded_request_digest(message: dict[str, Any]) -> str:
        canonical = json.dumps(message, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def _dispatch(self, raw: str, ws: Any) -> None:
        try:
            message = json.loads(raw)
        except (TypeError, ValueError):
            await super()._dispatch(raw, ws)
            return
        if message.get("type") != "commit_intent":
            await super()._dispatch(raw, ws)
            return
        await self._handle_commit_intent(message, ws)

    async def _handle_commit_intent(self, message: dict[str, Any], ws: Any) -> None:
        expected_keys = {"type", "guard_id", "request_id", "request_digest"}
        guard_id = message.get("guard_id")
        request_id = message.get("request_id")
        request_digest = message.get("request_digest")
        normalized_request_id = (
            int(request_id)
            if isinstance(request_id, float) and request_id.is_integer()
            else request_id
        )
        state: _GuardedSendState | None = None
        if (
            set(message) == expected_keys
            and isinstance(guard_id, str)
            and len(guard_id) == 32
            and all(character in "0123456789abcdef" for character in guard_id)
            and isinstance(normalized_request_id, int)
            and not isinstance(normalized_request_id, bool)
            and isinstance(request_digest, str)
            and len(request_digest) == 64
            and all(character in "0123456789abcdef" for character in request_digest)
            and self._ws is ws
        ):
            with self._commit_guards_lock:
                stored = self._commit_guards.get(guard_id)
            if isinstance(stored, _GuardedSendState):
                state = stored

        if state is None:
            authorized, reason, error = False, "request_terminal", None
        else:
            authorized, reason, error = state.authorize(ws, normalized_request_id, request_digest)
        if authorized and self._ws is not ws:
            state.reject_authorization()
            authorized = False
            reason = "host_identity_mismatch"
            error = BridgeConnectionError(
                "Godot host connection changed at guarded commit boundary"
            )
        if error is not None and state is not None:
            self._fail_guarded_request_by_id(state.request_id, error)

        authorization = {
            "type": "commit_authorization",
            "guard_id": guard_id,
            "request_id": request_id,
            "request_digest": request_digest,
            "authorized": authorized,
            "reason": reason,
        }
        await super()._send(
            json.dumps(authorization, separators=(",", ":")),
            ws,
        )
        if not authorized and isinstance(guard_id, str):
            with self._commit_guards_lock:
                if self._commit_guards.get(guard_id) is state:
                    self._commit_guards.pop(guard_id, None)

    async def _handle_dcc(self, ws: Any) -> None:
        try:
            await super()._handle_dcc(ws)
        finally:
            disconnected: list[tuple[str, _GuardedSendState]] = []
            with self._commit_guards_lock:
                for guard_id, stored in list(self._commit_guards.items()):
                    if isinstance(stored, _GuardedSendState) and stored.belongs_to(ws):
                        disconnected.append((guard_id, stored))
                        self._commit_guards.pop(guard_id, None)
            for _guard_id, state in disconnected:
                self._fail_guarded_request_by_id(
                    state.request_id,
                    BridgeConnectionError("Godot host disconnected before guarded commit"),
                )

    def _fail_guarded_request(
        self,
        message: dict[str, Any],
        exc: BaseException,
    ) -> None:
        self._fail_guarded_request_by_id(message.get("id"), exc)

    def _fail_guarded_request_by_id(
        self,
        request_id: str | int | None,
        exc: BaseException,
    ) -> None:
        with self._pending_lock:
            pending = self._pending.pop(request_id, None)
        if pending is not None and not pending.done():
            pending.set_exception(exc)

    async def _serve(self) -> None:
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "The 'websockets' package is required for DccBridge. "
                "Install it with: pip install websockets"
            ) from exc

        shutdown_event = asyncio.Event()
        self._shutdown_event = shutdown_event
        try:
            # Godot's WebSocketPeer only handles control frames while the editor
            # main loop polls it.  An idle or unfocused editor may therefore miss
            # the library's default ping deadline despite remaining alive.  This
            # loopback transport relies on TCP close for process-death detection.
            async with websockets.serve(
                self._handle_dcc,
                self._host,
                self._port,
                ping_interval=None,
            ) as server:
                self._ws_server = server
                self._server_ready.set()
                logger.debug("Godot DccBridge listening on %s", self.endpoint)
                await shutdown_event.wait()
        finally:
            self._shutdown_event = None
            self._ws_server = None


def get_bridge() -> DccBridge:
    """Return the process-wide bridge, creating it without starting it."""
    global _bridge
    with _lock:
        if _bridge is None:
            port = int(os.environ.get("DCC_MCP_GODOT_BRIDGE_PORT", "3847"))
            _bridge = GodotDccBridge(
                host="127.0.0.1",
                port=port,
                timeout=float(os.environ.get("DCC_MCP_GODOT_BRIDGE_TIMEOUT", "60")),
                server_name="dcc-mcp-godot",
            )
            os.environ.setdefault("DCC_MCP_GODOT_BRIDGE_URL", f"ws://127.0.0.1:{port}")
        return _bridge


def start_bridge() -> DccBridge:
    bridge = get_bridge()
    bridge.connect(wait_for_dcc=False)
    return bridge


def stop_bridge() -> None:
    global _bridge
    with _lock:
        bridge, _bridge = _bridge, None
    if bridge is not None:
        bridge.disconnect()


def call_host(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    commit_guard: HostCommitGuard | None = None,
) -> dict[str, Any]:
    """Invoke one typed command in the connected Godot editor plugin."""
    wire_params = dict(params or {})
    if "method" in wire_params:
        # DccBridge.call() owns the Python ``method`` keyword. Keep the public
        # tool field while using a private wire key inside the Godot adapter.
        wire_params["__method__"] = wire_params.pop("method")
    running_bridge = get_bridge()
    if commit_guard is None:
        result = running_bridge.call(method, **wire_params)
    else:
        guarded_call = getattr(running_bridge, "call_with_commit_guard", None)
        if not callable(guarded_call):
            raise RuntimeError("Godot bridge does not support guarded host commits")
        result = guarded_call(commit_guard, method, **wire_params)
    if not isinstance(result, dict):
        return {"value": result}
    return result
