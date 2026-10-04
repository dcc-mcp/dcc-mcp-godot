"""File/schema/dispatch contracts; native editor behavior has a separate runner."""

from __future__ import annotations

import hashlib
import io
import os
import struct
from pathlib import Path

import jsonschema
import pytest
import yaml
from dcc_mcp_core.skill import skill_success
from PIL import Image

from dcc_mcp_godot import capability_dispatch
from dcc_mcp_godot.ui_texture import (
    MAX_PNG_BYTES,
    TextureImportPending,
    TextureValidationError,
    _dimensions,
    _read_regular,
    _validate_ctex,
    prepare_texture,
    validate_request,
)
from tools.generate_capability_skills import UI_TEXTURE_OUTPUT_SCHEMA, _tool_yaml

ROOT = Path(__file__).parents[1]
NATIVE = ROOT / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot/ui_texture.gd"
PARAMS = {"node_path": "Icon", "texture_path": "res://assets/icon.png"}


def png_bytes(size=(8, 8), color=(12, 34, 56, 255)):
    output = io.BytesIO()
    Image.new("RGBA", size, color).save(output, format="PNG")
    return output.getvalue()


def ctex_bytes(png, dimensions=(8, 8)):
    # Godot 4 CTEX version 1, lossless embedded PNG, no mipmaps.
    width, height = dimensions
    return (
        b"GST2"
        + struct.pack("<8I", 1, width, height, 0, 0, 0, 0, 0)
        + struct.pack("<IHHIII", 1, width, height, 0, 5, len(png))
        + png
    )


@pytest.fixture
def project(tmp_path):
    (tmp_path / "assets").mkdir()
    imported = tmp_path / ".godot/imported"
    imported.mkdir(parents=True)
    png = png_bytes()
    (tmp_path / "assets/icon.png").write_bytes(png)
    stem = "icon.png-" + hashlib.md5(PARAMS["texture_path"].encode()).hexdigest()
    import_path = "res://.godot/imported/" + stem + ".ctex"
    (imported / (stem + ".ctex")).write_bytes(ctex_bytes(png))
    (imported / (stem + ".md5")).write_text(
        'source_md5="'
        + hashlib.md5(png).hexdigest()
        + '"\n'
        + 'dest_md5="'
        + hashlib.md5(ctex_bytes(png)).hexdigest()
        + '"\n'
    )
    (tmp_path / "assets/icon.png.import").write_text(
        '[remap]\nimporter="texture"\ntype="CompressedTexture2D"\npath="'
        + import_path
        + '"\n[deps]\nsource_file="res://assets/icon.png"\n[params]\n'
        "compress/mode=0\nmipmaps/generate=false\n"
    )
    return tmp_path


def test_native_import_preflight_is_bound_to_exact_bytes(project):
    prepared = prepare_texture(str(project), PARAMS)
    proof = prepared["_validated_texture"]
    assert prepared["node_path"] == "Icon"
    assert proof["width"] == proof["height"] == 8
    assert len(proof["files"]) == 4
    for entry in proof["files"]:
        data = (project / entry["path"][6:]).read_bytes()
        assert entry["size"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    assert prepare_texture(str(project), PARAMS) == prepared


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/tmp/icon.png",
        "user://icon.png",
        "http://x/icon.png",
        "res://../icon.png",
        "res://assets/../icon.png",
        "res://assets//icon.png",
        "res://assets/./icon.png",
        "res://C:/icon.png",
        "res://assets\\icon.png",
        "res://assets/icon.PNG",
        "res://assets/icon.tres",
        "res://assets/\x00icon.png",
        "res://" + "a" * 500 + ".png",
    ],
)
def test_texture_paths_are_strict(path):
    with pytest.raises(TextureValidationError):
        validate_request({**PARAMS, "texture_path": path})


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/root/Icon",
        "../Icon",
        "A/../Icon",
        "%Icon",
        "A/%Icon",
        "A/%Icon/B",
        "A:icon",
        "A//B",
        "A\\B",
        "A\nB",
        "a" * 501,
    ],
)
def test_node_paths_are_bounded_edited_scene_paths(path):
    with pytest.raises(TextureValidationError):
        validate_request({**PARAMS, "node_path": path})


