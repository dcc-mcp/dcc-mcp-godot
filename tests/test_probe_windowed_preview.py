"""Unit coverage for the parts of the windowed lane that need no Godot host.

The lane itself only runs where a Godot binary and a windowed display both
exist, so its decision logic would otherwise be unverifiable in the unit
matrix. These tests pin that logic: which exit code each outcome maps to, that
a skipped lane never reports a pass, that the noise floor is summarised, and
that the controls the lane relies on actually reject a trap frame.
"""

from __future__ import annotations

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
