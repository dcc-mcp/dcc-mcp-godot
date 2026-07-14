import zipfile

import pytest

from tools.download_latest_godot import _extract_archive


def test_extract_archive_rejects_parent_traversal(tmp_path):
    archive = tmp_path / "godot.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "unsafe")

    with pytest.raises(RuntimeError, match="unsafe path"):
        _extract_archive(archive, tmp_path / "output")


def test_extract_archive_accepts_files_below_output(tmp_path):
    archive = tmp_path / "godot.zip"
    output = tmp_path / "output"
    output.mkdir()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Godot_v4.7-stable_linux.x86_64", "binary")

    _extract_archive(archive, output)

    assert (output / "Godot_v4.7-stable_linux.x86_64").read_text() == "binary"
