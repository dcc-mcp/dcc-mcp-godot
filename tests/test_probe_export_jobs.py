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


def test_all_probe_calls_are_present_in_loaded_skill_schemas():
    import ast
    from pathlib import Path

    import probe_export_jobs
    import yaml

    root = Path(__file__).parents[1]
    declared = {"load_skill"}  # Official Core bootstrap action.
    for skill in probe_export_jobs.REQUIRED_SKILLS:
        schema = yaml.safe_load(
            (root / "src/dcc_mcp_godot/skills" / skill / "tools.yaml").read_text()
        )
        declared.update(tool["name"] for tool in schema["tools"])
    source = ast.parse(Path(probe_export_jobs.__file__).read_text())
    called = {
        node.args[0].value
        for node in ast.walk(source)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "call"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert called <= declared, called - declared
    assert {
        "start_export_job",
        "get_export_job",
        "cancel_export_job",
        "execute_editor_script",
    } <= called


def test_fixture_preset_has_native_required_empty_fields():
    import ast
    import configparser
    from pathlib import Path

    import probe_export_jobs

    source = ast.parse(Path(probe_export_jobs.__file__).read_text())
    literals = [
        node.value
        for node in ast.walk(source)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("[preset.0]\n")
    ]
    assert len(literals) == 1
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(literals[0])
    assert {
        "name",
        "platform",
        "runnable",
        "export_filter",
        "include_filter",
        "exclude_filter",
        "export_path",
        "script_export_mode",
    } <= set(parser["preset.0"])
    assert parser["preset.0"]["include_filter"] == '""'
    assert parser["preset.0"]["export_path"] == '""'


def test_fixture_cleans_native_memory_before_freezing_export_baseline():
    import ast
    from pathlib import Path

    import probe_export_jobs

    tree = ast.parse(Path(probe_export_jobs.__file__).read_text())
    scripts = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("@tool\n")
    ]
    assert len(scripts) == 1
    script = scripts[0]
    assert 'for key in ["autoload/DccMcpRuntimePeer", "editor_plugins/enabled"]:' in script
    assert "ProjectSettings.set_setting(key, null)" in script
    assert "ProjectSettings.save()" in script
    assert "if before != after:" in script
    assert "FileAccess.WRITE" not in script
