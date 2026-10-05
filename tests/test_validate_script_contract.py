"""Contract tests for the ``validate_script`` path / script_path alias.

These guard the defect where the tool schema declared both ``path`` and
``script_path`` while the host read only ``path``: a caller naming one script
was answered about an empty path, and empty GDScript reloads as ``OK``, so the
answer was ``valid: true`` for no script at all. A silent success is worse than
a rejection, so the host must either compile what the caller named or fail
loudly.

The two sides of the fix are covered here: the adapter normalizer in
``capability_dispatch.py``, which resolves the alias before the wire call, and
the host handler in ``capabilities.gd``, which is the last line of defence for
callers that reach the editor by another route.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dcc_mcp_godot import capability_dispatch

ROOT = Path(__file__).parents[1]
CAPABILITIES = (
    ROOT / "src" / "dcc_mcp_godot" / "godot_addon" / "addons" / "dcc_mcp_godot" / "capabilities.gd"
)


def _body(name: str, following: str) -> str:
    """Return the body of ``func name``, up to the start of ``func following``."""
    source = CAPABILITIES.read_text(encoding="utf-8")
    start = source.index(f"func {name}")
    end = source.index(f"func {following}", start)
    assert start < end, f"{following} does not follow {name}"
    return source[start:end]


def _validate_script() -> str:
    return _body("_validate_script(", "_search_in_files(")


# --------------------------------------------------------------------------
# Host side: capabilities.gd
# --------------------------------------------------------------------------


def test_validate_script_receives_the_tool_params() -> None:
    # The dispatch site is where the parameter used to be dropped; a handler
    # that never sees params cannot honour script_path at all.
    source = CAPABILITIES.read_text(encoding="utf-8")
    assert '"validate_script": return _validate_script(params)' in source
    assert "func _validate_script(params: Dictionary) -> Dictionary:" in source


def test_validate_script_reads_path_with_script_path_as_the_alias() -> None:
    body = _validate_script()
    assert 'params.get("path", "")' in body
    assert 'params.get("script_path", "")' in body


def test_validate_script_rejects_conflicting_path_aliases() -> None:
    # Two different scripts named in one call is a caller bug. Preferring one
    # of them silently would compile a script the caller did not name.
    body = _validate_script()
    assert "explicit_path != alias_path" in body
    assert '"Conflicting script paths: path=%s but script_path=%s"' in body
    assert body.index("Conflicting script paths") < body.index("GDScript.new()")


def test_validate_script_rejects_an_explicitly_empty_alias() -> None:
    # {"script_path": ""} is a caller mistake, not "no script requested": the
    # old code fell through to reload empty source, which reloads as OK.
    body = _validate_script()
    assert 'params.has("path") and explicit_path.is_empty()' in body
    assert 'params.has("script_path") and alias_path.is_empty()' in body
    assert "non-empty res:// path when supplied" in body
    assert body.index("non-empty res:// path when supplied") < body.index("GDScript.new()")


def test_validate_script_rejects_an_empty_path_instead_of_returning_valid() -> None:
    # The core regression: with no path and no source the old handler compiled
    # the empty string and answered {"valid": true}. Anything that reaches the
    # reload with nothing to compile is the defect, so the guard must run first
    # and no branch may hand a default path to the compiler.
    body = _validate_script()
    assert "if path.is_empty() and source.strip_edges().is_empty():" in body
    assert 'return _error("validate_script requires a non-empty source' in body
    assert body.index("source.strip_edges().is_empty()") < body.index("GDScript.new()")
    # An empty path is never read from disk, so no default can revive it.
    assert "_read_text(" not in body.split("source.strip_edges().is_empty()")[0]


def test_validate_script_rejects_a_whitespace_source_instead_of_returning_valid() -> None:
    # The same defect one notch narrower: GDScript.reload() answers OK for
    # "   " and "\n", so a guard that only tested the raw string still reported
    # {"valid": true} for a source nobody wrote. The guard has to trim.
    body = _validate_script()
    assert "source.strip_edges().is_empty()" in body
    assert body.index("source.strip_edges().is_empty()") < body.index("GDScript.new()")
    # The fallback below is deliberately left untrimmed: an explicit source
    # wins over path, so only a raw-empty source means "read the file".
    assert "if source.is_empty():" in body


def test_validate_script_still_compiles_inline_source_without_a_path() -> None:
    # Omitting the path keeps the documented "compile this source" behaviour;
    # the empty-path guard must not demand a path when source is supplied.
    body = _validate_script()
    assert "if source.is_empty():" in body
    assert body.index("path.is_empty() and source.strip_edges().is_empty()") < body.index(
        "if source.is_empty():"
    )
    assert "_read_text(" in body


def test_validate_script_reports_the_path_it_compiled() -> None:
    # Callers must be able to tell which of the two aliases was honoured.
    assert '"path": path' in _validate_script()


def test_validate_script_rejects_params_it_cannot_honour() -> None:
    # The skill input schema is a union over the whole skill, so a caller can
    # legally send node_path/query/base_type here. Ignoring them reproduces the
    # original defect: a plausible answer that never used the caller's input.
    body = _validate_script()
    assert '_unsupported_params(params, ["path", "script_path", "source"])' in body
    assert "only path (or script_path) and source are read" in body
    assert body.index("_unsupported_params(") < body.index("GDScript.new()")


# --------------------------------------------------------------------------
# Dispatch side: capability_dispatch.py
# --------------------------------------------------------------------------


@pytest.fixture
def host_calls(monkeypatch: pytest.MonkeyPatch):
    """Capture the params the adapter would put on the wire."""
    calls: list[dict[str, object]] = []

    def call_host(method: str, params: dict[str, object], **_: object) -> dict[str, object]:
        calls.append({"method": method, "params": params})
        return {"valid": True, "error": "OK", "path": str(params.get("path", ""))}

    monkeypatch.setattr(capability_dispatch, "call_host", call_host)
    return calls


def test_dispatch_sends_script_path_as_path(host_calls) -> None:
    # The defect: script_path was forwarded untouched and the host ignored it.
    capability_dispatch.dispatch("validate_script", {"script_path": "res://player.gd"})

    assert host_calls[0]["params"] == {"script_path": "res://player.gd", "path": "res://player.gd"}
    assert host_calls[0]["method"] == "capability.validate_script"


def test_dispatch_keeps_path_when_both_aliases_name_one_script(host_calls) -> None:
    capability_dispatch.dispatch(
        "validate_script", {"path": "res://player.gd", "script_path": "res://player.gd"}
    )

    assert host_calls[0]["params"]["path"] == "res://player.gd"


def test_dispatch_does_not_rewrite_params_for_other_actions(host_calls) -> None:
    # attach_script uses script_path as its own primary name, so the alias must
    # stay scoped to validate_script.
    capability_dispatch.dispatch("attach_script", {"script_path": "res://player.gd"})

    assert host_calls[0]["params"] == {"script_path": "res://player.gd"}


def test_dispatch_rejects_conflicting_aliases(host_calls) -> None:
    with pytest.raises(ValueError, match="Conflicting script paths"):
        capability_dispatch.dispatch(
            "validate_script", {"path": "res://a.gd", "script_path": "res://b.gd"}
        )

    assert host_calls == []


def test_dispatch_rejects_an_explicitly_empty_alias(host_calls) -> None:
    with pytest.raises(ValueError, match="non-empty res:// path"):
        capability_dispatch.dispatch("validate_script", {"script_path": ""})

    assert host_calls == []


def test_dispatch_rejects_an_empty_call_before_the_host_sees_it(host_calls) -> None:
    # The core regression on this side: nothing to compile must never become a
    # wire call, because an empty compile answers valid: true.
    for params in ({}, {"source": ""}):
        with pytest.raises(ValueError, match="non-empty source"):
            capability_dispatch.dispatch("validate_script", params)

    # Explicitly empty aliases are the same defect with a different shape.
    with pytest.raises(ValueError, match="non-empty res:// path"):
        capability_dispatch.dispatch("validate_script", {"path": "", "script_path": ""})

    assert host_calls == []


def test_dispatch_rejects_a_whitespace_only_source(host_calls) -> None:
    # Same regression as the empty source, narrower: Godot reloads a blank
    # source as OK, so "   " and "\n" must not reach the wire at all.
    for params in ({"source": "   "}, {"source": "\n"}, {"source": "\t \n "}):
        with pytest.raises(ValueError, match="non-empty source"):
            capability_dispatch.dispatch("validate_script", params)

    assert host_calls == []


def test_dispatch_accepts_inline_source_without_a_path(host_calls) -> None:
    capability_dispatch.dispatch("validate_script", {"source": "extends Node"})

    assert host_calls[0]["params"] == {"source": "extends Node"}
