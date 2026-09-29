"""Contract tests for the unattended scene-preview render path.

These guard the decisions measured on a real Windows Godot 4.7.2 host, so a
later refactor cannot quietly reintroduce a silently-blank frame, a hidden
fallback to another rendering backend, or the minimized-window black-frame trap.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
CAPABILITIES = ROOT / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot/capabilities.gd"
PLUGIN = ROOT / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot/plugin.gd"


def _function(source: str, name: str, following: str) -> str:
    return source.split(f"func {name}", 1)[1].split(f"func {following}", 1)[0]


def _capabilities() -> str:
    return CAPABILITIES.read_text(encoding="utf-8")


def test_render_scene_preview_refuses_a_headless_host_instead_of_blanking() -> None:
    # --headless degrades Godot to rendering/dummy, where an offscreen
    # SubViewport reads back nothing at all. Returning a PNG there would look
    # like success, so the host must refuse before it ever renders.
    body = _function(_capabilities(), "_render_scene_preview(", "has_pending_preview")
    assert "var display_driver := DisplayServer.get_name()" in body
    assert 'if display_driver == "headless":' in body
    # The refusal happens before any viewport is created.
    assert body.index('display_driver == "headless"') < body.index("SubViewport.new()")
    assert "--headless" in body


def test_render_scene_preview_never_silently_falls_back_to_another_backend() -> None:
    # Cross-renderer frames differ by mean_delta 0.912/255 with 71.2% of pixels
    # changed, so an unreported backend switch destroys the comparison baseline.
    body = _function(_capabilities(), "_render_scene_preview(", "has_pending_preview")
    assert 'params.get("rendering_method", "")' in body
    assert "requested_method != rendering_method" in body
    assert "silently fall back" in body


def test_render_scene_preview_echoes_the_render_contract_fields() -> None:
    finish = (
        _capabilities()
        .split("func _finish_pending_preview", 1)[1]
        .split("func _free_preview_viewport", 1)[0]
    )
    for field in (
        '"path"',
        '"width"',
        '"height"',
        '"rendering_method"',
        '"display_driver"',
        '"scene_path"',
        '"camera_source"',
        '"frame_count"',
    ):
        assert field in finish, field


def test_render_scene_preview_keeps_png_encoding_off_the_host_thread() -> None:
    # The PNG encode dominates the main-thread cost; pixels are staged raw and
    # encoded by the adapter, exactly like the existing screenshot tools.
    body = (
        _capabilities()
        .split("func _render_scene_preview", 1)[1]
        .split("func _free_preview_viewport", 1)[0]
    )
    assert "__raw_snapshot__" in body
    assert "save_png" not in body


def test_render_scene_preview_parks_the_request_for_real_frames() -> None:
    # Measured: every synchronous draw path returns a fully blank frame here,
    # so the render is advanced by real editor frames, not by force_draw.
    setup = _function(_capabilities(), "_render_scene_preview(", "has_pending_preview")
    assert '"__deferred_preview__"' in setup
    assert "RenderingServer.force_draw" not in setup
    assert _capabilities().count("func poll_pending_preview") == 1


def test_framing_camera_never_minimizes_and_only_frames_geometry() -> None:
    source = _capabilities()
    # Minimizing under gl_compatibility reports success with an all-black frame.
    assert "WINDOW_MODE_MINIMIZED" not in source
    # Lights and probes carry helper AABBs that drag the framing centre away.
    collect = source.split("func _collect_preview_bounds", 1)[1].split("func _framed", 1)[0]
    assert "node is GeometryInstance3D" in collect
    # No other branch may add a bounding box to the framing set.
    assert collect.count("entries.append(") == 1
    assert "Light3D" not in collect


def test_framing_camera_orients_while_detached() -> None:
    # look_at() is a no-op outside the tree; the camera is added to the preview
    # viewport only after it is configured.
    framed = _capabilities().split("func _framed_preview_camera", 1)[1].split("\n\n\n", 1)[0]
    assert "look_at_from_position(" in framed
    assert "camera.look_at(" not in framed


def test_plugin_parks_deferred_previews_and_reports_mode() -> None:
    source = PLUGIN.read_text(encoding="utf-8")
    assert "__deferred_preview__" in source
    assert "_advance_pending_preview" in source
    # A parked request must not hang forever if the editor stops ticking.
    assert "PREVIEW_REQUEST_TIMEOUT_MS" in source
    assert "did not finish" in source


def test_generated_editor_skill_declares_the_preview_tool() -> None:
    tools = (ROOT / "src/dcc_mcp_godot/skills/godot-editor/tools.yaml").read_text(encoding="utf-8")
    block = re.search(
        r"(?ms)^  - name: render_scene_preview\n(?P<body>.*?)(?=^  - name: |\Z)", tools
    )
    assert block is not None
    body = block.group("body")
    # Rendered on the main lane so a later same-path publisher cannot overtake
    # an earlier one, and read-only because it never mutates the scene.
    assert "\n    execution: sync\n" in body
    assert "\n    affinity: main\n" in body
    assert "\n    read_only: true\n" in body
    for field in ("scene_path", "camera_path", "rendering_method", "frame_count"):
        assert field in body, field


@pytest.mark.parametrize(
    "expression",
    [
        'params.get("width"',
        'params.get("height"',
        'params.get("frame_count"',
        'params.get("scene_path"',
    ],
)
def test_render_scene_preview_accepts_the_declared_inputs(expression: str) -> None:
    body = _function(_capabilities(), "_render_scene_preview(", "has_pending_preview")
    assert expression in body
