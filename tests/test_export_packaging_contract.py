"""Host-free instruction regressions; these do not certify an exported game."""

import importlib.util
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SKILL = ROOT / "src/dcc_mcp_godot/skills/godot-export"


def test_export_entry_requires_first_response_preflight():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for requirement in (
        "first response",
        "standalone",
        "EXE",
        "edition",
        "architecture",
        "download permission",
        "references/platform-packaging.md",
    ):
        assert requirement in text


def test_generator_preserves_export_entry_contract():
    spec = importlib.util.spec_from_file_location(
        "export_skill_generator", ROOT / "tools/generate_capability_skills.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as temporary:
        with patch.object(module, "ROOT", Path(temporary)):
            module.generate()
        assert (Path(temporary) / "godot-export/SKILL.md").read_text(encoding="utf-8") == (
            SKILL / "SKILL.md"
        ).read_text(encoding="utf-8")


def test_packaging_reference_preserves_authority_and_rebuild_receipts():
    text = (SKILL / "references/platform-packaging.md").read_text(encoding="utf-8")
    for requirement in (
        "## First-response readiness gate",
        "## Trusted persistent template cache",
        "official URL",
        "SHA-256",
        "archive member",
        "free disk space",
        "download size",
        "Do not download or install",
        "unknown, not cleaned",
        "isolated snapshot",
        "existing saves",
        "startup logs",
        "not-tested",
        "combat",
        "chest",
        "reset",
        "provider/runtime/PID/birth/HWND",
    ):
        assert requirement in text


def test_relic_fixture_distinguishes_source_web_and_windows_deliverables():
    text = (SKILL / "references/platform-packaging.md").read_text(encoding="utf-8")
    for row in (
        "| RelicCourier-native.zip | Editable source |",
        "| Web HTML/JS/WASM/PCK | Web build |",
        "| Windows EXE + required PCK/native libraries | Windows build candidate |",
    ):
        assert row in text
    assert "4.6.3 Windows release template is missing" in text
    assert "Do not substitute a 4.7 template" in text
