import base64
import struct
import zlib

import pytest

from dcc_mcp_godot import capability_dispatch
from dcc_mcp_godot.screenshot import finalize_screenshot


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
