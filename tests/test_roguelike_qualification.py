from pathlib import Path

import probe_roguelike_qualification as probe

ROOT = Path(__file__).parents[1]
GAME = (
    ROOT
    / "src"
    / "dcc_mcp_godot"
    / "godot_addon"
    / "addons"
    / "dcc_mcp_godot"
    / "templates"
    / "roguelike"
    / "game.gd"
)
COMMANDS = (
    ROOT / "src" / "dcc_mcp_godot" / "godot_addon" / "addons" / "dcc_mcp_godot" / "commands.gd"
)


def test_qualification_project_preserves_export_contract(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    probe.project_files(project, "Windows Desktop", "Windows Desktop", None, None)
    settings = (project / "project.godot").read_text(encoding="utf-8")
    presets = (project / "export_presets.cfg").read_text(encoding="utf-8")
    assert 'run/main_scene="res://roguelike/main.tscn"' in settings
    assert 'name="Windows Desktop"' in presets
    assert 'name="Web"' in presets
    assert (project / "roguelike" / "ci_smoke.gd").is_file()


def test_game_template_exposes_observable_input_failure_and_restart_state():
    source = GAME.read_text(encoding="utf-8")
    for token in (
        'Input.is_action_just_pressed("ui_select")',
        'Input.is_action_just_pressed("ui_accept")',
        '"game_over": health <= 0.0',
        '"restart_count": restart_count',
        "JavaScriptBridge.eval",
    ):
        assert token in source


def test_create_validation_requires_the_gameplay_contract():
    source = COMMANDS.read_text(encoding="utf-8")
    assert 'instance.has_method("spawn_enemies_for_test")' in source
    assert '"restart"' in source
