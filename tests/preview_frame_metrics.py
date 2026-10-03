"""Frame metrics and the two-tier scene-preview acceptance judgement.

A scene preview is only accepted when its dimensions, size, colour spread and
rendering method are all reported and all in range, and when its pixels match a
reference frame to the tolerance of the tier that applies on this platform.

Two tiers exist because a tolerance that is provable on one platform is not
transferable to another:

``A``
    Measured on a windowed Windows host: ten consecutive renders of one scene
    were byte-identical to the archived windowed baseline, so the criteria
    demand exactly that -- ``mean_delta`` 0.0, ``different_pixels`` 0 and a
    matching sha256.
``B``
    For a platform with no measured noise floor yet (Linux under Xvfb, macOS):
    ``mean_delta <= 1.0/255`` and ``max_delta <= 32``. Wide enough to absorb a
    software rasteriser, tight enough to reject a tool that returned a different
    image. The noise floor has to be re-measured on every platform, which is
    what ``tests/probe_windowed_preview.py`` writes into its artifact.

Nothing here sniffs the platform: the caller picks the tier, and a tier B run
records its own noise floor so the tier can later be tightened with evidence.

Standard library only. The unit suite and the CI lane both run on Python 3.9
with no wheels available, so the PNG is decoded with ``zlib`` and the pixel math
uses ``struct``, ``bytes`` slicing and C-level ``map``/``sum`` instead of numpy.
The adapter writes filter-0 rows (``screenshot._encode_png``), which is the fast
path of the decoder below; the other four filters are implemented for
completeness because the reference frame may come from any encoder.
"""

from __future__ import annotations

import hashlib
import operator
import struct
import zlib
from dataclasses import dataclass
from itertools import chain, repeat
from pathlib import Path
from typing import Any

TIER_A = "A"
TIER_B = "B"

# Tier A: measured, not inferred. Ten consecutive renders were byte-identical.
TIER_A_MEAN_DELTA = 0.0
TIER_A_DIFFERENT_PIXELS = 0
# Tier B: unmeasured until a platform runs the probe and records its floor.
TIER_B_MEAN_DELTA = 1.0
TIER_B_MAX_DELTA = 32

# A real frame of the reference scene measures 9317 unique colours on Windows/
# gl_compatibility; a blank trap frame collapses to 1.
MIN_UNIQUE_COLORS = 1000

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_COLOR_TYPE_RGB = 2
_COLOR_TYPE_RGBA = 6


@dataclass(frozen=True)
class Frame:
    """One decoded PNG: the packed RGBA8 pixels plus what the file reports."""

    path: str
    width: int
    height: int
    png_bytes: int
    sha256: str
    pixels: bytes


@dataclass(frozen=True)
class FrameMetrics:
    """Measurements taken from one frame, independent of any baseline."""

    path: str
    width: int
    height: int
    bytes: int
    sha256: str
    unique_colors: int
    mean_luma: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "width": self.width,
            "height": self.height,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "unique_colors": self.unique_colors,
            "mean_luma": self.mean_luma,
        }


@dataclass(frozen=True)
class FrameDelta:
    """Comparison of one candidate frame against a reference frame."""

    sha256_match: bool
    mean_delta: float
    max_delta: int
    different_pixels: int
    total_pixels: int
    different_pixel_pct: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "sha256_match": self.sha256_match,
            "mean_delta": self.mean_delta,
            "max_delta": self.max_delta,
            "different_pixels": self.different_pixels,
            "total_pixels": self.total_pixels,
            "different_pixel_pct": self.different_pixel_pct,
        }


def _chunks(data: bytes):
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG file: missing signature")
    offset = 8
    while offset + 8 <= len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        kind = data[offset + 4 : offset + 8]
        body = data[offset + 8 : offset + 8 + length]
        if len(body) != length:
            raise ValueError(f"truncated PNG chunk {kind!r}")
        yield kind, body
        offset += 12 + length


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    distance_left = abs(estimate - left)
    distance_up = abs(estimate - up)
    distance_up_left = abs(estimate - up_left)
    if distance_left <= distance_up and distance_left <= distance_up_left:
        return left
    if distance_up <= distance_up_left:
        return up
    return up_left


