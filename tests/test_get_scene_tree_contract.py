"""Contract tests for the read-only ``get_scene_tree`` scene_path contract.

These guard the defect where ``scene_path`` was accepted by the tool schema but
ignored by the host: every call returned the edited scene with ``success: true``,
so a caller asking about one scene silently received another scene's tree. A
silent wrong answer is worse than a rejection, so the host must either honour the
requested path or fail loudly.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
CAPABILITIES = ROOT / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot/capabilities.gd"


def _body(name: str, following: str) -> str:
    """Return the body of ``func name``, up to the start of ``func following``."""
    source = CAPABILITIES.read_text(encoding="utf-8")
    start = source.index(f"func {name}")
    end = source.index(f"func {following}", start)
    assert start < end, f"{following} does not follow {name}"
    return source[start:end]


def _get_scene_tree() -> str:
    return _body("_get_scene_tree(", "_edited_scene_tree(")


def _edited_scene_tree() -> str:
    return _body("_edited_scene_tree(", "_packed_scene_tree(")


def _packed_scene_tree() -> str:
    return _body("_packed_scene_tree(", "_create_scene(")


def test_get_scene_tree_receives_the_tool_params() -> None:
    # The dispatch site is where the parameter used to be dropped; a no-argument
    # handler cannot honour scene_path no matter what the body does.
    source = CAPABILITIES.read_text(encoding="utf-8")
    assert '"get_scene_tree": return _get_scene_tree(params)' in source
    assert "func _get_scene_tree(params: Dictionary) -> Dictionary:" in source


def test_get_scene_tree_reads_scene_path_with_path_as_the_alias() -> None:
    body = _get_scene_tree()
    assert 'params.get("scene_path", params.get("path", ""))' in body


def test_get_scene_tree_rejects_unsupported_params_instead_of_ignoring_them() -> None:
    # The skill input schema is a union over the whole skill, so a caller can
    # legally send root_type/mode/open here. Ignoring them reproduces the
    # original defect: a plausible answer that never used the caller's input.
    body = _get_scene_tree()
    assert '_unsupported_params(params, ["scene_path", "path"])' in body
    assert "only scene_path (or path) is read" in body
    # The rejection is the first branch, before anything is read.
    assert body.index("_unsupported_params(") < body.index("_existing_path(")


def test_get_scene_tree_validates_the_requested_scene_path() -> None:
    # An unusable path must fail, never fall back to the edited scene.
    body = _get_scene_tree()
    assert '_existing_path(requested, ["tscn", "scn"])' in body
    assert body.index("_existing_path(") < body.index("return _packed_scene_tree(")


def test_get_scene_tree_reads_from_disk_without_opening_the_scene() -> None:
    # The whole point of the parameter: read a scene the caller is not editing,
    # without the write side effect of open_scene.
    packed = _packed_scene_tree()
    assert "packed.instantiate()" in packed
    assert "instance.free()" in packed
    assert '"source": "file"' in packed
    assert "EditorInterface.open_scene_from_path" not in packed
    # The snapshot is taken before the instance is freed.
    assert packed.index("_node_snapshot(instance") < packed.index("instance.free()")


def test_get_scene_tree_reports_which_scene_it_answered() -> None:
    # Callers must be able to tell an edited-scene answer from a file answer
    # without comparing trees by hand.
    assert '"source": "edited"' in _edited_scene_tree()
    assert '"scene_path": path' in _packed_scene_tree()


def test_get_scene_tree_still_reads_the_edited_scene_by_default() -> None:
    # Omitting the parameter keeps the documented default behaviour.
    assert "requested.is_empty():" in _get_scene_tree()
    edited = _edited_scene_tree()
    assert "EditorInterface.get_edited_scene_root()" in edited
    assert 'return _error("No scene is open")' in edited
