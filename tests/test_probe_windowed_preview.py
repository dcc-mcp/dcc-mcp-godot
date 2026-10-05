"""Unit coverage for the parts of the windowed lane that need no Godot host.

The lane itself only runs where a Godot binary and a windowed display both
exist, so its decision logic would otherwise be unverifiable in the unit
matrix. These tests pin that logic: which exit code each outcome maps to, that
a skipped lane never reports a pass, that the noise floor is summarised, that
the controls the lane relies on fail closed, that the CI gate only lets the
documented codes through, and that a harness fault is never downgraded into a
"not measured" warning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import probe_windowed_preview as probe
import pytest


def _receipt(measured: bool, passed: bool) -> dict[str, Any]:
    return {"measured": measured, "verdict": {"passed": passed, "failures": []}}


def test_a_passing_measurement_exits_zero() -> None:
    assert probe._exit_code(_receipt(measured=True, passed=True)) == probe.EXIT_MEASURED_PASS


def test_a_failing_measurement_exits_one() -> None:
    # A frame that was measured and missed the criteria is a real regression and
    # must turn the job red.
    assert probe._exit_code(_receipt(measured=True, passed=False)) == probe.EXIT_MEASURED_FAIL


def test_a_skipped_lane_exits_two_and_never_reports_a_pass() -> None:
    assert probe._exit_code(_receipt(measured=False, passed=False)) == probe.EXIT_NOT_MEASURED
    # The failure this lane exists to prevent: a green light it did not earn.
    assert probe._exit_code(_receipt(measured=False, passed=True)) == probe.EXIT_NOT_MEASURED


def test_blank_trap_control_rejects_an_all_black_frame() -> None:
    control = probe._blank_frame_control(320, 180)
    assert control["rejected"] is True
    assert control["rejected_by"] == "unique_colors"
    assert any("unique_colors" in item for item in control["failures"])
    assert control["metrics"]["width"] == 320
    assert control["metrics"]["height"] == 180


def test_noise_floor_reports_the_worst_repeat() -> None:
    floor = probe._noise_floor(
        [
            {"mean_delta": 0.0, "max_delta": 0, "different_pixel_pct": 0.0, "sha256_match": True},
            {"mean_delta": 0.5, "max_delta": 12, "different_pixel_pct": 0.4, "sha256_match": False},
            {"mean_delta": 0.1, "max_delta": 4, "different_pixel_pct": 0.1, "sha256_match": False},
        ]
    )
    assert floor["status"] == "measured"
    assert floor["repeats"] == 3
    assert floor["mean_delta_max"] == 0.5
    assert floor["max_delta_max"] == 12
    assert floor["different_pixel_pct_max"] == 0.4
    # One repeat differed, so this platform's floor is not byte-identical.
    assert floor["repeats_byte_identical"] is False


def test_noise_floor_is_marked_unmeasured_without_repeats() -> None:
    assert probe._noise_floor([]) == {"status": "not_measured", "repeats": 0}


def test_summary_marks_a_skipped_lane_as_not_coverage() -> None:
    receipt = {
        "measured": False,
        "tier": "B",
        "godot_version": "4.7.2.stable",
        "platform": {"system": "Linux"},
        "not_measured": {"reason": "no_frames_rendered", "detail": "tool refused"},
    }
    summary = probe._summary(receipt)
    assert "Not measured" in summary
    assert "no_frames_rendered" in summary
    # A skipped lane must say so, not hide behind an empty table.
    assert "PASS" not in summary
    assert "FAIL" not in summary


def test_summary_reports_the_noise_floor_of_a_measured_lane() -> None:
    receipt = {
        "measured": True,
        "tier": "B",
        "godot_version": "4.7.2.stable",
        "platform": {"system": "Linux"},
        "host": {
            "display_driver": "x11",
            "rendering_method": "gl_compatibility",
            "video_adapter": "llvmpipe",
            "has_rendering_device": False,
        },
        "request": {"calls": 5, "width": 1280, "height": 720},
        "calls_ok": 5,
        "reference_frame": {"metrics": {"bytes": 1, "unique_colors": 9317, "mean_luma": 150.0}},
        "noise_floor": {
            "status": "measured",
            "repeats": 4,
            "mean_delta_max": 0.0,
            "max_delta_max": 0,
            "different_pixel_pct_max": 0.0,
            "repeats_byte_identical": True,
        },
        "controls": {
            "blank_trap": {"rejected": True},
            "alt_camera": {
                "status": "measured",
                "mean_delta_vs_reference": 8.037,
                "different_pixel_pct": 96.36,
                "discriminating": True,
            },
        },
        "verdict": {"passed": True, "failures": []},
    }
    summary = probe._summary(receipt)
    assert "PASS" in summary
    assert "llvmpipe" in summary
    assert "8.037" in summary
    assert "noise floor" in summary


def test_a_connected_bridge_is_not_yet_a_ready_backend() -> None:
    # Regression: the first CI run had the editor attached to the loopback
    # bridge and still had every render call refused, because the adapter
    # publishes these bits from its own monitor rather than at connect time.
    ci_refusal = {
        "process": True,
        "dcc": False,
        "skill_catalog": True,
        "dispatcher": True,
        "host_execution_bridge": False,
        "main_thread_executor": False,
    }
    assert probe._readiness_ready(ci_refusal) is False


def test_readiness_needs_every_execution_bit() -> None:
    ready = {bit: True for bit in probe.READINESS_BITS}
    assert probe._readiness_ready(ready) is True
    for bit in probe.READINESS_BITS:
        assert probe._readiness_ready({**ready, bit: False}) is False
    assert probe._readiness_ready({}) is False


def test_the_lane_waits_for_readiness_before_rendering() -> None:
    # The wait is what turns the CI refusal into a measured run, so it has to
    # stay between the tool lookup and the first render call.
    source = (probe.REPO / "tests" / "probe_windowed_preview.py").read_text(encoding="utf-8")
    resolved = source.index('receipt["tool_name"] = tool_name')
    waited = source.index("_wait_for_ready(mcp_url)")
    first_call = source.index("tool_name,\n                {")
    assert resolved < waited < first_call


def test_the_lane_never_hides_the_window_by_minimizing() -> None:
    # Minimizing reports success with an all-black frame under gl_compatibility,
    # so the lane asks for no hiding at all and runs on a private display.
    source = (probe.REPO / "tests" / "probe_windowed_preview.py").read_text(encoding="utf-8")
    assert "WINDOW_MODE_MINIMIZED" not in source
    assert 'environment["DCC_MCP_GODOT_HIDE_WINDOW"] = "0"' in source


def test_the_lane_renders_the_committed_probe_scene() -> None:
    scene = (probe.REPO / "tests" / "godot_project" / "preview_probe.tscn").read_text(
        encoding="utf-8"
    )
    assert probe.SCENE_RESOURCE == "res://preview_probe.tscn"
    assert f'[node name="{probe.ALT_CAMERA}" type="Camera3D" parent="."]' in scene
    assert '[node name="Camera" type="Camera3D" parent="."]' in scene


@pytest.mark.parametrize("driver", ["opengl3"])
def test_the_editor_command_stays_windowed(driver: str) -> None:
    # --headless is exactly what makes the host refuse scene previews.
    command = probe._editor_command(
        godot=probe.Path("/tmp/godot"),
        project=probe.Path("/tmp/project"),
        driver=driver,
        wrap_xvfb=False,
    )
    assert "--headless" not in command
    assert "--editor" in command
    assert driver in command


def test_xvfb_wrapping_asks_for_a_24_bit_screen() -> None:
    # xvfb-run's default screen is 8-bit pseudocolour and cannot host a GLX
    # context, so Godot would fall back to a driver that reads back nothing.
    command = probe._editor_command(
        godot=probe.Path("/tmp/godot"),
        project=probe.Path("/tmp/project"),
        driver="opengl3",
        wrap_xvfb=True,
    )
    assert command[0] == "xvfb-run"
    assert probe.XVFB_SERVER_ARGS in command
    assert "24" in probe.XVFB_SERVER_ARGS


def test_the_gate_passes_only_the_two_documented_codes() -> None:
    assert probe.gate_decision("0") == {"outcome": "pass", "exit": 0, "message": ""}
    skip = probe.gate_decision("2")
    assert skip["outcome"] == "skip"
    assert skip["exit"] == 0
    assert "not measured" in skip["message"]


@pytest.mark.parametrize("code", ["1", "3", "126", "127", "137", "", "abc", "0\n", "00"])
def test_the_gate_fails_every_other_exit_code(code: str) -> None:
    # 127 is a missing interpreter and "" is what an if: always() step reads when
    # the probe step never ran at all. The old gate only listed the code it
    # wanted to fail, so both fell through to a green job.
    decision = probe.gate_decision(code)
    assert decision["outcome"] == "fail"
    assert decision["exit"] == 1
    assert decision["message"]


def test_the_controls_pass_only_when_both_checks_held() -> None:
    controls = {
        "blank_trap": {"rejected": True},
        "alt_camera": {"status": "measured", "discriminating": True},
    }
    assert probe._control_failures(controls) == []


def test_a_vacuous_alt_camera_fails_the_verdict() -> None:
    controls = {
        "blank_trap": {"rejected": True},
        "alt_camera": {
            "status": "measured",
            "discriminating": False,
            "mean_delta_vs_reference": 0.0,
        },
    }
    failures = probe._control_failures(controls)
    assert len(failures) == 1
    assert "vacuous" in failures[0]


@pytest.mark.parametrize("status", ["inconclusive", "skipped", None])
def test_an_alt_camera_that_was_never_measured_fails_the_verdict(status: str | None) -> None:
    # Regression: "inconclusive" used to fall through as if the control had been
    # checked, so a comparison that never ran counted as a passing control.
    controls = {"blank_trap": {"rejected": True}, "alt_camera": {"status": status}}
    failures = probe._control_failures(controls)
    assert len(failures) == 1
    assert "never measured" in failures[0]


def test_missing_controls_fail_closed() -> None:
    failures = probe._control_failures({})
    assert any("blank trap" in item for item in failures)
    assert any("never measured" in item for item in failures)


def test_a_harness_fault_after_measuring_is_a_failed_measurement() -> None:
    # The defect that blocked this lane: exit 2 is the one code the gate lets
    # through with a warning, so folding a post-measure crash into "not measured"
    # turned a real regression into a green job.
    receipt = {"measured": True, "verdict": {"passed": True, "failures": []}}
    faulted = probe._harness_faulted_receipt(receipt, "Traceback: boom")
    assert faulted["measured"] is True
    assert faulted["verdict"]["passed"] is False
    assert faulted["harness_error"] == "Traceback: boom"
    assert probe._exit_code(faulted) == probe.EXIT_MEASURED_FAIL
    # The original receipt is not mutated behind the caller's back.
    assert receipt["verdict"]["passed"] is True


def test_a_harness_fault_before_measuring_stays_not_measured() -> None:
    faulted = probe._harness_faulted_receipt({"measured": False}, "Traceback: boom")
    assert faulted["not_measured"]["reason"] == "harness_error"
    assert probe._exit_code(faulted) == probe.EXIT_NOT_MEASURED


def test_the_not_measured_receipt_keeps_what_the_lane_learned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Regression: the skip path rebuilt a bare receipt, so a lane that died at
    # the editor step lost the platform, the Godot version and the
    # install/bootstrap outcome that make the skip diagnosable at all.
    def fake_probe(**kwargs: Any) -> dict[str, Any]:
        kwargs["receipt_sink"].update(
            {
                "lane": "windowed-render-scene-preview",
                "measured": False,
                "tier": "B",
                "platform": {"system": "Linux"},
                "godot_version": "4.7.2.stable",
                "install": {"exit_code": 50, "status": "requires_restart"},
                "bootstrap": {"status": "ready"},
                "editor_command": ["godot", "--editor"],
                "verdict": {"passed": False, "failures": []},
            }
        )
        raise probe.NotMeasured("editor_did_not_connect", "timed out")

    monkeypatch.setattr(probe, "probe", fake_probe)
    monkeypatch.setattr(
        sys, "argv", ["probe", "--godot", "godot", "--out", str(tmp_path), "--tier", "B"]
    )
    assert probe.main() == probe.EXIT_NOT_MEASURED
    receipt = json.loads((tmp_path / "preview-probe.json").read_text(encoding="utf-8"))
    assert receipt["platform"]["system"] == "Linux"
    assert receipt["godot_version"] == "4.7.2.stable"
    assert receipt["install"]["status"] == "requires_restart"
    assert receipt["bootstrap"]["status"] == "ready"
    assert receipt["editor_command"] == ["godot", "--editor"]
    assert receipt["not_measured"]["reason"] == "editor_did_not_connect"


def test_the_lane_commits_to_a_measurement_before_decoding_frames() -> None:
    # Regression: the frames were decoded while `measured` was still False, so a
    # host that wrote PNGs we cannot read back produced exit 2 -- the one code
    # the gate lets through with a warning -- and the job went green with no
    # coverage. Having the files on disk, not being able to decode them, is what
    # turns this into a measurement worth failing over. Nothing else in the file
    # pinned this order, so a refactor could have reverted it silently.
    source = (probe.REPO / "tests" / "probe_windowed_preview.py").read_text(encoding="utf-8")
    commit = source.find('if frames:\n            receipt["measured"] = True')
    decode = source.find('receipt["frames"] = [')
    assert commit != -1, "the lane no longer commits to a measurement before decoding"
    assert decode != -1, "the lane no longer decodes into receipt['frames']"
    assert commit < decode
    # The unconditional marker further down must stay later than the decode.
    assert source.rindex('receipt["measured"] = True') > decode