@pytest.mark.parametrize(
    "extra",
    [
        {"property": "script"},
        {"resource_type": "Script"},
        {"_validated_texture": {}},
        {"refresh": True},
    ],
)
def test_unknown_fields_cannot_select_a_loader_or_property(extra):
    with pytest.raises(TextureValidationError):
        validate_request({**PARAMS, **extra})


@pytest.mark.parametrize(
    "change", ["missing", "directory", "corrupt", "oversize", "symlink", "parent_symlink", "fifo"]
)
def test_bad_source_never_reaches_host_assignment(project, tmp_path, monkeypatch, change):
    path = project / "assets/icon.png"
    path.unlink()
    if change == "directory":
        path.mkdir()
    elif change == "corrupt":
        path.write_bytes(b"not a png")
    elif change == "oversize":
        with path.open("wb") as stream:
            stream.truncate(MAX_PNG_BYTES + 1)
    elif change == "symlink":
        outside = tmp_path / "other.png"
        outside.write_bytes(png_bytes())
        path.symlink_to(outside)
    elif change == "parent_symlink":
        (project / "assets/icon.png.import").unlink()
        (project / "assets").rmdir()
        other = tmp_path / "other"
        other.mkdir()
        (other / "icon.png").write_bytes(png_bytes())
        (project / "assets").symlink_to(other, target_is_directory=True)
    elif change == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO not supported")
        os.mkfifo(path)
    calls = []

    def host(method, _params):
        calls.append(method)
        return {"project_path": str(project)}

    monkeypatch.setattr(capability_dispatch, "call_host", host)
    result = capability_dispatch._dispatch_ui_texture(PARAMS)
    assert result["assigned"] is False
    assert result["status"] == "rejected"
    assert calls == ["capability.get_project_info"]


@pytest.mark.parametrize("dimensions", [(4097, 1), (1, 4097), (2049, 2049)])
def test_dimensions_reject_before_pixel_allocation(monkeypatch, dimensions):
    class HeaderOnly:
        size = dimensions

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def verify(self):
            pytest.fail("Oversized image must be rejected before verify/decode")

    monkeypatch.setattr(Image, "open", lambda *_args, **_kwargs: HeaderOnly())
    with pytest.raises(TextureValidationError):
        _dimensions(b"header", ("PNG",))


def test_truncated_png_and_bad_crc_rejected():
    png = png_bytes()
    for broken in (png[:40], png[:45] + bytes([png[45] ^ 1]) + png[46:]):
        with pytest.raises(TextureValidationError):
            _dimensions(broken, ("PNG",))


@pytest.mark.parametrize("what", ["metadata", "ctex", "digest", "source_changed"])
def test_incomplete_or_stale_import_is_pending(project, what):
    if what == "metadata":
        (project / "assets/icon.png.import").unlink()
    elif what == "source_changed":
        (project / "assets/icon.png").write_bytes(png_bytes(color=(200, 0, 0, 255)))
    else:
        suffix = ".ctex" if what == "ctex" else ".md5"
        next((project / ".godot/imported").glob("*" + suffix)).unlink()
    with pytest.raises(TextureImportPending):
        prepare_texture(str(project), PARAMS)


@pytest.mark.parametrize(
    "old,new",
    [
        ('importer="texture"', 'importer="custom"'),
        ('type="CompressedTexture2D"', 'type="Script"'),
        ("compress/mode=0", "compress/mode=2"),
        ("mipmaps/generate=false", "mipmaps/generate=true"),
        ('source_file="res://assets/icon.png"', 'source_file="res://other.png"'),
        ('importer="texture"', 'importer="texture"\nimporter="texture"'),
    ],
)
def test_unsupported_or_ambiguous_import_is_rejected(project, old, new):
    path = project / "assets/icon.png.import"
    path.write_text(path.read_text().replace(old, new))
    with pytest.raises(TextureValidationError):
        prepare_texture(str(project), PARAMS)


