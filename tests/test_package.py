import json
from pathlib import Path

from dcc_mcp_godot import __version__

ROOT = Path(__file__).parents[1]


def test_version_metadata_is_synchronized():
    assert f'version = "{__version__}"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / ".release-please-manifest.json").read_text(encoding="utf-8"))
    assert manifest["."] == __version__


def test_addon_and_roguelike_templates_are_packaged():
    addon = ROOT / "src" / "dcc_mcp_godot" / "godot_addon" / "addons" / "dcc_mcp_godot"
    assert (addon / "plugin.cfg").is_file()
    assert (addon / "plugin.gd").is_file()
    assert (addon / "commands.gd").is_file()
    assert (addon / "templates" / "roguelike" / "game.gd").is_file()
    assert (addon / "templates" / "roguelike" / "ci_smoke.gd").is_file()


def test_release_workflow_uses_trusted_publishing_environment():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "name: pypi" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "ref: ${{ needs.release-please.outputs.tag_name }}" in workflow


def test_install_sop_is_public_and_canonical_console_is_packaged():
    guide = (ROOT / "install.md").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    for verb in ("install", "status", "verify", "uninstall", "upgrade"):
        assert f"dcc-mcp-godot {verb}" in guide
    for platform in ("Windows", "macOS", "Linux"):
        assert platform in guide
    assert 'dcc-mcp-godot = "dcc_mcp_godot.cli:main"' in project
    assert 'dcc-mcp-godot-install = "dcc_mcp_godot.install:main"' in project
