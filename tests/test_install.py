from pathlib import Path

import pytest

from dcc_mcp_godot.install import install_addon


def test_install_addon_copies_packaged_plugin(tmp_path: Path):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")

    destination = install_addon(tmp_path)

    assert (destination / "plugin.cfg").is_file()
    assert (destination / "commands.gd").is_file()
    with pytest.raises(FileExistsError):
        install_addon(tmp_path)


def test_install_addon_requires_godot_project(tmp_path: Path):
    with pytest.raises(ValueError, match="project.godot"):
        install_addon(tmp_path)