def test_imported_file_symlink_and_resource_redirect_rejected(project):
    path = next((project / ".godot/imported").glob("*.ctex"))
    data = path.read_bytes()
    path.unlink()
    target = project / "other.ctex"
    target.write_bytes(data)
    path.symlink_to(target)
    with pytest.raises(TextureValidationError, match="Symlinks"):
        prepare_texture(str(project), PARAMS)
    metadata = project / "assets/icon.png.import"
    metadata.write_text(
        metadata.read_text().replace('path="res://.godot/imported/', 'path="res://../')
    )
    with pytest.raises(TextureValidationError, match="Unexpected"):
        prepare_texture(str(project), PARAMS)


@pytest.mark.parametrize(
    "offset,value", [(4, 2), (8, 99999), (36, 3), (44, 99999), (48, 99999), (52, 999999)]
)
def test_ctex_header_bounds_before_decode(offset, value):
    data = bytearray(ctex_bytes(png_bytes()))
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(TextureValidationError):
        _validate_ctex(bytes(data), (8, 8))


def test_ctex_embedded_dimensions_must_match_outer_header():
    with pytest.raises(TextureValidationError):
        _validate_ctex(ctex_bytes(png_bytes(size=(9, 9))), (8, 8))


def test_native_failure_is_not_promoted_to_assigned(project, monkeypatch):
    calls = []

    def host(method, params):
        calls.append((method, params))
        if method.endswith("get_project_info"):
            return {"project_path": str(project)}
        return {"assigned": False, "status": "import_failed", "reason": "native failure"}

    monkeypatch.setattr(capability_dispatch, "call_host", host)
    response = capability_dispatch.dispatch("godot__node__assign_ui_texture", PARAMS)
    assert response["context"]["assigned"] is False
    assert response["context"]["status"] == "import_failed"
    assert calls[-1][0] == "capability.assign_ui_texture"
    assert calls[-1][1]["_validated_texture"]["width"] == 8


def test_generated_schema_is_specific_and_matches_committed_inventory():
    generated = yaml.safe_load("tools:\n" + _tool_yaml("node", "assign_ui_texture", "Assign PNG"))[
        "tools"
    ][0]
    schema = generated["input_schema"]
    jsonschema.validate(PARAMS, schema)
    for invalid in (
        {},
        {**PARAMS, "property": "texture"},
        {**PARAMS, "texture_path": "res://x.tres"},
    ):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)
    inventory = yaml.safe_load(
        (ROOT / "src/dcc_mcp_godot/skills/godot-node/tools.yaml").read_text()
    )
    committed = next(tool for tool in inventory["tools"] if tool["name"] == "assign_ui_texture")
    assert committed["input_schema"] == schema
    assert committed["read_only"] is False
    assert committed["affinity"] == "main"
    assert committed["enforce_thread_affinity"] is True


def test_native_contract_derives_property_and_never_generically_loads_resources():
    code = NATIVE.read_text()
    assert 'node.get_class() == "TextureRect"' in code
    assert 'property_name = "texture"' in code
    assert 'node.get_class() == "Button"' in code
    assert 'property_name = "icon"' in code
    assert "node.get_script() != null" in code
    executable = "\n".join(line for line in code.splitlines() if not line.strip().startswith("#"))
    assert "ResourceLoader.load(" not in executable
    assert "take_over_path(" not in executable
    assert "instantiate(" not in executable
    assert "candidate.load(imported_path)" in executable
    assert "ResourceLoader.get_cached_ref(texture_path)" in executable


def test_native_contract_null_transition_undo_rollback_and_persistent_reference():
    code = NATIVE.read_text()
    assert "candidate.resource_path = texture_path" in code
    assert "cached_texture.resource_path != texture_path" in code
    assert "if previous == texture:" in code
    assert 'result.status = "unchanged"' in code
    assert code.index("node.set(property_name, texture)") < code.index("undo.create_action(")
    assert "node.set(property_name, previous)" in code
    assert 'failed["rollback_verified"] = node.get(property_name) == previous' in code
    assert "undo.add_do_property(node, property_name, texture)" in code
    assert "undo.add_undo_property(node, property_name, previous)" in code
    assert "undo.commit_action(false)" in code
    assert '"source_native_rgba8_matches_import"' in code
    # Native save/reopen and undo execution are acceptance gates, not claimed by
    # these source assertions. The runner uses real MCP save/open/readback calls.


