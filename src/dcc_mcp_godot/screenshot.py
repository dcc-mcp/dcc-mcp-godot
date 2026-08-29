"""Finalize immutable Godot pixel snapshots outside the Godot process thread."""

from __future__ import annotations

import base64
import binascii
import os
import struct
import tempfile
import zlib
from pathlib import Path
from typing import Any

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_FORMATS = {
    "rgb8": (3, 2),
    "rgba8": (4, 6),
}


def finalize_screenshot(result: dict[str, Any], *, include_base64: bool = False) -> dict[str, Any]:
    """Encode a host-produced raw pixel snapshot and remove its staging file."""
    snapshot = result.pop("__raw_snapshot__", None)
    if snapshot is None:
        return result
    if not isinstance(snapshot, dict):
        raise ValueError("Godot screenshot snapshot metadata is invalid")

    raw_path = Path(_required_string(snapshot, "path"))
    try:
        output_path = Path(_required_string(snapshot, "output_path"))
        if (
            output_path.suffix.lower() != ".png"
            or raw_path.parent.resolve() != output_path.parent.resolve()
            or not raw_path.name.startswith(f"{output_path.name}.dcc-mcp-")
            or raw_path.suffix.lower() != ".raw"
        ):
            raise ValueError("Godot screenshot snapshot paths are invalid")
        width = _required_positive_int(result, "width")
        height = _required_positive_int(result, "height")
        format_name = _required_string(snapshot, "format").lower()
        if format_name not in _FORMATS:
            raise ValueError(f"Unsupported Godot screenshot format: {format_name}")

        channels, color_type = _FORMATS[format_name]
        expected_size = width * height * channels
        declared_size = _required_positive_int(snapshot, "byte_length")
        if declared_size != expected_size:
            raise ValueError("Godot screenshot snapshot byte length does not match its dimensions")
        pixels = raw_path.read_bytes()
        if len(pixels) != expected_size:
            raise ValueError("Godot screenshot snapshot is incomplete")
        png = _encode_png(
            pixels, width=width, height=height, channels=channels, color_type=color_type
        )
        _atomic_write(output_path, png)
    finally:
        raw_path.unlink(missing_ok=True)

    if include_base64:
        result["png_base64"] = base64.b64encode(png).decode("ascii")
    return result


def finalize_screenshot_batch(result: dict[str, Any]) -> dict[str, Any]:
    """Finalize a batch of immutable snapshots captured by the Godot host.

    Each PNG is encoded and published by the adapter thread.  A malformed
    snapshot fails the whole batch closed while all staging files are removed.
    """
    snapshots = result.pop("__raw_snapshots__", None)
    if snapshots is None:
        return result
    if not isinstance(snapshots, list):
        raise ValueError("Godot screenshot snapshot metadata is invalid")
    remaining = list(snapshots)
    try:
        for snapshot in snapshots:
            single = dict(result)
            if isinstance(snapshot, dict):
                single.update(
                    {key: snapshot[key] for key in ("width", "height") if key in snapshot}
                )
            single["__raw_snapshot__"] = snapshot
            finalize_screenshot(single)
            remaining.pop(0)
    finally:
        for snapshot in remaining:
            if isinstance(snapshot, dict):
                raw_path = snapshot.get("path")
                if isinstance(raw_path, str) and raw_path:
                    Path(raw_path).unlink(missing_ok=True)
    return result


def _encode_png(
    pixels: bytes,
    *,
    width: int,
    height: int,
    channels: int,
    color_type: int,
) -> bytes:
    stride = width * channels
    scanlines = b"".join(
        b"\x00" + pixels[offset : offset + stride] for offset in range(0, len(pixels), stride)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return b"".join(
        (
            _PNG_SIGNATURE,
            _png_chunk(b"IHDR", header),
            _png_chunk(b"IDAT", zlib.compress(scanlines)),
            _png_chunk(b"IEND", b""),
        )
    )


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = binascii.crc32(kind)
    checksum = binascii.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(data)
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"Godot screenshot snapshot {key} is invalid")
    return item


def _required_positive_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool) or item <= 0:
        raise ValueError(f"Godot screenshot snapshot {key} is invalid")
    return item


__all__ = ["finalize_screenshot", "finalize_screenshot_batch"]
