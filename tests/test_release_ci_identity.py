"""Keep release PR automation on the explicit organization credential."""

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/release.yml"


def bash_executable():
    if os.name == "nt":
        # PATH may point at the WSL launcher instead of an installed shell.
        git = shutil.which("git")
        if git is None:
            return None
        candidate = Path(git).resolve().parent.parent / "bin" / "bash.exe"
        return str(candidate) if candidate.is_file() else None
    return shutil.which("bash")


BASH = bash_executable()


def release_steps():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = workflow.split("  release-please:\n", 1)[1].split("\n  publish:", 1)[0]
    return job.split("    steps:\n", 1)[1]


def test_release_action_uses_only_the_organization_token():
    steps = release_steps()
    action = steps.split("      - id: release\n", 1)[1]
    assert "uses: googleapis/release-please-action@v5" in action
    assert re.findall(r"^          token: (.+)$", action, re.MULTILINE) == [
        "${{ secrets.PERSONAL_ACCESS_TOKEN }}"
    ]
    assert "github.token" not in steps
    assert "secrets.GITHUB_TOKEN" not in steps
    assert "||" not in steps


def test_preflight_is_unconditional_and_precedes_release():
    steps = release_steps()
    preflight, _ = steps.split("      - id: release\n", 1)
    assert preflight.startswith("      - name: Require organization release token\n")
    assert "        shell: bash\n" in preflight
    assert "          RELEASE_PR_TOKEN: ${{ secrets.PERSONAL_ACCESS_TOKEN }}\n" in preflight
    assert "        if:" not in steps
    assert "continue-on-error:" not in steps


@pytest.mark.skipif(BASH is None, reason="native Bash is unavailable")
@pytest.mark.parametrize("token,expected", [(None, 1), ("", 1), ("offline-fixture-only", 0)])
def test_preflight_fails_closed_without_disclosing_token(token, expected):
    preflight = release_steps().split("      - id: release\n", 1)[0]
    script = textwrap.dedent(preflight.split("        run: |\n", 1)[1])
    env = dict(os.environ)
    env.pop("RELEASE_PR_TOKEN", None)
    if token is not None:
        env["RELEASE_PR_TOKEN"] = token
    result = subprocess.run(
        [BASH, "-eu", "-c", script], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == expected
    if expected:
        assert "::error::Organization PERSONAL_ACCESS_TOKEN is unavailable" in result.stdout
    assert "offline-fixture-only" not in result.stdout + result.stderr
