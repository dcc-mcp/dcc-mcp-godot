"""Bounded file preflight for the native, PNG-only UI texture capability.

This module never deserializes Godot resources. Import metadata is read as
bounded text and the built-in CTEX image payload is inspected as PNG/WebP.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import struct
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

MAX_PNG_BYTES = 16 * 1024 * 1024
MAX_IMPORT_BYTES = 32 * 1024 * 1024
MAX_DIMENSION = 4096
MAX_PIXELS = 4 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024


class TextureValidationError(ValueError):
    """The assignment must be rejected without modifying a scene."""


class TextureImportPending(TextureValidationError):
    """The native editor has not produced a current supported import yet."""


def validate_request(params: dict[str, Any]) -> tuple[str, str]:
    if set(params) != {"node_path", "texture_path"}:
        raise TextureValidationError("Exactly node_path and texture_path are required")
    node = params["node_path"]
    if not isinstance(node, str) or not 1 <= len(node) <= 500:
        raise TextureValidationError("node_path must contain 1-500 characters")
    if node != "." and (
        node.startswith(("/", "%"))
        or any(part in {"", ".", ".."} or part.startswith("%") for part in node.split("/"))
        or any(c in node for c in ("\\", ":", "\x00"))
        or any(ord(c) < 32 for c in node)
    ):
        raise TextureValidationError("node_path must be relative to the edited scene")
    texture = params["texture_path"]
    _parts(texture)
    if not texture.endswith(".png"):
        raise TextureValidationError("texture_path must end with lowercase .png")
    return node, texture


def _parts(path: Any) -> list[str]:
    if not isinstance(path, str) or not 7 <= len(path) <= 500 or not path.startswith("res://"):
        raise TextureValidationError("A bounded res:// project path is required")
    parts = path[6:].split("/")
    if (
        any(part in {"", ".", ".."} for part in parts)
        or any(c in path[6:] for c in ("\\", ":", "\x00"))
        or any(ord(c) < 32 for c in path)
    ):
        raise TextureValidationError(
            "Project paths cannot contain traversal or absolute components"
        )
    return parts


def _read_regular(project: Path, resource_path: str, limit: int) -> bytes:
    """Reject symlinks/reparse points and nonregular files before opening them.

    The adapter and editor must share a local project filesystem. Concurrent
    hostile replacement of project directories is outside this editor contract;
    the host rechecks paths, lengths and hashes immediately before loading.
    """
    parts = _parts(resource_path)
    root = project.resolve(strict=True)
    current = root
    for index, part in enumerate(parts):
        current = current / part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise TextureValidationError("Symlinks and reparse points are not supported")
        expected = stat.S_ISREG if index == len(parts) - 1 else stat.S_ISDIR
        if not expected(info.st_mode):
            raise TextureValidationError("Expected project directories and a regular file")
    if root not in current.resolve(strict=True).parents:
        raise TextureValidationError("Resource escapes the project")
    if not 0 < info.st_size <= limit:
        raise TextureValidationError("File is empty or exceeds the documented byte limit")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(current, flags)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            info.st_dev,
            info.st_ino,
        ):
            raise TextureValidationError("File changed during validation")
        data = stream.read(limit + 1)
    if len(data) != info.st_size or len(data) > limit:
        raise TextureValidationError("File changed or exceeded its byte limit")
    return data


def _dimensions(data: bytes, formats: tuple[str, ...]) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(data), formats=formats) as image:
            width, height = image.size
            if not (1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION):
                raise TextureValidationError("Image sides must be between 1 and 4096 pixels")
            if width * height > MAX_PIXELS:
                raise TextureValidationError("Image exceeds the 4194304 pixel limit")
            if getattr(image, "n_frames", 1) != 1:
                raise TextureValidationError("Animated images are not supported")
            image.verify()
        # verify() checks structure; load() also verifies that pixels decode.
        with Image.open(io.BytesIO(data), formats=formats) as image:
            image.load()
        return width, height
    except TextureValidationError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        EOFError,
        Image.DecompressionBombError,
    ) as exc:
        raise TextureValidationError("Image data is corrupt or unsupported") from exc


def _field(data: bytes, section: str, key: str) -> Any:
    """Read only a JSON scalar from one INI key, never a Godot Variant."""
    try:
        text = data.decode("utf-8")
        current = ""
        values = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1]
            elif current == section and re.match(re.escape(key) + r"\s*=", line):
                values.append(json.loads(line.split("=", 1)[1]))
        if len(values) != 1 or not isinstance(values[0], (str, int, bool)):
            raise ValueError("Missing or ambiguous metadata")
        return values[0]
    except (UnicodeError, ValueError) as exc:
        raise TextureValidationError("Unsupported or ambiguous texture import metadata") from exc


def _webp_lossless_dimensions(data: bytes) -> tuple[int, int]:
    # Godot's native lossless packer emits a single VP8L RIFF chunk. Accept
    # only that bounded form; encoding=WEBP alone also admits lossy VP8.
    if (
        len(data) < 25
        or data[:4] != b"RIFF"
        or data[8:16] != b"WEBPVP8L"
        or struct.unpack_from("<I", data, 4)[0] != len(data) - 8
        or data[20] != 0x2F
    ):
        raise TextureValidationError("Imported WebP must contain a single lossless VP8L image")
    chunk_size = struct.unpack_from("<I", data, 16)[0]
    bits = struct.unpack_from("<I", data, 21)[0]
    if chunk_size < 5 or 20 + chunk_size + (chunk_size & 1) != len(data) or bits >> 29:
        raise TextureValidationError("Invalid lossless WebP header")
    return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1


def _validate_ctex(data: bytes, dimensions: tuple[int, int]) -> None:
    if len(data) < 56 or data[:4] != b"GST2":
        raise TextureValidationError("Invalid imported texture header")
    version, width, height = struct.unpack_from("<III", data, 4)
    encoding, pixel_width, pixel_height, mipmaps, pixel_format = struct.unpack_from(
        "<IHHII", data, 36
    )
    payload_length = struct.unpack_from("<I", data, 52)[0]
    if (
        version != 1
        or (width, height) != dimensions
        or (pixel_width, pixel_height) != dimensions
        or encoding not in {1, 2}
        or mipmaps != 0
        or pixel_format > 5
        or payload_length != len(data) - 56
    ):
        raise TextureValidationError(
            "Only bounded lossless 2D imports without mipmaps are supported"
        )
    if encoding == 2 and _webp_lossless_dimensions(data[56:]) != dimensions:
        raise TextureValidationError("Lossless WebP dimensions do not match the PNG")
    formats = ("PNG",) if encoding == 1 else ("WEBP",)
    if _dimensions(data[56:], formats) != dimensions:
        raise TextureValidationError("Imported image dimensions do not match the PNG")


def prepare_texture(project_path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Return internal native attestation, or fail before native scene mutation."""
    node, path = validate_request(params)
    project = Path(project_path)
    if not project.is_absolute() or not project.is_dir():
        raise TextureValidationError(
            "The editor project must be accessible on the adapter filesystem"
        )
    try:
        png = _read_regular(project, path, MAX_PNG_BYTES)
    except FileNotFoundError as exc:
        raise TextureValidationError("PNG file does not exist") from exc
    dimensions = _dimensions(png, ("PNG",))
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise TextureValidationError("Expected PNG data")
    import_path = path + ".import"
    try:
        metadata = _read_regular(project, import_path, MAX_METADATA_BYTES)
    except FileNotFoundError as exc:
        raise TextureImportPending("PNG import is missing; import in the editor and retry") from exc
    if (
        _field(metadata, "remap", "importer") != "texture"
        or _field(metadata, "remap", "type") != "CompressedTexture2D"
    ):
        raise TextureValidationError("Only the built-in 2D texture importer is supported")
    if _field(metadata, "params", "compress/mode") != 0:
        raise TextureValidationError("Use Lossless texture import for this UI capability")
    if _field(metadata, "params", "mipmaps/generate") is not False:
        raise TextureValidationError("Disable mipmaps for this UI capability")
    if _field(metadata, "deps", "source_file") != path:
        raise TextureValidationError("Import metadata does not identify the source PNG")
    ctex_path = _field(metadata, "remap", "path")
    expected = (
        "res://.godot/imported/"
        + Path(path).name
        + "-"
        + hashlib.md5(path.encode("utf-8")).hexdigest()
        + ".ctex"
    )
    if ctex_path != expected:
        raise TextureValidationError("Unexpected imported texture path")
    md5_path = ctex_path[:-5] + ".md5"
    try:
        digest_data = _read_regular(project, md5_path, MAX_METADATA_BYTES)
        ctex = _read_regular(project, ctex_path, MAX_IMPORT_BYTES)
    except FileNotFoundError as exc:
        raise TextureImportPending(
            "Imported texture is missing; finish editor import and retry"
        ) from exc
    if _field(digest_data, "", "source_md5") != hashlib.md5(png).hexdigest():
        raise TextureImportPending("PNG changed; refresh its editor import and retry")
    if _field(digest_data, "", "dest_md5") != hashlib.md5(ctex).hexdigest():
        raise TextureImportPending("Imported texture changed; refresh its editor import and retry")
    _validate_ctex(ctex, dimensions)
    files = []
    for name, data in (
        (path, png),
        (import_path, metadata),
        (md5_path, digest_data),
        (ctex_path, ctex),
    ):
        files.append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return {
        "node_path": node,
        "texture_path": path,
        "_validated_texture": {
            "project_path": project.resolve().as_posix(),
            "width": dimensions[0],
            "height": dimensions[1],
            "source_sha256": files[0]["sha256"],
            "imported_path": ctex_path,
            "files": files,
        },
    }
