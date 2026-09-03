"""Project-aware helpers for generating small Godot export-template builds."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MAX_FILE_BYTES = 1_000_000
MAX_SCAN_BYTES = 20_000_000
TEXT_SUFFIXES = {
    ".cfg",
    ".csv",
    ".gd",
    ".gdshader",
    ".godot",
    ".ini",
    ".json",
    ".md",
    ".res",
    ".shader",
    ".tres",
    ".tscn",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {".git", ".godot", ".build-size", "build", "dist"}
TARGET_PLATFORMS = {
    "android": "android",
    "ios": "ios",
    "linux": "linuxbsd",
    "macos": "macos",
    "web": "web",
    "windows": "windows",
}
FORCE_FEATURES = {
    "3d",
    "accesskit",
    "advanced-gui",
    "advanced-text",
    "graphite",
    "minimal-modules",
    "navigation",
    "vulkan",
    "xr",
    "zip",
}

_FEATURES_RE = re.compile(r"config/features\s*=\s*PackedStringArray\(\"([^\"]+)")
_RENDERER_RE = re.compile(
    r'renderer/rendering_method(?:\.mobile)?\s*=\s*"([^"]+)"',
    re.IGNORECASE,
)
_NON_LATIN_RE = re.compile(
    "["
    "\\u0590-\\u08ff"  # Hebrew, Arabic and related scripts.
    "\\u0900-\\u0dff"  # Indic scripts.
    "\\u0e00-\\u0e7f"  # Thai and Lao.
    "\\u1100-\\u11ff\\u2e80-\\u9fff\\uac00-\\ud7af"  # CJK and Hangul.
    "\\uf900-\\ufaff\\U00020000-\\U0002ffff"
    "]"
)

_FEATURE_PATTERNS: Mapping[str, tuple[str, ...]] = {
    "3d": (
        r"\b(?:Node3D|MeshInstance3D|Camera3D|WorldEnvironment|GridMap|"
        r"PhysicsBody3D|CollisionShape3D|NavigationRegion3D|NavigationAgent3D|"
        r"DirectionalLight3D|OmniLight3D|SpotLight3D|SubViewport3D)\b",
    ),
    "advanced_gui": (
        r"\b(?:RichTextLabel|TextEdit|CodeEdit|SpinBox|MenuBar|Tree|"
        r"ItemList|FileDialog|ColorPicker|GraphEdit|GraphNode|TabBar)\b",
    ),
    "navigation": (
        r"\b(?:NavigationRegion2D|NavigationRegion3D|NavigationAgent2D|"
        r"NavigationAgent3D|NavigationLink2D|NavigationLink3D|AStar2D|AStar3D|"
        r"AStarGrid2D)\b",
    ),
    "xr": (r"\b(?:XR|OpenXR|WebXR|ARVR)[A-Za-z0-9_]*\b",),
    "2d_physics": (
        r"\b(?:CharacterBody2D|StaticBody2D|RigidBody2D|AnimatableBody2D|"
        r"CollisionShape2D|CollisionPolygon2D|RayCast2D|Area2D|KinematicCollision2D)\b",
    ),
    "3d_physics": (
        r"\b(?:CharacterBody3D|StaticBody3D|RigidBody3D|AnimatableBody3D|"
        r"CollisionShape3D|CollisionPolygon3D|RayCast3D|Area3D|KinematicCollision3D)\b",
    ),
    "zip": (r"\b(?:ZIPReader|ZIPPacker)\b|zip://|\.zip(?:\W|$)",),
    "text": (
        r"\b(?:Label|RichTextLabel|TextEdit|CodeEdit|FontFile|FontVariation|"
        r"SystemFont|TextServer|Theme|Button|LineEdit)\b",
    ),
}


def _version_tuple(version: str | None) -> tuple[int, int, int] | None:
    if not version:
        return None
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def _is_at_least(version: str | None, major: int, minor: int) -> bool:
    parsed = _version_tuple(version)
    return parsed is not None and parsed >= (major, minor, 0)


def _normalise_renderer(value: str | None) -> str | None:
    if not value or value == "auto":
        return None
    value = value.casefold().replace("-", "_")
    aliases = {
        "gl_compatibility": "compatibility",
        "compatibility": "compatibility",
        "mobile": "mobile",
        "forward_plus": "forward_plus",
        "forwardplus": "forward_plus",
    }
    if value not in aliases:
        raise ValueError(f"Unsupported renderer: {value}")
    return aliases[value]


def _iter_project_files(project: Path) -> Iterable[Path]:
    for path in sorted(project.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative_parts = path.relative_to(project).parts
        if any(part in SKIP_DIRS or part.startswith(".") for part in relative_parts[:-1]):
            continue
        if path.suffix.casefold() in TEXT_SUFFIXES:
            yield path


def _iter_all_project_files(project: Path) -> Iterable[Path]:
    for path in sorted(project.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative_parts = path.relative_to(project).parts
        if any(part in SKIP_DIRS or part.startswith(".") for part in relative_parts[:-1]):
            continue
        yield path


def _scan_text_files(project: Path) -> tuple[list[tuple[Path, str]], int, list[str]]:
    files: list[tuple[Path, str]] = []
    scanned_bytes = 0
    warnings: list[str] = []
    for path in _iter_project_files(project):
        try:
            size = path.stat().st_size
        except OSError as exc:
            warnings.append(f"Could not stat {path}: {exc}")
            continue
        if size > MAX_FILE_BYTES:
            warnings.append(f"Skipped large text file {path} ({size} bytes)")
            continue
        if scanned_bytes + size > MAX_SCAN_BYTES:
            warnings.append(
                f"Stopped scanning after {MAX_SCAN_BYTES} bytes; remaining files were not inspected"
            )
            break
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            warnings.append(f"Skipped unreadable text file {path}: {exc}")
            continue
        files.append((path, text))
        scanned_bytes += size
    return files, scanned_bytes, warnings


def scan_project(project: str | Path) -> dict[str, Any]:
    """Return bounded static evidence used to choose conservative build flags."""

    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Project directory does not exist: {root}")
    project_file = root / "project.godot"
    if not project_file.is_file():
        raise ValueError(f"Godot project.godot was not found below {root}")

    files, scanned_bytes, warnings = _scan_text_files(root)
    combined = "\n".join(text for _, text in files)
    project_text = project_file.read_text(encoding="utf-8", errors="replace")
    version_match = _FEATURES_RE.search(project_text)
    version = version_match.group(1) if version_match else None
    renderer_match = _RENDERER_RE.search(project_text)
    renderer = _normalise_renderer(renderer_match.group(1) if renderer_match else None)
    evidence: dict[str, list[str]] = {}
    signals: dict[str, bool] = {}
    for feature, patterns in _FEATURE_PATTERNS.items():
        matches: list[str] = []
        for pattern in patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                matches.append(pattern)
        signals[feature] = bool(matches)
        if matches:
            evidence[feature] = matches
    suffixes = {path.suffix.casefold() for path in _iter_all_project_files(root)}
    signals["svg"] = ".svg" in suffixes
    signals["webp"] = ".webp" in suffixes
    signals["non_latin_text"] = bool(_NON_LATIN_RE.search(combined))
    if signals["non_latin_text"]:
        evidence["non_latin_text"] = ["non-ASCII script ranges requiring advanced text support"]
    signals["3d"] = signals["3d"] or signals["3d_physics"]
    signals["text"] = (
        signals["text"]
        or signals["non_latin_text"]
        or bool({".ttf", ".otf", ".woff", ".woff2"}.intersection(suffixes))
    )
    return {
        "project": str(root),
        "godot_version": version,
        "renderer": renderer,
        "files_scanned": len(files),
        "bytes_scanned": scanned_bytes,
        "signals": signals,
        "evidence": evidence,
        "warnings": warnings,
    }


def _validate_force(force: Sequence[str]) -> set[str]:
    forced = {item.casefold() for item in force}
    unknown = sorted(forced - FORCE_FEATURES)
    if unknown:
        raise ValueError(f"Unknown --force feature(s): {', '.join(unknown)}")
    return forced


def _module_options(signals: Mapping[str, bool], forced: set[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    if signals.get("3d_physics") or "3d" in forced:
        options["module_godot_physics_3d_enabled"] = "yes"
    if signals.get("2d_physics"):
        options["module_godot_physics_2d_enabled"] = "yes"
    if signals.get("text") or "advanced-text" in forced:
        if signals.get("non_latin_text") or "advanced-text" in forced:
            options["module_text_server_adv_enabled"] = "yes"
        else:
            options["module_text_server_fb_enabled"] = "yes"
        options["module_freetype_enabled"] = "yes"
    if signals.get("svg"):
        options["module_svg_enabled"] = "yes"
    if signals.get("webp"):
        options["module_webp_enabled"] = "yes"
    if signals.get("navigation") or "navigation" in forced:
        options.update(
            {
                "module_navigation_2d_enabled": "yes",
                "module_navigation_3d_enabled": "yes",
            }
        )
    if signals.get("zip") or "zip" in forced:
        options["module_zip_enabled"] = "yes"
    return options


def _disabled_options(options: Mapping[str, str]) -> dict[str, bool]:
    excluded = {"target", "debug_symbols", "optimize", "lto", "platform", "arch"}
    result: dict[str, bool] = {}
    for name, value in options.items():
        if name in excluded or name == "modules_enabled_by_default":
            continue
        if value == "no":
            result[name] = False
        elif value == "yes" and name.startswith("disable_"):
            result[name] = True
    return result


def make_plan(
    scan: Mapping[str, Any],
    *,
    godot_version: str | None = None,
    target: str = "windows",
    renderer: str | None = None,
    minimal_modules: bool = False,
    force: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a deterministic profile plan without writing project files."""

    forced = _validate_force(force)
    version = godot_version or str(scan.get("godot_version") or "") or None
    detected_renderer = _normalise_renderer(renderer) or _normalise_renderer(scan.get("renderer"))
    signals = scan.get("signals", {})
    options: dict[str, str] = {
        "target": "template_release",
        "debug_symbols": "no",
        "optimize": "size_extra" if _is_at_least(version, 4, 5) else "size",
        "lto": "full",
    }
    withheld: dict[str, str] = {}

    if not signals.get("3d") and "3d" not in forced:
        options["disable_3d"] = "yes"
    else:
        withheld["disable_3d"] = "3D evidence or --force 3d"
    if not signals.get("advanced_gui") and "advanced-gui" not in forced:
        options["disable_advanced_gui"] = "yes"
    else:
        withheld["disable_advanced_gui"] = "advanced GUI evidence or --force advanced-gui"
    if signals.get("text") and not signals.get("non_latin_text") and "advanced-text" not in forced:
        options.update(
            {
                "module_text_server_adv_enabled": "no",
                "module_text_server_fb_enabled": "yes",
                "graphite": "no",
            }
        )
    elif signals.get("text"):
        withheld["fallback_text_server"] = "non-Latin text evidence or --force advanced-text"
    if detected_renderer == "compatibility" and "vulkan" not in forced:
        options.update({"vulkan": "no", "use_volk": "no"})
    elif detected_renderer != "compatibility":
        withheld["vulkan"] = "renderer is not confirmed as Compatibility"
    if not signals.get("xr") and "xr" not in forced:
        if _is_at_least(version, 4, 5):
            options["disable_xr"] = "yes"
        else:
            options["openxr"] = "no"
    else:
        withheld["disable_xr"] = "XR evidence or --force xr"
    if not signals.get("zip") and "zip" not in forced:
        options["minizip" if not _is_at_least(version, 4, 5) else "module_zip_enabled"] = "no"
    else:
        withheld["zip"] = "ZIP API/archive evidence or --force zip"
    if _is_at_least(version, 4, 5):
        if not signals.get("navigation") and "navigation" not in forced:
            options.update({"disable_navigation_2d": "yes", "disable_navigation_3d": "yes"})
        else:
            withheld["navigation"] = "navigation evidence or --force navigation"
        if "accesskit" not in forced:
            options["accesskit"] = "no"
        if (
            "graphite" not in options
            and "graphite" not in forced
            and "advanced-text" not in forced
            and not signals.get("non_latin_text")
        ):
            options["graphite"] = "no"
    if minimal_modules or "minimal-modules" in forced:
        options["modules_enabled_by_default"] = "no"
        for name, value in _module_options(signals, forced).items():
            options[name] = value

    recommendations = [
        "Compile with the same Godot source version as the project and matching export templates.",
        (
            "Export from a clean staging directory, launch the packaged artifact, and inspect "
            "startup logs before accepting the size change."
        ),
        "Static scanning cannot see reflection, dynamically loaded resources, or every "
        "GDExtension dependency.",
    ]
    if minimal_modules or "minimal-modules" in forced:
        recommendations.append(
            "Minimal module mode is high risk; add back every module required by runtime "
            "smoke tests before release."
        )
    if target == "windows":
        recommendations.append(
            "UPX is optional post-processing: verify antivirus acceptance, memory use, and "
            "startup before sharing a packed executable."
        )
    if target == "web":
        recommendations.extend(
            [
                "wasm-opt may reduce the uncompressed WebAssembly file; measure the final "
                "archive because ZIP gains can be small.",
                "Use Brotli only when the production server sends the documented "
                "Content-Encoding and MIME headers.",
            ]
        )
    return {
        "schema_version": 1,
        "project": scan["project"],
        "target": target,
        "platform": TARGET_PLATFORMS[target],
        "godot_version": version,
        "renderer": detected_renderer,
        "scan": dict(scan),
        "options": options,
        "disabled_build_options": _disabled_options(options),
        "withheld": withheld,
        "recommendations": recommendations,
    }


