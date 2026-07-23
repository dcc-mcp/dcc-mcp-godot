"""Download the latest stable Godot binary from the official GitHub release."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import urllib.request
import zipfile
from pathlib import Path

RELEASE_URL = "https://api.github.com/repos/godotengine/godot/releases/latest"


def _asset_suffix() -> str:
    system = platform.system().lower()
    if system == "linux":
        return "_linux.x86_64.zip"
    if system == "windows":
        return "_win64.exe.zip"
    if system == "darwin":
        return "_macos.universal.zip"
    raise RuntimeError(f"Unsupported platform: {system}")


def _extract_archive(archive: Path, output: Path) -> None:
    root = output.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            destination = (output / member.filename).resolve()
            if destination != root and root not in destination.parents:
                raise RuntimeError(f"Godot archive contains an unsafe path: {member.filename}")
        bundle.extractall(output)


def download_latest(output: Path) -> Path:
    output = output.resolve()
    existing = (
        [path for path in output.rglob("Godot*") if path.is_file()] if output.exists() else []
    )
    if existing:
        if platform.system().lower() == "windows":
            console = [path for path in existing if path.name.lower().endswith("_console.exe")]
            existing = console or existing
        if platform.system().lower() == "darwin":
            existing = [path for path in existing if "Godot.app/Contents/MacOS/Godot" in str(path)]
        if existing:
            return existing[0].resolve()
    headers = {"User-Agent": "dcc-mcp-godot-ci", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(RELEASE_URL, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        release = json.load(response)
    suffix = _asset_suffix()
    assets = [
        item
        for item in release["assets"]
        if item["name"].endswith(suffix) and "mono" not in item["name"].lower()
    ]
    if len(assets) != 1:
        raise RuntimeError(f"Expected one Godot asset ending in {suffix}, found {len(assets)}")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / assets[0]["name"]
    with urllib.request.urlopen(assets[0]["browser_download_url"], timeout=120) as response:  # noqa: S310
        with archive.open("wb") as stream:
            shutil.copyfileobj(response, stream)
    _extract_archive(archive, output)
    archive.unlink()
    candidates = [path for path in output.rglob("Godot*") if path.is_file()]
    if platform.system().lower() == "windows":
        console = [path for path in candidates if path.name.lower().endswith("_console.exe")]
        candidates = console or candidates
    if platform.system().lower() == "darwin":
        candidates = list(output.rglob("Godot.app/Contents/MacOS/Godot"))
    if not candidates:
        raise RuntimeError("Downloaded Godot archive contained no executable")
    executable = candidates[0]
    if os.name != "nt":
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable.resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".godot-bin"))
    args = parser.parse_args()
    print(download_latest(args.output))


if __name__ == "__main__":
    main()