def test_empty_regular_file_rejected(project):
    (project / "empty.png").touch()
    with pytest.raises(TextureValidationError):
        _read_regular(project, "res://empty.png", MAX_PNG_BYTES)


def test_imported_payload_drift_is_pending(project):
    path = next((project / ".godot/imported").glob("*.ctex"))
    path.write_bytes(ctex_bytes(png_bytes(color=(0, 0, 0, 255))))
    with pytest.raises(TextureImportPending, match="Imported texture changed"):
        prepare_texture(str(project), PARAMS)


def test_project_identity_uses_portable_slashes(project):
    from pathlib import PureWindowsPath

    proof = prepare_texture(str(project), PARAMS)["_validated_texture"]
    assert proof["project_path"] == project.resolve().as_posix()
    assert PureWindowsPath(r"C:\Projects\Example").as_posix() == "C:/Projects/Example"
    code = NATIVE.read_text()
    assert 'OS.get_name() == "Windows"' in code
    assert "proof_project_path.to_lower()" in code


@pytest.mark.parametrize("lossless", [True, False])
def test_imported_webp_must_be_lossless(lossless):
    output = io.BytesIO()
    Image.new("RGBA", (8, 8), (25, 50, 80, 255)).save(output, format="WEBP", lossless=lossless)
    payload = output.getvalue()
    data = bytearray(ctex_bytes(payload))
    struct.pack_into("<I", data, 36, 2)
    if lossless:
        _validate_ctex(bytes(data), (8, 8))
    else:
        with pytest.raises(TextureValidationError, match="lossless"):
            _validate_ctex(bytes(data), (8, 8))


def test_webp_header_rejected_before_pillow_decoder(monkeypatch):
    output = io.BytesIO()
    Image.new("RGBA", (8, 8), (25, 50, 80, 255)).save(output, format="WEBP", lossless=True)
    payload = bytearray(output.getvalue())
    # VP8L dimensions claim 16384 x 16384, while the CTEX remains a bounded 8x8.
    struct.pack_into("<I", payload, 21, 0x0FFFFFFF)
    data = bytearray(ctex_bytes(bytes(payload)))
    struct.pack_into("<I", data, 36, 2)

    def no_decoder(*_args, **_kwargs):
        pytest.fail("Header rejection must precede WebPAnimDecoder allocation")

    monkeypatch.setattr(Image, "open", no_decoder)
    with pytest.raises(TextureValidationError, match="dimensions"):
        _validate_ctex(bytes(data), (8, 8))


def test_png_metadata_decode_failure_has_structured_rejection(project, monkeypatch):
    import zlib

    raw = png_bytes(size=(1, 1))
    compressed_text = b"note\x00\x00" + zlib.compress(b"x" * (1024 * 1024 + 1))
    chunk_type = b"zTXt"
    chunk = (
        struct.pack(">I", len(compressed_text))
        + chunk_type
        + compressed_text
        + struct.pack(">I", zlib.crc32(chunk_type + compressed_text))
    )
    (project / "assets/icon.png").write_bytes(raw[:33] + chunk + raw[33:])
    calls = []

    def host(method, _params):
        calls.append(method)
        return {"project_path": str(project)}

    monkeypatch.setattr(capability_dispatch, "call_host", host)
    result = capability_dispatch._dispatch_ui_texture(PARAMS)
    assert result["assigned"] is False and result["status"] == "rejected"
    assert calls == ["capability.get_project_info"]


def test_output_schema_cannot_claim_assignment_for_null_or_pending():
    jsonschema.validate(
        skill_success("Waiting", assigned=False, status="import_pending", reason="waiting"),
        UI_TEXTURE_OUTPUT_SCHEMA,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            skill_success("Invalid", assigned=True, status="import_pending"),
            UI_TEXTURE_OUTPUT_SCHEMA,
        )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            skill_success("Invalid", assigned=True, status="assigned", resource_path=None),
            UI_TEXTURE_OUTPUT_SCHEMA,
        )