def _unfilter_sub(line: bytes, previous: bytes, stride: int, bpp: int) -> bytes:
    del previous, stride
    out = bytearray(len(line))
    out[:bpp] = line[:bpp]
    for index in range(bpp, len(line)):
        out[index] = (line[index] + out[index - bpp]) & 0xFF
    return bytes(out)


def _unfilter_up(line: bytes, previous: bytes, stride: int, bpp: int) -> bytes:
    del stride, bpp
    return bytes((line[i] + previous[i]) & 0xFF for i in range(len(line)))


def _unfilter_average(line: bytes, previous: bytes, stride: int, bpp: int) -> bytes:
    del stride
    out = bytearray(len(line))
    for index in range(len(line)):
        left = out[index - bpp] if index >= bpp else 0
        out[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
    return bytes(out)


def _unfilter_paeth(line: bytes, previous: bytes, stride: int, bpp: int) -> bytes:
    del stride
    out = bytearray(len(line))
    for index in range(len(line)):
        left = out[index - bpp] if index >= bpp else 0
        up_left = previous[index - bpp] if index >= bpp else 0
        out[index] = (line[index] + _paeth(left, previous[index], up_left)) & 0xFF
    return bytes(out)


def _unfilter(raw: bytes, width: int, height: int, channels: int) -> bytes:
    """Undo the per-row PNG filters, returning packed rows without filter bytes."""
    stride = width * channels
    if len(raw) < height * (stride + 1):
        raise ValueError("PNG data is shorter than its declared scanlines")
    handlers = (
        None,
        _unfilter_sub,
        _unfilter_up,
        _unfilter_average,
        _unfilter_paeth,
    )
    out = bytearray()
    previous = bytes(stride)
    position = 0
    for _ in range(height):
        filter_type = raw[position]
        position += 1
        line = raw[position : position + stride]
        position += stride
        if filter_type == 0:
            current = line
        elif filter_type < len(handlers):
            current = handlers[filter_type](line, previous, stride, channels)
        else:
            raise ValueError(f"unknown PNG filter type {filter_type}")
        out += current
        previous = current
    return bytes(out)


def _as_rgba(pixels: bytes, channels: int) -> bytes:
    """Expand RGB rows to RGBA so every metric sees the same four channels."""
    if channels == 4:
        return pixels
    return bytes(chain.from_iterable(zip(pixels[0::3], pixels[1::3], pixels[2::3], repeat(255))))


def decode_rgba(data: bytes) -> tuple[int, int, bytes]:
    """Decode an 8-bit RGB/RGBA PNG into ``(width, height, packed RGBA8 rows)``."""
    width = 0
    height = 0
    channels = 0
    blocks: list[bytes] = []
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            width, height, depth, color_type, _compression, _filter, interlace = struct.unpack(
                ">IIBBBBB", body
            )
            if depth != 8:
                raise ValueError(f"unsupported PNG bit depth {depth}; only 8-bit is handled")
            if interlace != 0:
                raise ValueError("interlaced PNG files are not supported")
            if color_type == _COLOR_TYPE_RGBA:
                channels = 4
            elif color_type == _COLOR_TYPE_RGB:
                channels = 3
            else:
                raise ValueError(f"unsupported PNG colour type {color_type}; expected RGB or RGBA")
        elif kind == b"IDAT":
            blocks.append(body)
        elif kind == b"IEND":
            break
    if not channels:
        raise ValueError("PNG has no IHDR chunk")
    return (
        width,
        height,
        _as_rgba(_unfilter(zlib.decompress(b"".join(blocks)), width, height, channels), channels),
    )


def load(path: Path | str) -> Frame:
    """Decode one PNG from disk."""
    resolved = Path(path)
    data = resolved.read_bytes()
    width, height, pixels = decode_rgba(data)
    return Frame(
        path=str(resolved),
        width=width,
        height=height,
        png_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        pixels=pixels,
    )


def _unique_colors(pixels: bytes) -> int:
    count = len(pixels) // 4
    if not count:
        return 0
    return len(set(struct.unpack(">%dI" % count, pixels)))


def measure(frame: Frame) -> FrameMetrics:
    """Measure one decoded frame. ``bytes`` is the PNG size, as the tool reports."""
    pixels = frame.pixels
    total = len(pixels) // 4
    # Luma over the RGB channels only: the tool renders an opaque frame, so a
    # constant alpha of 255 would otherwise drag the mean toward 255.
    luma = (
        0.2126 * sum(pixels[0::4]) + 0.7152 * sum(pixels[1::4]) + 0.0722 * sum(pixels[2::4])
    ) / total
    return FrameMetrics(
        path=frame.path,
        width=frame.width,
        height=frame.height,
        bytes=frame.png_bytes,
        sha256=frame.sha256,
        unique_colors=_unique_colors(pixels),
        mean_luma=round(luma, 4),
    )


def compare(reference: Frame, candidate: Frame) -> FrameDelta:
    """Diff a candidate frame against the reference at 0-255 channel scale.

    A size mismatch means the tool returned a different image entirely, so it is
    reported as a total delta rather than raised: the caller must see it as a
    hard acceptance failure, not as an exception it might swallow.
    """
    if reference.width != candidate.width or reference.height != candidate.height:
        total = max(reference.width * reference.height, candidate.width * candidate.height)
        return FrameDelta(
            sha256_match=False,
            mean_delta=255.0,
            max_delta=255,
            different_pixels=total,
            total_pixels=total,
            different_pixel_pct=100.0,
        )
    total_pixels = reference.width * reference.height
    channel_total = total_pixels * 4
    delta_sum = 0
    delta_max = 0
    for channel in range(4):
        plane = list(
            map(abs, map(operator.sub, reference.pixels[channel::4], candidate.pixels[channel::4]))
        )
        delta_sum += sum(plane)
        delta_max = max(delta_max, max(plane))
    # Per-pixel "any channel moved", which a per-channel mean would hide: a
    # red/green swap averages to a small delta while being the wrong image.
    xor = int.from_bytes(reference.pixels, "big") ^ int.from_bytes(candidate.pixels, "big")
    words = struct.unpack(">%dI" % total_pixels, xor.to_bytes(channel_total, "big"))
    different = total_pixels - words.count(0)
    return FrameDelta(
        sha256_match=reference.sha256 == candidate.sha256,
        mean_delta=round(delta_sum / channel_total, 6),
        max_delta=delta_max,
        different_pixels=different,
        total_pixels=total_pixels,
        different_pixel_pct=round(100.0 * different / total_pixels, 4),
    )


def judge(
    metrics: FrameMetrics,
    delta: FrameDelta | None,
    *,
    tier: str,
    expected_width: int,
    expected_height: int,
    expected_rendering_method: str,
    observed_rendering_method: str,
) -> dict[str, Any]:
    """Apply the acceptance criteria, returning the verdict and every reason."""
    failures: list[str] = []

    if metrics.width != expected_width or metrics.height != expected_height:
        failures.append(
            f"dimensions {metrics.width}x{metrics.height} != requested "
            f"{expected_width}x{expected_height}"
        )
    if metrics.bytes <= 0:
        failures.append(f"bytes={metrics.bytes} (must be > 0)")
    if metrics.unique_colors <= MIN_UNIQUE_COLORS:
        failures.append(
            f"unique_colors={metrics.unique_colors} (must be > {MIN_UNIQUE_COLORS}); "
            "a blank or trap frame collapses to a handful of colors"
        )
    if observed_rendering_method != expected_rendering_method:
        failures.append(
            f"rendering_method '{observed_rendering_method}' != baseline "
            f"'{expected_rendering_method}': the frame took a different rendering path"
        )

    if delta is None:
        failures.append("no baseline delta was computed")
    elif tier == TIER_A:
        if delta.mean_delta != TIER_A_MEAN_DELTA:
            failures.append(f"tier A mean_delta={delta.mean_delta} (must be exactly 0.000)")
        if delta.different_pixels != TIER_A_DIFFERENT_PIXELS:
            failures.append(f"tier A different_pixels={delta.different_pixels} (must be exactly 0)")
        if not delta.sha256_match:
            failures.append("tier A sha256 does not match the baseline (recommended check)")
    elif tier == TIER_B:
        if delta.mean_delta > TIER_B_MEAN_DELTA:
            failures.append(f"tier B mean_delta={delta.mean_delta} (must be <= 1.0/255)")
        if delta.max_delta > TIER_B_MAX_DELTA:
            failures.append(f"tier B max_delta={delta.max_delta} (must be <= 32)")
    else:
        failures.append(f"unknown tier {tier!r}")

    return {
        "tier": tier,
        "passed": not failures,
        "failures": failures,
        "metrics": metrics.as_dict(),
        "delta": delta.as_dict() if delta else None,
    }
