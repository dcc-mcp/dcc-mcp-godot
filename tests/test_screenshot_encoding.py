import base64
import struct
import zlib
from pathlib import Path

import pytest

from dcc_mcp_godot import capability_dispatch, screenshot
from dcc_mcp_godot.screenshot import finalize_screenshot, finalize_screenshot_batch


def test_game_screenshot_encodes_immutable_host_snapshot_off_the_godot_thread(
    monkeypatch, tmp_path
):
    raw_path = tmp_path / "game.png.dcc-mcp-1.raw"
    output_path = tmp_path / "game.png"
    pixels = bytes((255, 0, 0, 255, 0, 255, 0, 128))
    raw_path.write_bytes(pixels)
    host_calls = []

    def call_host(method, params):
        host_calls.append((method, params))
        return {
            "path": "res://.dcc-mcp/game.png",
            "width": 2,
            "height": 1,
            "__raw_snapshot__": {
                "path": str(raw_path),
                "output_path": str(output_path),
                "format": "rgba8",
                "byte_length": len(pixels),
            },
        }

    monkeypatch.setattr(capability_dispatch, "call_host", call_host)

    result = capability_dispatch.dispatch(
        "get_game_screenshot", {"path": "res://.dcc-mcp/game.png"}
    )

    assert host_calls == [("capability.get_game_screenshot", {"path": "res://.dcc-mcp/game.png"})]
    assert result["context"] == {
        "path": "res://.dcc-mcp/game.png",
        "width": 2,
        "height": 1,
    }
    png = output_path.read_bytes()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", png[16:24]) == (2, 1)
    idat_size = struct.unpack(">I", png[33:37])[0]
    assert zlib.decompress(png[41 : 41 + idat_size]) == b"\x00" + pixels
    assert not raw_path.exists()


def test_game_screenshot_base64_is_derived_from_the_off_thread_png(monkeypatch, tmp_path):
    raw_path = tmp_path / "game.png.dcc-mcp-2.raw"
    output_path = tmp_path / "game.png"
    raw_path.write_bytes(bytes((10, 20, 30)))
    monkeypatch.setattr(
        capability_dispatch,
        "call_host",
        lambda _method, _params: {
            "path": "res://.dcc-mcp/game.png",
            "width": 1,
            "height": 1,
            "__raw_snapshot__": {
                "path": str(raw_path),
                "output_path": str(output_path),
                "format": "rgb8",
                "byte_length": 3,
            },
        },
    )

    result = capability_dispatch.dispatch("get_game_screenshot", {"include_base64": True})

    assert base64.b64decode(result["context"]["png_base64"]) == output_path.read_bytes()
    assert not raw_path.exists()


def test_editor_screenshot_uses_the_same_off_thread_finalizer(monkeypatch, tmp_path):
    raw_path = tmp_path / "editor.png.dcc-mcp-1.raw"
    output_path = tmp_path / "editor.png"
    raw_path.write_bytes(bytes((9, 8, 7)))
    monkeypatch.setattr(
        capability_dispatch,
        "call_host",
        lambda _method, _params: {
            "path": "res://.dcc-mcp/editor.png",
            "width": 1,
            "height": 1,
            "__raw_snapshot__": {
                "path": str(raw_path),
                "output_path": str(output_path),
                "format": "rgb8",
                "byte_length": 3,
            },
        },
    )

    result = capability_dispatch.dispatch("get_editor_screenshot", {})

    assert result["context"]["path"] == "res://.dcc-mcp/editor.png"
    assert output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert not raw_path.exists()


def test_screenshot_snapshot_size_mismatch_fails_closed_and_removes_staging_file(tmp_path):
    raw_path = tmp_path / "game.png.dcc-mcp-3.raw"
    output_path = tmp_path / "game.png"
    raw_path.write_bytes(b"too-short")

    with pytest.raises(ValueError, match="byte length"):
        finalize_screenshot(
            {
                "path": "res://.dcc-mcp/game.png",
                "width": 2,
                "height": 2,
                "__raw_snapshot__": {
                    "path": str(raw_path),
                    "output_path": str(output_path),
                    "format": "rgba8",
                    "byte_length": 9,
                },
            }
        )

    assert not raw_path.exists()
    assert not output_path.exists()


