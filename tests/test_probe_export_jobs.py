"""Offline artifact guards; not a substitute for native/browser execution."""

import hashlib
import struct

import pytest
from probe_export_jobs import inspect_clean_pck


def fixture(path, version=3, name="res://project.binary", config=b"ECFG-clean", flags=0):
    raw = bytearray(512 + len(config))
    raw[:32] = struct.pack("<4sIIIIIQ", b"GDPC", version, 4, 6, 3, flags, 0)
    if version == 3:
        struct.pack_into("<Q", raw, 32, 128)
        offset = 128
    else:
        offset = 96
    name = name.encode()
    entry = (
        struct.pack("<II", 1, len(name))
        + name
        + struct.pack("<QQ", 512, len(config))
        + hashlib.md5(config).digest()
        + struct.pack("<I", 0)
    )
    raw[offset : offset + len(entry)] = entry
    raw[512:] = config
    path.write_bytes(raw)
    return path


@pytest.mark.parametrize("version", [2, 3])
def test_clean_pck_formats(tmp_path, version):
    result = inspect_clean_pck(fixture(tmp_path / "test.pck", version=version))
    assert result["entries"] == ["res://project.binary"]


@pytest.mark.parametrize(
    "params",
    [
        {"config": b"autoload/DccMcpRuntimePeer"},
        {"name": "res://addons/control.gd"},
        {"name": "res://export_probe.gd"},
        {"name": "res://web-complete/index.pck"},
        {"flags": 1},
    ],
)
def test_control_pollution_rejected(tmp_path, params):
    with pytest.raises(ValueError):
        inspect_clean_pck(fixture(tmp_path / "test.pck", **params))


def test_truncated_pck_rejected(tmp_path):
    path = fixture(tmp_path / "test.pck")
    path.write_bytes(path.read_bytes()[:150])
    with pytest.raises(ValueError):
        inspect_clean_pck(path)
