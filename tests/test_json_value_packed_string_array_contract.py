"""Contract tests for the ``_json_value`` PackedStringArray branch.

These guard the defect where ``get_project_settings`` returned PackedStringArray
values as JSON *strings*: ``{"application/config/features": "[\"4.6\"]"}``
instead of ``["4.6"]``. ``_json_value`` recursed over plain ``Array`` but
``PackedStringArray`` is not an ``Array``, so it fell through to
``return str(value)`` and handed callers a quoted rendering of the array. A
caller type-checking the value then failed on a perfectly valid setting read.

Only ``PackedStringArray`` is in scope: the other Packed* array types are
deliberately left on the old path until they are measured separately.
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


def _json_value() -> str:
    return _body("_json_value(", "_string_array(")


def test_json_value_has_an_explicit_packed_string_array_branch() -> None:
    # The defect was the absence of this branch, so assert on the type test
    # itself rather than on anything incidental to how it is implemented.
    body = _json_value()
    assert "value is PackedStringArray:" in body


def test_packed_string_array_branch_returns_an_array() -> None:
    # The observable contract: a JSON array, not str(value). A branch that
    # declared an Array but returned a string would still fail the caller.
    body = _json_value()
    start = body.index("value is PackedStringArray:")
    end = body.index("if value is Rect2", start)
    branch = body[start:end]
    # An untyped `[]` is a plain Array and is recursed over by the Array branch
    # further down, which would re-enter and re-match PackedStringArray.
    assert "Array = []" in branch
    assert ".append(" in branch
    assert "return packed_strings" in branch
    # str(value) in this branch is exactly the bug; so is delegating to the
    # generic Array recursion, which would hit PackedStringArray again.
    assert "str(value)" not in branch
    assert "_json_value(" not in branch


def test_packed_string_array_branch_precedes_the_string_fallthrough() -> None:
    # str(value) is the last resort; every typed branch must come before it.
    body = _json_value()
    assert body.index("value is PackedStringArray:") < body.rindex("return str(value)")


def test_json_value_still_returns_plain_strings_unchanged() -> None:
    # A String that happens to look like JSON must stay a String: converting it
    # would silently retype unrelated settings on the same read path.
    body = _json_value()
    assert "value is String: return value" in body
    # The String return is the first branch, before any array handling, so a
    # JSON-looking string never reaches the PackedStringArray branch.
    assert body.index("value is String: return value") < body.index("value is PackedStringArray:")


def test_other_serialization_branches_are_unchanged() -> None:
    # The fix is scoped to one branch; these neighbours must keep their shape.
    body = _json_value()
    for expected in (
        "value is Vector2 or value is Vector2i: return [value.x, value.y]",
        "value is Vector3 or value is Vector3i: return [value.x, value.y, value.z]",
        "value is Color: return [value.r, value.g, value.b, value.a]",
        'value is Resource: return {"type": value.get_class(), "path": value.resource_path}',
        'value is Object: return {"type": value.get_class(),'
        ' "instance_id": value.get_instance_id()}',
        "value is Array:",
        "value is Dictionary:",
    ):
        assert expected in body, f"_json_value lost or altered: {expected}"


def test_other_packed_array_types_are_deliberately_not_special_cased() -> None:
    # Out of scope by decision: broadening to every Packed* type widens the
    # blast radius and needs its own measurement. Name them so an accidental
    # addition is caught, not silently shipped.
    body = _json_value()
    for packed in (
        "PackedInt32Array",
        "PackedInt64Array",
        "PackedFloat32Array",
        "PackedFloat64Array",
        "PackedVector2Array",
        "PackedVector3Array",
        "PackedColorArray",
        "PackedByteArray",
    ):
        assert packed not in body, f"{packed} was added without its own issue"


def test_string_array_helper_is_unchanged() -> None:
    # _string_array already handled PackedStringArray; it is not the defect and
    # must not be repurposed as the fix.
    helper = _body("_string_array(", "_collect_matching_nodes(")
    assert "value is Array or value is PackedStringArray:" in helper
    assert "Array[String] = []" in helper