def test_same_path_screenshot_error_does_not_poison_the_next_call(monkeypatch, tmp_path):
    failed_raw_path = tmp_path / "game.png.dcc-mcp-failed.raw"
    next_raw_path = tmp_path / "game.png.dcc-mcp-next.raw"
    output_path = tmp_path / "game.png"
    failed_raw_path.write_bytes(b"in")
    next_pixels = bytes((7, 11, 13))
    next_raw_path.write_bytes(next_pixels)
    snapshots = iter(
        (
            {
                "path": "res://.dcc-mcp/game.png",
                "width": 1,
                "height": 1,
                "__raw_snapshot__": {
                    "path": str(failed_raw_path),
                    "output_path": str(output_path),
                    "format": "rgb8",
                    "byte_length": 3,
                },
            },
            {
                "path": "res://.dcc-mcp/game.png",
                "width": 1,
                "height": 1,
                "__raw_snapshot__": {
                    "path": str(next_raw_path),
                    "output_path": str(output_path),
                    "format": "rgb8",
                    "byte_length": 3,
                },
            },
        )
    )
    monkeypatch.setattr(capability_dispatch, "call_host", lambda _method, _params: next(snapshots))

    with pytest.raises(ValueError, match="incomplete"):
        capability_dispatch.dispatch("get_game_screenshot", {"include_base64": True})

    result = capability_dispatch.dispatch("get_game_screenshot", {"include_base64": True})

    assert not failed_raw_path.exists()
    assert not next_raw_path.exists()
    assert base64.b64decode(result["context"]["png_base64"]) == output_path.read_bytes()


def test_capture_frames_finalizes_each_immutable_snapshot_off_the_godot_thread(tmp_path):
    first_raw = tmp_path / "frame_000.png.dcc-mcp-1.raw"
    second_raw = tmp_path / "frame_001.png.dcc-mcp-2.raw"
    first_output = tmp_path / "frame_000.png"
    second_output = tmp_path / "frame_001.png"
    first_raw.write_bytes(bytes((1, 2, 3)))
    second_raw.write_bytes(bytes((4, 5, 6)))
    first_output.write_bytes(b"old-first")
    second_output.write_bytes(b"old-second")

    result = finalize_screenshot_batch(
        {
            "paths": ["res://.dcc-mcp/frame_000.png", "res://.dcc-mcp/frame_001.png"],
            "count": 2,
            "__raw_snapshots__": [
                {
                    "path": str(first_raw),
                    "output_path": str(first_output),
                    "format": "rgb8",
                    "byte_length": 3,
                    "width": 1,
                    "height": 1,
                },
                {
                    "path": str(second_raw),
                    "output_path": str(second_output),
                    "format": "rgb8",
                    "byte_length": 3,
                    "width": 1,
                    "height": 1,
                },
            ],
        }
    )

    assert result["paths"] == ["res://.dcc-mcp/frame_000.png", "res://.dcc-mcp/frame_001.png"]
    assert first_output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert second_output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert not first_raw.exists()
    assert not second_raw.exists()


