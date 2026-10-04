"""Unit coverage for the lifecycle-verify retry in the live Godot smoke harness."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
from typing import Any, Callable

import pytest

ROOT = Path(__file__).parents[1]
SMOKE_PATH = ROOT / "tests" / "live_godot_smoke.py"
SMOKE_SPEC = importlib.util.spec_from_file_location("dcc_mcp_godot_live_godot_smoke", SMOKE_PATH)
assert SMOKE_SPEC is not None and SMOKE_SPEC.loader is not None
SMOKE = importlib.util.module_from_spec(SMOKE_SPEC)
SMOKE_SPEC.loader.exec_module(SMOKE)

PROJECT = Path("/tmp/dcc-mcp-godot-smoke-project")


def _verify_payload(*, usable: bool, stage: str | None = None, reason: str | None = None) -> str:
    verify: dict[str, Any] = {"directly_usable": usable}
    if stage is not None:
        verify["failure_stage"] = stage
    if reason is not None:
        verify["failure_reason"] = reason
    return json.dumps({"status": "verified" if usable else "failed", "verify": verify})


def _torn_payload() -> str:
    return _verify_payload(
        usable=False,
        stage=SMOKE.VERIFY_ABSENT_STAGE,
        reason=SMOKE.VERIFY_ABSENT_REASON,
    )


def _install_main(
    payload: str, exit_code: int
) -> tuple[Callable[[list[str]], int], list[list[str]]]:
    """Return a stub ``install_main`` replaying one fixed result, plus its call log."""
    calls: list[list[str]] = []

    def fake(argv: list[str]) -> int:
        calls.append(argv)
        print(payload)
        return exit_code

    return fake, calls


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SMOKE.time, "sleep", lambda _seconds: None)


def test_verify_accepts_the_first_usable_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, calls = _install_main(_verify_payload(usable=True), 0)
    monkeypatch.setattr(SMOKE, "install_main", fake)

    result = SMOKE._run_lifecycle_verify(PROJECT, "instance-1")

    assert result["verify"]["directly_usable"] is True
    assert len(calls) == 1
    assert calls[0][:2] == ["verify", str(PROJECT)]
    assert calls[0][calls[0].index("--instance-id") + 1] == "instance-1"


def test_verify_retries_a_torn_install_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    payloads = iter([_torn_payload(), _torn_payload(), _verify_payload(usable=True)])
    calls: list[list[str]] = []

    def fake(argv: list[str]) -> int:
        calls.append(argv)
        print(next(payloads))
        return 0

    monkeypatch.setattr(SMOKE, "install_main", fake)

    result = SMOKE._run_lifecycle_verify(PROJECT, "instance-1")

    assert result["verify"]["directly_usable"] is True
    assert len(calls) == SMOKE.VERIFY_INSTALL_ATTEMPTS


def test_verify_gives_up_after_the_attempt_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, calls = _install_main(_torn_payload(), 1)
    monkeypatch.setattr(SMOKE, "install_main", fake)

    with pytest.raises(RuntimeError, match="lifecycle verify failed"):
        SMOKE._run_lifecycle_verify(PROJECT, "instance-1")

    assert len(calls) == SMOKE.VERIFY_INSTALL_ATTEMPTS


def test_verify_does_not_retry_other_failure_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _verify_payload(usable=False, stage="readiness", reason="instance is not ready")
    fake, calls = _install_main(payload, 1)
    monkeypatch.setattr(SMOKE, "install_main", fake)

    with pytest.raises(RuntimeError, match="lifecycle verify failed"):
        SMOKE._run_lifecycle_verify(PROJECT, "instance-1")

    assert len(calls) == 1


def test_verify_does_not_retry_a_different_install_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _verify_payload(usable=False, stage="install", reason="receipt is not owned")
    fake, calls = _install_main(payload, 1)
    monkeypatch.setattr(SMOKE, "install_main", fake)

    with pytest.raises(RuntimeError, match="lifecycle verify failed"):
        SMOKE._run_lifecycle_verify(PROJECT, "instance-1")

    assert len(calls) == 1


def test_verify_rejects_a_zero_exit_without_direct_usability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake, calls = _install_main(_verify_payload(usable=False), 0)
    monkeypatch.setattr(SMOKE, "install_main", fake)

    with pytest.raises(RuntimeError, match="lifecycle verify failed"):
        SMOKE._run_lifecycle_verify(PROJECT, "instance-1")

    assert len(calls) == 1


def test_verify_keeps_install_json_off_the_smoke_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake, _calls = _install_main(_verify_payload(usable=True), 0)
    monkeypatch.setattr(SMOKE, "install_main", fake)
    noise = io.StringIO()

    with contextlib.redirect_stdout(noise):
        SMOKE._run_lifecycle_verify(PROJECT, "instance-1")

    assert noise.getvalue() == ""