def _profile_text(options: Mapping[str, str], report_path: str) -> str:
    lines = [
        "# Generated by dcc-mcp-godot godot-build-optimization.",
        "# Re-run the plan after changing project features or Godot source version.",
        f"# Evidence report: {report_path}",
        "",
    ]
    for name, value in options.items():
        lines.append(f"{name} = {value!r}")
    lines.append("")
    return "\n".join(lines)


def write_plan(plan: Mapping[str, Any], output: str | Path) -> dict[str, str]:
    """Write the SCons profile, build profile, and evidence report."""

    output_dir = Path(output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "optimization-report.json"
    profile_path = output_dir / "custom.py"
    build_profile_path = output_dir / "build_config.gdbuild"
    report = dict(plan)
    report["outputs"] = {
        "profile": str(profile_path),
        "build_profile": str(build_profile_path),
        "report": str(report_path),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    profile_path.write_text(
        _profile_text(plan["options"], str(report_path)), encoding="utf-8", newline="\n"
    )
    build_profile = {
        "disabled_build_options": plan["disabled_build_options"],
        "disabled_classes": [],
        "type": "build_profile",
    }
    build_profile_path.write_text(
        json.dumps(build_profile, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "profile": str(profile_path),
        "build_profile": str(build_profile_path),
        "report": str(report_path),
    }


def _hash_path(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    if path.is_file():
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                total += len(chunk)
                digest.update(chunk)
        return total, digest.hexdigest()
    if not path.is_dir():
        raise ValueError(f"Artifact does not exist: {path}")
    for child in sorted(path.rglob("*")):
        if not child.is_file() or child.is_symlink():
            continue
        relative = child.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        size, child_hash = _hash_path(child)
        total += size
        digest.update(bytes.fromhex(child_hash))
    return total, digest.hexdigest()


def measure_artifacts(
    artifacts: Sequence[str | Path], baseline: str | Path | None = None
) -> dict[str, Any]:
    """Return reproducible byte counts and SHA-256 digests for exported artifacts."""

    rows = []
    for raw_path in artifacts:
        path = Path(raw_path).expanduser().resolve()
        size, digest = _hash_path(path)
        rows.append({"path": str(path), "bytes": size, "sha256": digest})
    result: dict[str, Any] = {
        "schema_version": 1,
        "artifacts": rows,
        "total_bytes": sum(row["bytes"] for row in rows),
    }
    if baseline is not None:
        baseline_data = json.loads(Path(baseline).read_text(encoding="utf-8"))
        previous = baseline_data.get("total_bytes")
        if isinstance(previous, int):
            result["baseline_total_bytes"] = previous
            result["delta_bytes"] = result["total_bytes"] - previous
    return result


def _add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True, type=Path, help="Godot project directory")
    parser.add_argument(
        "--godot-version",
        help="Engine version (for example 4.5); inferred from project.godot when omitted",
    )
    parser.add_argument("--target", choices=sorted(TARGET_PLATFORMS), default="windows")
    parser.add_argument(
        "--renderer",
        choices=["auto", "compatibility", "forward_plus", "mobile"],
        default="auto",
    )
    parser.add_argument(
        "--minimal-modules",
        action="store_true",
        help="Allowlist detected modules; use only with runtime smoke coverage",
    )
    parser.add_argument(
        "--force",
        action="append",
        default=[],
        choices=sorted(FORCE_FEATURES),
        help="Keep a feature enabled despite static evidence (repeatable)",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan", help="Scan and print a build-size plan")
    _add_project_args(plan_parser)
    generate_parser = subparsers.add_parser("generate", help="Write profile and build config files")
    _add_project_args(generate_parser)
    generate_parser.add_argument("--output", required=True, type=Path)
    measure_parser = subparsers.add_parser(
        "measure", help="Measure exported artifact files or directories"
    )
    measure_parser.add_argument("--artifact", action="append", required=True, type=Path)
    measure_parser.add_argument("--baseline", type=Path)
    measure_parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "measure":
            result = measure_artifacts(args.artifact, args.baseline)
            encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
            if args.output:
                output = args.output.expanduser().resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(encoded, encoding="utf-8")
            print(encoded, end="")
            return 0
        scan = scan_project(args.project)
        plan = make_plan(
            scan,
            godot_version=args.godot_version,
            target=args.target,
            renderer=args.renderer,
            minimal_modules=args.minimal_modules,
            force=args.force,
        )
        if args.command == "plan":
            print(json.dumps(plan, indent=2, sort_keys=True))
        else:
            outputs = write_plan(plan, args.output)
            print(json.dumps({"plan": plan, "outputs": outputs}, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"godot-build-optimization: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