def test_capture_frames_batch_failure_is_atomic_and_cleans_all_staging(tmp_path):
    first_raw = tmp_path / "frame_000.png.dcc-mcp-1.raw"
    second_raw = tmp_path / "frame_001.png.dcc-mcp-2.raw"
    first_output = tmp_path / "frame_000.png"
    second_output = tmp_path / "frame_001.png"
    first_raw.write_bytes(bytes((1, 2, 3)))
    second_raw.write_bytes(bytes((4, 5, 6)))

    with pytest.raises(ValueError, match="byte length"):
        finalize_screenshot_batch(
            {
                "__raw_snapshots__": [
                    {
                        "path": str(first_raw),
                        "output_path": str(first_output),
                        "format": "rgb8",
                        "byte_length": 3,
                        "width": 1,
                        "height": 1,
                    },
                    {
                        "path": str(second_raw),
                        "output_path": str(second_output),
                        "format": "rgb8",
                        "byte_length": 4,
                        "width": 1,
                        "height": 1,
                    },
                ]
            }
        )

    assert not first_output.exists()
    assert not second_output.exists()
    assert not first_raw.exists()
    assert not second_raw.exists()


def test_capture_frames_batch_publish_failure_rolls_back_outputs_and_staging(monkeypatch, tmp_path):
    first_raw = tmp_path / "frame_000.png.dcc-mcp-1.raw"
    second_raw = tmp_path / "frame_001.png.dcc-mcp-2.raw"
    first_output = tmp_path / "frame_000.png"
    second_output = tmp_path / "frame_001.png"
    first_raw.write_bytes(bytes((1, 2, 3)))
    second_raw.write_bytes(bytes((4, 5, 6)))
    first_output.write_bytes(b"old-first")
    second_output.write_bytes(b"old-second")
    replace = screenshot.os.replace
    calls = 0

    def fail_on_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated publish failure")
        return replace(source, destination)

    monkeypatch.setattr(screenshot.os, "replace", fail_on_second_replace)

    with pytest.raises(OSError, match="simulated publish failure"):
        finalize_screenshot_batch(
            {
                "__raw_snapshots__": [
                    {
                        "path": str(first_raw),
                        "output_path": str(first_output),
                        "format": "rgb8",
                        "byte_length": 3,
                        "width": 1,
                        "height": 1,
                    },
                    {
                        "path": str(second_raw),
                        "output_path": str(second_output),
                        "format": "rgb8",
                        "byte_length": 3,
                        "width": 1,
                        "height": 1,
                    },
                ]
            }
        )

    assert first_output.read_bytes() == b"old-first"
    assert second_output.read_bytes() == b"old-second"
    assert not first_raw.exists()
    assert not second_raw.exists()


def _preview_snapshot(raw_path, output_path, pixels: bytes, *, width: int, height: int) -> dict:
    raw_path.write_bytes(pixels)
    return {
        "path": "res://.dcc-mcp/preview/scene.png",
        "width": width,
        "height": height,
        "rendering_method": "gl_compatibility",
        "__raw_snapshot__": {
            "path": str(raw_path),
            "output_path": str(output_path),
            "format": "rgba8",
            "byte_length": len(pixels),
        },
    }


def test_scene_preview_publishes_bytes_and_unique_color_evidence(monkeypatch, tmp_path):
    raw_path = tmp_path / "scene.png.dcc-mcp-1.raw"
    output_path = tmp_path / "scene.png"
    # Four distinct RGBA pixels: the unique-color count is the caller's proof
    # that the frame carries real shading instead of a silent blank render.
    pixels = bytes((10, 20, 30, 255, 11, 21, 31, 255, 200, 90, 40, 255, 201, 91, 41, 255))
    monkeypatch.setattr(
        capability_dispatch,
        "call_host",
        lambda _method, _params: _preview_snapshot(
            raw_path, output_path, pixels, width=2, height=2
        ),
    )

    result = capability_dispatch.dispatch(
        "render_scene_preview", {"scene_path": "res://scene.tscn"}
    )

    context = result["context"]
    assert context["width"] == 2 and context["height"] == 2
    assert context["unique_colors"] == 4
    assert context["bytes"] == len(output_path.read_bytes())
    assert context["bytes"] > 0
    assert context["path"] == "res://.dcc-mcp/preview/scene.png"
    assert not raw_path.exists()


