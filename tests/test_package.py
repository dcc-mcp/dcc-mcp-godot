import json
import re
from pathlib import Path

from dcc_mcp_godot import __version__

ROOT = Path(__file__).parents[1]
PLUGIN_CFG = (
    ROOT / "src" / "dcc_mcp_godot" / "godot_addon" / "addons" / "dcc_mcp_godot" / "plugin.cfg"
)


def test_version_metadata_is_synchronized():
    assert f'version = "{__version__}"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / ".release-please-manifest.json").read_text(encoding="utf-8"))
    assert manifest["."] == __version__


def _plugin_cfg_version_line():
    match = re.search(r'^version="[^"]+".*$', PLUGIN_CFG.read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None, "plugin.cfg must declare a version"
    return match.group(0)


def test_addon_plugin_cfg_version_matches_the_package():
    # The addon version is what users read in Godot's plugin manager and quote in
    # bug reports, so it must never drift from the released package version.
    version = re.search(r'"([^"]+)"', _plugin_cfg_version_line()).group(1)
    assert version == __version__


def test_release_please_owns_the_addon_plugin_cfg_version():
    # release-please only rewrites lines carrying the marker, and only files
    # listed in extra-files, so both halves of the wiring are pinned here.
    assert "x-release-please-version" in _plugin_cfg_version_line()
    config = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
    extra_files = config["packages"]["."]["extra-files"]
    assert {
        "type": "generic",
        "path": "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot/plugin.cfg",
    } in extra_files


def test_addon_and_roguelike_templates_are_packaged():
    addon = ROOT / "src" / "dcc_mcp_godot" / "godot_addon" / "addons" / "dcc_mcp_godot"
    assert (addon / "plugin.cfg").is_file()
    assert (addon / "plugin.gd").is_file()
    assert (addon / "commands.gd").is_file()
    assert (addon / "templates" / "roguelike" / "game.gd").is_file()
    assert (addon / "templates" / "roguelike" / "ci_smoke.gd").is_file()
    assert (
        ROOT / "src" / "dcc_mcp_godot" / "schemas" / "playtest_actions_manifest_v1.schema.json"
    ).is_file()


def test_godot_export_skill_ships_cross_platform_packaging_guidance():
    skill = ROOT / "src" / "dcc_mcp_godot" / "skills" / "godot-export"
    skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
    guide_path = skill / "references" / "platform-packaging.md"

    assert "references/platform-packaging.md" in skill_text
    assert guide_path.is_file()

    guide = guide_path.read_text(encoding="utf-8")
    for platform in ("Windows", "macOS", "Linux", "Web", "Android"):
        assert f"## {platform}" in guide
    assert "C:/Windows/Fonts" in guide
    assert "bundled font" in guide.lower()
    assert "CJK" in guide
    assert "exported artifact" in guide


def test_release_workflow_uses_trusted_publishing_environment():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "name: pypi" in workflow
    # The publish action is pinned to an immutable commit SHA; only the action
    # identity matters here, not which tag or SHA pins it.
    assert "pypa/gh-action-pypi-publish@" in workflow
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


def test_hatchling_132_is_an_executable_isolated_build_contract():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert 'requires = ["hatchling>=1.26"]' in project
    assert 'python -m pip install "hatchling==1.32.0" build twine' in workflow
    assert "python -m build --no-isolation" in workflow
    assert "python -m twine check dist/*" in workflow
