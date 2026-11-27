"""Build the addon archive used by the Godot Asset Store.

The store expects an archive whose root contains ``addons/dcc_mcp_godot``.
This command keeps that archive separate from the Python wheel and sdist so a
release can publish both artifacts without relying on a working tree layout.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADDON = ROOT / "src" / "dcc_mcp_godot" / "godot_addon" / "addons" / "dcc_mcp_godot"
VERSION_PATTERN = re.compile(r'^version="(?P<version>[^"]+)".*$', re.MULTILINE)


def read_addon_version(plugin_cfg: Path) -> str:
    """Read the release-managed version from ``plugin.cfg``."""

    match = VERSION_PATTERN.search(plugin_cfg.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"No plugin version found in {plugin_cfg}")
    return match.group("version")


def iter_files(addon_root: Path):
    """Yield addon files in deterministic archive order."""

    for path in sorted((item for item in addon_root.rglob("*") if item.is_file())):
        yield path


def build_package(addon_root: Path, output: Path) -> tuple[str, int, str]:
    """Create a reproducible Godot addon archive and return its metadata."""

    addon_root = addon_root.resolve()
    output = output.resolve()
    plugin_cfg = addon_root / "plugin.cfg"
    if not plugin_cfg.is_file():
        raise ValueError(f"Addon root does not contain plugin.cfg: {addon_root}")

    files = list(iter_files(addon_root))
    if not files:
        raise ValueError(f"Addon root is empty: {addon_root}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(addon_root).as_posix()
            archive_name = f"addons/dcc_mcp_godot/{relative}"
            info = zipfile.ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return output.name, len(files), digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--addon-root",
        type=Path,
        default=DEFAULT_ADDON,
        help="source addon directory (default: the repository addon)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output ZIP path (default: dist/dcc-mcp-godot-<version>.zip)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    addon_root = args.addon_root if args.addon_root.is_absolute() else ROOT / args.addon_root
    version = read_addon_version(addon_root / "plugin.cfg")
    output = args.output or ROOT / "dist" / f"dcc-mcp-godot-{version}.zip"
    if not output.is_absolute():
        output = ROOT / output

    filename, file_count, digest = build_package(addon_root, output)
    print(f"package={output}")
    print(f"version={version}")
    print(f"files={file_count}")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