def test_scene_preview_reports_a_single_color_for_a_blank_frame(monkeypatch, tmp_path):
    # A trap frame collapses to one colour, which the caller's
    # unique_colors > 1000 acceptance guard is built to reject.
    raw_path = tmp_path / "scene.png.dcc-mcp-2.raw"
    output_path = tmp_path / "scene.png"
    pixels = bytes((0, 0, 0, 255)) * 4
    monkeypatch.setattr(
        capability_dispatch,
        "call_host",
        lambda _method, _params: _preview_snapshot(
            raw_path, output_path, pixels, width=2, height=2
        ),
    )

    result = capability_dispatch.dispatch("render_scene_preview", {})

    assert result["context"]["unique_colors"] == 1
    assert not raw_path.exists()


def test_scene_preview_leaves_plain_screenshots_without_extra_fields(monkeypatch, tmp_path):
    raw_path = tmp_path / "game.png.dcc-mcp-3.raw"
    output_path = tmp_path / "game.png"
    raw_path.write_bytes(bytes((255, 0, 0, 255)))
    monkeypatch.setattr(
        capability_dispatch,
        "call_host",
        lambda _method, _params: {
            "path": "res://.dcc-mcp/game.png",
            "width": 1,
            "height": 1,
            "__raw_snapshot__": {
                "path": str(raw_path),
                "output_path": str(output_path),
                "format": "rgba8",
                "byte_length": 4,
            },
        },
    )

    result = capability_dispatch.dispatch("get_game_screenshot", {})

    assert "unique_colors" not in result["context"]
    assert "bytes" not in result["context"]


def test_unique_color_count_matches_a_shaded_frame_at_preview_scale():
    width, height = 128, 72
    pixels = bytearray()
    for index in range(width * height):
        pixels += bytes((index % 256, (index * 7) % 256, (index * 13) % 256, 255))

    assert screenshot.count_unique_colors(bytes(pixels), channels=4) == len(
        {bytes(pixels[offset : offset + 4]) for offset in range(0, len(pixels), 4)}
    )


# The PNG signature, spelled out so this decoder does not inherit the bytes
# from the encoder it is supposed to check.
_PNG_SIGNATURE = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))
_PNG_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}


def _decode_png(data: bytes) -> tuple:
    """Decode a non-interlaced 8-bit PNG, validating every chunk CRC.

    This walks the stream the way a standard decoder does, so a bad CRC, a
    wrong chunk length, an unexpected bit depth or a filter type the encoder
    never emits all fail here instead of silently yielding a broken image.
    """
    assert data.startswith(_PNG_SIGNATURE)
    offset = len(_PNG_SIGNATURE)
    chunks: list = []
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        (crc,) = struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])
        assert crc == zlib.crc32(kind + payload) & 0xFFFFFFFF, "bad CRC in %r" % (kind,)
        chunks.append((kind, payload))
        offset += 12 + length
    assert chunks[0][0] == b"IHDR"
    assert chunks[-1][0] == b"IEND"
    width, height, depth, color_type, compression, filt, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    assert (depth, compression, filt, interlace) == (8, 0, 0, 0)
    channels = _PNG_CHANNELS[color_type]
    raw = zlib.decompress(b"".join(payload for kind, payload in chunks if kind == b"IDAT"))
    stride = width * channels
    assert len(raw) == height * (stride + 1), "scanline stream has the wrong length"
    pixels = bytearray()
    for row in range(height):
        start = row * (stride + 1)
        assert raw[start] == 0, "only filter type 0 is emitted"
        pixels += raw[start + 1 : start + 1 + stride]
    return width, height, bytes(pixels)


