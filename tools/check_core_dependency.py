"""Check the adapter's declared and built-wheel Core compatibility range.

Canonical policy (the source of truth, not a separate adapter policy):
https://github.com/dcc-mcp/dcc-mcp-core/blob/main/compatibility/core-bounds.json
This packaging gate handles this repository's explicit >=floor,<ceiling form.
Keep it aligned with dcc_mcp_core.deployment.core_bounds; importing a newer Core
checker must not force an unrelated increase of the adapter's supported floor.
"""

import argparse
from email.parser import BytesParser
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10 build environments
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


class CoreDependencyError(ValueError):
    """The adapter or built wheel violates the Core dependency contract."""


def _require(condition, message):
    if not condition:
        raise CoreDependencyError(message)


def core_requirement(requirements):
    parsed = [Requirement(item) for item in requirements]
    matches = [item for item in parsed if canonicalize_name(item.name) == "dcc-mcp-core"]
    _require(len(matches) == 1, "Expected one unconditional Core dependency")
    requirement = matches[0]
    _require(
        not requirement.url and not requirement.marker and not requirement.extras,
        "Core dependency must be an unconditional version range without extras or a URL",
    )
    return requirement


def check_core_range(requirement):
    bounds = list(requirement.specifier)
    _require(
        len(bounds) == 2 and {bound.operator for bound in bounds} == {">=", "<"},
        "Core dependency requires explicit >=floor,<ceiling bounds",
    )
    floor = Version(next(bound.version for bound in bounds if bound.operator == ">="))
    ceiling = Version(next(bound.version for bound in bounds if bound.operator == "<"))
    _require(
        floor.major == 0 and not floor.is_prerelease and not ceiling.is_prerelease,
        "Core dependency bounds must use stable 0.x versions",
    )
    next_minor = Version(f"0.{floor.minor + 1}.0")
    _require(floor < ceiling <= next_minor, "Core dependency must stay within one minor line")


def project_metadata(root=ROOT):
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def check_wheel(wheel, root=ROOT):
    project = project_metadata(root)
    declared = core_requirement(project["dependencies"])
    check_core_range(declared)
    with ZipFile(wheel) as archive:
        metadata_paths = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        _require(len(metadata_paths) == 1, "Expected exactly one wheel METADATA file")
        metadata = BytesParser().parsebytes(archive.read(metadata_paths[0]))
    names = metadata.get_all("Name", [])
    versions = metadata.get_all("Version", [])
    _require(len(names) == 1, "Wheel METADATA requires exactly one Name field")
    _require(len(versions) == 1, "Wheel METADATA requires exactly one Version field")
    _require(
        canonicalize_name(names[0]) == canonicalize_name(project["name"]),
        "Wheel name differs from pyproject.toml",
    )
    _require(versions[0] == project["version"], "Wheel version differs from pyproject.toml")
    packaged = core_requirement(metadata.get_all("Requires-Dist", []))
    check_core_range(packaged)
    _require(
        packaged.specifier == declared.specifier,
        "Wheel Core range differs from pyproject.toml",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheels", nargs="+", type=Path)
    args = parser.parse_args()
    for wheel in args.wheels:
        try:
            check_wheel(wheel)
        except (ValueError, OSError, BadZipFile, KeyError) as error:
            parser.exit(1, f"{wheel}: {error}\n")
        print(f"{wheel.name}: Core dependency contract passed")


if __name__ == "__main__":
    main()
