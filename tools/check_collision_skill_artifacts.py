"""Check the collision skill contract in built artifacts, without importing the adapter."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
SKILLS = ("godot-scene-3d", "godot-physics", "godot-testing-qa")
REFERENCE = "godot-physics/references/collision-intent.md"


def expected_files(root: Path = ROOT) -> dict[str, bytes]:
    paths = [f"{skill}/{name}" for skill in SKILLS for name in ("SKILL.md", "tools.yaml")]
    paths += [f"{skill}/scripts/dispatch.py" for skill in SKILLS]
    paths.append(REFERENCE)
    return {
        f"dcc_mcp_godot/skills/{path}": (root / "src/dcc_mcp_godot/skills" / path).read_bytes()
        for path in paths
    }


def verify_artifact(artifact: Path, expected: dict[str, bytes]) -> None:
    if artifact.name.endswith(".whl"):
        with zipfile.ZipFile(artifact) as archive:
            for path, content in expected.items():
                matches = [info for info in archive.infolist() if info.filename == path]
                if len(matches) != 1 or archive.read(matches[0]) != content:
                    raise ValueError(f"{artifact.name}: missing, duplicated, or stale {path}")
    elif artifact.name.endswith(".tar.gz"):
        with tarfile.open(artifact, "r:gz") as archive:
            for path, content in expected.items():
                # The sdist has exactly one arbitrary versioned top-level directory.
                matches = [
                    member
                    for member in archive.getmembers()
                    if member.isfile() and member.name.partition("/")[2] == f"src/{path}"
                ]
                if len(matches) != 1:
                    raise ValueError(f"{artifact.name}: missing or duplicated {path}")
                stream = archive.extractfile(matches[0])
                if stream is None or stream.read() != content:
                    raise ValueError(f"{artifact.name}: stale {path}")
    else:
        raise ValueError(f"Unsupported artifact: {artifact}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path, nargs="+")
    args = parser.parse_args()
    if not any(p.name.endswith(".whl") for p in args.artifacts) or not any(
        p.name.endswith(".tar.gz") for p in args.artifacts
    ):
        parser.error("Supply both wheel and sdist artifacts")
    expected = expected_files()
    for artifact in args.artifacts:
        verify_artifact(artifact, expected)
        print(f"verified {len(expected)} collision skill files in {artifact.name}")


if __name__ == "__main__":
    main()