def test_scene_preview_png_decodes_back_to_the_requested_dimensions(monkeypatch, tmp_path):
    # Acceptance: the new render path must produce a PNG a standard decoder can
    # open, with dimensions matching the request and bytes > 0.
    raw_path = tmp_path / "scene.png.dcc-mcp-1.raw"
    output_path = tmp_path / "scene.png"
    width, height = 3, 2
    pixels = b"".join(
        bytes((index % 256, (index * 7) % 256, (index * 13) % 256, 255))
        for index in range(width * height)
    )
    monkeypatch.setattr(
        capability_dispatch,
        "call_host",
        lambda _method, _params: _preview_snapshot(
            raw_path, output_path, pixels, width=width, height=height
        ),
    )

    result = capability_dispatch.dispatch(
        "render_scene_preview", {"width": width, "height": height}
    )

    context = result["context"]
    assert context["width"] == width and context["height"] == height
    decoded_width, decoded_height, decoded_pixels = _decode_png(output_path.read_bytes())
    assert (decoded_width, decoded_height) == (width, height)
    assert decoded_pixels == pixels
    assert context["bytes"] == len(output_path.read_bytes())
    assert context["bytes"] > 0
    assert not raw_path.exists()


def test_scene_preview_metrics_read_the_staging_file_exactly_once(monkeypatch, tmp_path):
    # Regression: unique_colors used to re-read the staging file after the
    # validation pass had already read it, doubling the I/O of every frame and
    # letting the file change underneath the snapshot that was validated.
    raw_path = tmp_path / "scene.png.dcc-mcp-1.raw"
    output_path = tmp_path / "scene.png"
    pixels = bytes((10, 20, 30, 255, 11, 21, 31, 255, 200, 90, 40, 255, 201, 91, 41, 255))
    monkeypatch.setattr(
        capability_dispatch,
        "call_host",
        lambda _method, _params: _preview_snapshot(
            raw_path, output_path, pixels, width=2, height=2
        ),
    )
    real_read_bytes = Path.read_bytes
    reads: list = []

    def counting_read_bytes(self):
        if self.suffix == ".raw":
            reads.append(self)
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)

    result = capability_dispatch.dispatch("render_scene_preview", {})

    assert result["context"]["unique_colors"] == 4
    assert reads == [raw_path]


def test_scene_preview_malformed_snapshot_fails_closed_with_half_published_evidence(tmp_path):
    # A truncated staging file must not publish a PNG, must not leave staging
    # behind, and must not report bytes/unique_colors as if a frame existed.
    raw_path = tmp_path / "scene.png.dcc-mcp-1.raw"
    output_path = tmp_path / "scene.png"
    raw_path.write_bytes(b"truncated")
    output_path.write_bytes(b"previous-render")
    result = {
        "path": "res://.dcc-mcp/preview/scene.png",
        "width": 2,
        "height": 2,
        "rendering_method": "gl_compatibility",
        "__raw_snapshot__": {
            "path": str(raw_path),
            "output_path": str(output_path),
            "format": "rgba8",
            "byte_length": 16,
        },
    }

    with pytest.raises(ValueError, match="incomplete"):
        finalize_screenshot(result, with_metrics=True)

    assert not raw_path.exists()
    assert output_path.read_bytes() == b"previous-render"
    assert "bytes" not in result
    assert "unique_colors" not in result


def test_scene_preview_unknown_format_fails_closed_instead_of_bypassing_the_encoder(tmp_path):
    # The new path must go through the shared format table: an unknown format
    # is an error to extend _FORMATS for, not a reason to add a parallel encoder.
    raw_path = tmp_path / "scene.png.dcc-mcp-1.raw"
    output_path = tmp_path / "scene.png"
    raw_path.write_bytes(bytes((1, 2, 3, 4)))

    with pytest.raises(ValueError, match="Unsupported Godot screenshot format"):
        finalize_screenshot(
            {
                "path": "res://.dcc-mcp/preview/scene.png",
                "width": 1,
                "height": 1,
                "__raw_snapshot__": {
                    "path": str(raw_path),
                    "output_path": str(output_path),
                    "format": "rgbf16",
                    "byte_length": 4,
                },
            },
            with_metrics=True,
        )

    assert not raw_path.exists()
    assert not output_path.exists()
