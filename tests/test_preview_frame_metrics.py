"""Unit coverage for the scene-preview frame metrics and acceptance judgement.

The windowed CI lane is the only place these criteria run against a real frame,
and it needs a Godot binary the unit matrix does not have. These tests pin the
measurement and the verdict on synthetic frames instead, so a regression in the
comparator or in the tier thresholds shows up on every platform and every
supported Python, not only where a host happens to be installed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from preview_frame_metrics import (
    MIN_UNIQUE_COLORS,
    TIER_A,
    TIER_B,
    TIER_B_MAX_DELTA,
    TIER_B_MEAN_DELTA,
    Frame,
    compare,
    decode_rgba,
    judge,
    load,
    measure,
)

from dcc_mcp_godot.screenshot import _encode_png

WIDTH = 48
HEIGHT = 32
CHANNELS = 4
METHOD = "gl_compatibility"


def _frame(pixels: bytes, *, width: int = WIDTH, height: int = HEIGHT) -> Frame:
    """Build an in-memory frame the way the adapter encodes one."""
    png = _encode_png(pixels, width=width, height=height, channels=CHANNELS, color_type=6)
    return Frame(
        path="in-memory",
        width=width,
        height=height,
        png_bytes=len(png),
        sha256=hashlib.sha256(png).hexdigest(),
        pixels=pixels,
    )


def _gradient() -> bytes:
    """A frame with a distinct colour per pixel, and more pixels than the gate.

    The unique-colour criterion is part of what is under test, so the synthetic
    frames have to clear it: a 48x32 frame holds more than 1000 distinct pixels,
    which a blank or trap frame never can.
    """
    count = WIDTH * HEIGHT
    assert count > MIN_UNIQUE_COLORS
    return bytes(
        bytearray(
            value
            for index in range(count)
            for value in (index % 256, (index // 256) % 256, (index // 65536) % 256, 255)
        )
    )


def _solid(value: int) -> bytes:
    return bytes(bytearray([value, value, value, 255]) * (WIDTH * HEIGHT))


def _write(pixels: bytes, directory: Path, name: str = "frame.png") -> Path:
    path = directory / name
    path.write_bytes(
        _encode_png(pixels, width=WIDTH, height=HEIGHT, channels=CHANNELS, color_type=6)
    )
    return path


def _judge(frame: Frame, delta, *, tier: str = TIER_B, observed: str = METHOD, **kwargs):
    return judge(
        measure(frame),
        delta,
        tier=tier,
        expected_width=kwargs.get("width", WIDTH),
        expected_height=kwargs.get("height", HEIGHT),
        expected_rendering_method=METHOD,
        observed_rendering_method=observed,
    )


def test_decode_round_trips_the_adapter_encoder(tmp_path: Path) -> None:
    pixels = _gradient()
    path = _write(pixels, tmp_path)
    width, height, decoded = decode_rgba(path.read_bytes())
    assert (width, height) == (WIDTH, HEIGHT)
    assert decoded == pixels


def test_load_reports_the_png_size_and_digest(tmp_path: Path) -> None:
    path = _write(_gradient(), tmp_path)
    frame = load(path)
    data = path.read_bytes()
    assert frame.png_bytes == len(data)
    assert frame.sha256 == hashlib.sha256(data).hexdigest()


def test_measure_counts_every_distinct_pixel(tmp_path: Path) -> None:
    metrics = measure(load(_write(_gradient(), tmp_path)))
    assert metrics.unique_colors == WIDTH * HEIGHT
    assert metrics.width == WIDTH
    assert metrics.height == HEIGHT
    assert metrics.bytes > 0


def test_measure_ignores_alpha_in_mean_luma(tmp_path: Path) -> None:
    # Alpha is a constant 255 for an opaque render, so folding it in would drag
    # every luma value toward 255 and make the metric insensitive to the frame.
    metrics = measure(load(_write(_solid(0), tmp_path)))
    assert metrics.mean_luma == pytest.approx(0.0)
    assert metrics.unique_colors == 1


def test_identical_frames_compare_to_zero() -> None:
    frame = _frame(_gradient())
    delta = compare(frame, frame)
    assert delta.sha256_match is True
    assert delta.mean_delta == 0.0
    assert delta.max_delta == 0
    assert delta.different_pixels == 0
    assert delta.different_pixel_pct == 0.0


def test_a_single_moved_channel_counts_as_a_different_pixel() -> None:
    # A red/green swap averages to a small delta while being the wrong image, so
    # the pixel count must look at channels individually.
    base = _frame(_solid(10))
    pixels = bytearray(base.pixels)
    pixels[0] = 11
    other = _frame(bytes(pixels))
    delta = compare(base, other)
    assert delta.different_pixels == 1
    assert delta.max_delta == 1
    # mean_delta is reported rounded to six decimals.
    assert delta.mean_delta == pytest.approx(1 / (WIDTH * HEIGHT * CHANNELS), abs=1e-6)


def test_mean_and_max_delta_are_computed_over_every_channel() -> None:
    base = _frame(_solid(0))
    other = _frame(_solid(64))
    delta = compare(base, other)
    assert delta.max_delta == 64
    assert delta.mean_delta == pytest.approx(48.0)  # alpha stays at 255


def test_a_size_mismatch_reports_a_total_delta_instead_of_raising() -> None:
    delta = compare(_frame(_gradient(), width=4, height=4), _frame(_gradient()))
    assert delta.mean_delta == 255.0
    assert delta.different_pixel_pct == 100.0


def test_judge_accepts_a_byte_identical_frame_at_tier_a() -> None:
    frame = _frame(_gradient())
    verdict = _judge(frame, compare(frame, frame), tier=TIER_A)
    assert verdict["passed"], verdict["failures"]


def test_judge_rejects_one_changed_pixel_at_tier_a() -> None:
    base = _frame(_gradient())
    pixels = bytearray(base.pixels)
    pixels[4] = 0
    other = _frame(bytes(pixels))
    verdict = _judge(other, compare(base, other), tier=TIER_A)
    assert not verdict["passed"]
    assert any("different_pixels" in item for item in verdict["failures"])


def test_judge_accepts_a_small_delta_at_tier_b() -> None:
    base = _frame(_gradient())
    pixels = bytearray(base.pixels)
    pixels[0] = (pixels[0] + TIER_B_MAX_DELTA) % 256
    other = _frame(bytes(pixels))
    delta = compare(base, other)
    assert delta.max_delta == TIER_B_MAX_DELTA
    assert delta.mean_delta <= TIER_B_MEAN_DELTA
    assert _judge(other, delta, tier=TIER_B)["passed"]


def test_judge_rejects_a_delta_above_the_tier_b_bounds() -> None:
    base = _frame(_gradient())
    other = _frame(bytes(bytearray(value ^ 0x80 for value in base.pixels)))
    delta = compare(base, other)
    assert delta.max_delta > TIER_B_MAX_DELTA
    verdict = _judge(other, delta, tier=TIER_B)
    assert not verdict["passed"]
    assert any("max_delta" in item for item in verdict["failures"])


def test_judge_rejects_a_blank_trap_frame() -> None:
    # The trap this lane exists to catch: a correctly sized, non-empty PNG that
    # carries no scene at all. Only the colour spread separates it from a frame.
    blank = _frame(_solid(0))
    verdict = _judge(blank, compare(blank, blank))
    assert not verdict["passed"]
    assert any("unique_colors" in item for item in verdict["failures"])
    assert any(str(MIN_UNIQUE_COLORS) in item for item in verdict["failures"])


def test_judge_rejects_a_wrong_rendering_method() -> None:
    frame = _frame(_gradient())
    verdict = _judge(frame, compare(frame, frame), observed="forward_plus")
    assert not verdict["passed"]
    assert any("rendering_method" in item for item in verdict["failures"])


def test_judge_rejects_a_missing_rendering_method_echo() -> None:
    # The tool must report the method it used; silence is a silent fallback.
    frame = _frame(_gradient())
    verdict = _judge(frame, compare(frame, frame), observed="")
    assert not verdict["passed"]


def test_judge_rejects_wrong_dimensions() -> None:
    frame = _frame(_gradient())
    verdict = _judge(frame, compare(frame, frame), width=WIDTH + 1)
    assert not verdict["passed"]
    assert any("dimensions" in item for item in verdict["failures"])


def test_judge_fails_closed_without_a_delta() -> None:
    frame = _frame(_gradient())
    verdict = _judge(frame, None)
    assert not verdict["passed"]
    assert any("no baseline delta" in item for item in verdict["failures"])


def test_judge_rejects_an_unknown_tier() -> None:
    frame = _frame(_gradient())
    verdict = _judge(frame, compare(frame, frame), tier="C")
    assert not verdict["passed"]
    assert any("unknown tier" in item for item in verdict["failures"])


def test_tier_b_is_looser_than_tier_a() -> None:
    # The point of the two tiers: B tolerates a software rasteriser's jitter
    # while A, which was measured byte-for-byte, tolerates nothing.
    base = _frame(_gradient())
    pixels = bytearray(base.pixels)
    pixels[0] ^= 0x01
    other = _frame(bytes(pixels))
    delta = compare(base, other)
    assert not _judge(other, delta, tier=TIER_A)["passed"]
    assert _judge(other, delta, tier=TIER_B)["passed"]
