"""Exercise interpreter selection with real isolated Python subprocesses."""

import json
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from dcc_mcp_godot import install


@pytest.fixture(params=[False, True], ids=["copied-python", "symlinked-python"])
def isolated_python(tmp_path, request, monkeypatch):
    if request.param and os.name == "nt":
        pytest.skip("Windows venvs use launcher executables by default")
    # Do not inherit a caller's package search path or Python installation.
    monkeypatch.delenv("PYTHONPATH", raising=False)
    monkeypatch.delenv("PYTHONHOME", raising=False)
    root = tmp_path / "selected environment"
    venv.EnvBuilder(with_pip=False, symlinks=request.param).create(root)
    python = root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    assert python.is_symlink() is request.param
    site_packages = Path(
        subprocess.check_output(
            [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            text=True,
        ).strip()
    )
    return python, site_packages


@pytest.mark.parametrize("core_version", ["0.20.41", "0.20.42", None, "0.20.40"])
@pytest.mark.parametrize("selection", ["absolute", "relative", "default"])
def test_install_probes_selected_environment(
    tmp_path, monkeypatch, capsys, isolated_python, core_version, selection
):
    python, site_packages = isolated_python
    if core_version is not None:
        # The installer only reads distribution metadata; no network or Core
        # native extension is needed to distinguish this venv from its base.
        metadata = site_packages / "dcc_mcp_core-0.0.0.dist-info"
        metadata.mkdir()
        (metadata / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: dcc-mcp-core\nVersion: {core_version}\n",
            encoding="utf-8",
        )
    project = tmp_path / "project"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        install,
        "_probe_godot",
        lambda path: {"path": str(path), "version": "4.4.1", "version_tuple": (4, 4, 1)},
    )
    arguments = ["install", "project", "--dcc-path", "godot", "--dry-run", "--json"]
    if selection == "default":
        monkeypatch.setattr(sys, "executable", str(python))
    else:
        selected = python.relative_to(tmp_path) if selection == "relative" else python
        arguments.extend(["--python", str(selected)])

    exit_code = install.main(arguments)
    report = json.loads(capsys.readouterr().out)

    if core_version in {"0.20.41", "0.20.42"}:
        assert exit_code == 0
        assert report["status"] == "planned"
        assert report["core_version"] == core_version
    else:
        assert exit_code == 10
        assert report["verify"]["failure_reason"] == "preflight_failed"
    assert not (project / "addons").exists()
    assert not (project / ".dcc-mcp").exists()


def test_preflight_rejects_missing_interpreter(tmp_path):
    import argparse

    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    args = argparse.Namespace(project=tmp_path, python=tmp_path / "missing", dcc_path=None)
    with pytest.raises(ValueError, match="Python interpreter not found"):
        install._preflight_install(args)
