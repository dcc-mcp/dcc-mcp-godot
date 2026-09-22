"""Unit coverage for the live smoke test's runtime-peer wait.

The live Godot smoke job is the only place the wait runs for real, so these
tests pin its state machine: a slow attach must keep waiting, a dead gameplay
process must fail fast, and a stuck peer must still fail the job.
"""

from __future__ import annotations

from typing import Any, Callable

import live_godot_smoke
import pytest
from live_godot_smoke import _wait_for_runtime_peer


class _FakeClock:
    """Clock that advances only when the wait sleeps."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _sampler(script: list[dict[str, Any]]) -> Callable[[], dict[str, Any]]:
    """Build a status sampler that replays ``script`` and then repeats its end."""
    calls = {"count": 0}

    def sample() -> dict[str, Any]:
        index = min(calls["count"], len(script) - 1)
        calls["count"] += 1
        return script[index]

    return sample


def _wait(
    script: list[dict[str, Any]],
    *,
    is_editor_alive: Callable[[], bool] | None = None,
) -> tuple[dict[str, Any], _FakeClock]:
    clock = _FakeClock()
    status = _wait_for_runtime_peer(
        _sampler(script),
        is_editor_alive=is_editor_alive,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )
    return status, clock


def test_connects_after_the_legacy_15s_window() -> None:
    status, clock = _wait(
        [{"connected": False, "playing": True, "runtime_ready": False}] * 200
        + [{"connected": True, "playing": True, "runtime_ready": True}]
    )

    assert status["connected"] is True
    assert clock.now > live_godot_smoke.RUNTIME_PEER_START_GRACE


def test_keeps_waiting_while_the_peer_reports_runtime_ready() -> None:
    # runtime_ready is the debugger-session signal: it keeps the wait alive past
    # the start grace even when is_playing_scene() has not flipped yet.
    status, clock = _wait(
        [{"connected": False, "playing": False, "runtime_ready": True}] * 200
        + [{"connected": True, "playing": True, "runtime_ready": True}]
    )

    assert status["connected"] is True
    assert clock.now > live_godot_smoke.RUNTIME_PEER_START_GRACE


def test_fails_fast_when_the_gameplay_process_exits() -> None:
    with pytest.raises(RuntimeError, match="gameplay process exited"):
        _wait(
            [{"connected": False, "playing": True, "runtime_ready": False}] * 5
            + [{"connected": False, "playing": False, "runtime_ready": False}]
        )


def test_fails_fast_when_the_gameplay_process_exits_before_the_hard_timeout() -> None:
    clock = _FakeClock()
    with pytest.raises(RuntimeError, match="gameplay process exited"):
        _wait_for_runtime_peer(
            _sampler(
                [{"connected": False, "playing": True, "runtime_ready": False}] * 5
                + [{"connected": False, "playing": False, "runtime_ready": False}]
            ),
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )

    assert clock.now < live_godot_smoke.RUNTIME_PEER_TIMEOUT


def test_fails_when_the_gameplay_process_never_starts() -> None:
    with pytest.raises(RuntimeError, match="did not start"):
        _wait([{"connected": False, "playing": False, "runtime_ready": False}])


def test_fails_when_the_editor_exits() -> None:
    with pytest.raises(RuntimeError, match="editor exited"):
        _wait(
            [{"connected": False, "playing": True, "runtime_ready": False}],
            is_editor_alive=lambda: False,
        )


def test_reports_the_hard_timeout_for_a_stuck_peer() -> None:
    clock = _FakeClock()
    with pytest.raises(RuntimeError, match="did not connect within 90s"):
        _wait_for_runtime_peer(
            _sampler([{"connected": False, "playing": True, "runtime_ready": False}]),
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )

    assert clock.now >= live_godot_smoke.RUNTIME_PEER_TIMEOUT


def test_reports_the_last_status_on_failure() -> None:
    last_status = {"connected": False, "playing": True, "runtime_ready": False}
    with pytest.raises(RuntimeError, match="playing"):
        _wait([last_status], is_editor_alive=lambda: False)
