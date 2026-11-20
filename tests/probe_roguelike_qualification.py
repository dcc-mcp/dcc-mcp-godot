"""Qualify the generated roguelike through native, desktop, and Web lanes."""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot/templates/roguelike"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run_command(
    command: list[str], log_path: Path, timeout: int
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    return result


def browser_executable(explicit: Path | None) -> str | None:
    if explicit is not None:
        return str(explicit.resolve())
    configured = os.environ.get("DCC_MCP_BROWSER_EXECUTABLE")
    if configured:
        return str(Path(configured).resolve())
    candidates = [
        "/opt/google/chrome/chrome",
        "/usr/bin/google-chrome",
        os.path.join(
            os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"
        ),
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"
        ),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    for name in ("google-chrome", "chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def project_files(
    project: Path,
    desktop_platform: str,
    desktop_preset: str,
    desktop_template: Path | None,
    web_template: Path | None,
) -> None:
    roguelike = project / "roguelike"
    roguelike.mkdir(parents=True)
    for name in ("main.tscn", "game.gd", "ci_smoke.gd"):
        shutil.copy2(TEMPLATE / name, roguelike / name)
    project.joinpath("project.godot").write_text(
        """config_version=5

[application]
config/name="DCC-MCP Roguelike Qualification"
run/main_scene="res://roguelike/main.tscn"

[display]
window/size/viewport_width=960
window/size/viewport_height=540
window/size/window_width_override=960
window/size/window_height_override=540

[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
""",
        encoding="utf-8",
    )
    web_template_value = json.dumps(str(web_template.resolve())) if web_template else '""'
    desktop_template_value = (
        json.dumps(str(desktop_template.resolve())) if desktop_template else '""'
    )
    project.joinpath("export_presets.cfg").write_text(
        f"""[preset.0]
name="{desktop_preset}"
platform="{desktop_platform}"
runnable=true
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path=""
script_export_mode=2

[preset.0.options]
custom_template/release={desktop_template_value}

[preset.1]
name="Web"
platform="Web"
runnable=true
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path=""
script_export_mode=2

[preset.1.options]
variant/extensions_support=false
variant/thread_support=false
vram_texture_compression/for_desktop=true
vram_texture_compression/for_mobile=false
custom_template/release={web_template_value}
""",
        encoding="utf-8",
    )


def browser_lane(web: Path, output: Path, explicit_browser: Path | None) -> dict[str, object]:
    from playwright.sync_api import sync_playwright

    def handler(*args, **kwargs):
        return http.server.SimpleHTTPRequestHandler(*args, directory=str(web), **kwargs)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=browser_executable(explicit_browser),
                headless=True,
                chromium_sandbox=os.name != "nt",
            )
            try:
                page = browser.new_page(viewport={"width": 960, "height": 540})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "console",
                    lambda message: (
                        errors.append(message.text) if message.type == "error" else None
                    ),
                )
                page.goto(f"http://127.0.0.1:{server.server_port}/index.html")
                page.wait_for_function(
                    "window.dccRoguelikeState && window.dccRoguelikeState.elapsed > 0.2"
                )
                initial = page.evaluate("window.dccRoguelikeState")
                page.keyboard.down("ArrowRight")
                page.wait_for_timeout(250)
                page.keyboard.up("ArrowRight")
                moved = page.evaluate("window.dccRoguelikeState")
                if moved["player_x"] <= initial["player_x"]:
                    raise AssertionError(f"Web input did not move player: {initial} -> {moved}")
                page.keyboard.down("Space")
                page.wait_for_timeout(250)
                page.keyboard.up("Space")
                page.wait_for_function("window.dccRoguelikeState.auto_fire_enabled === false")
                disabled = page.evaluate("window.dccRoguelikeState")
                page.evaluate("window.dispatchEvent(new Event('blur'))")
                page.bring_to_front()
                page.keyboard.down("ArrowLeft")
                page.wait_for_timeout(250)
                page.keyboard.up("ArrowLeft")
                recovered_focus = page.evaluate("window.dccRoguelikeState")
                if recovered_focus["player_x"] >= moved["player_x"]:
                    raise AssertionError("Web input did not recover after focus restoration")
                page.wait_for_function(
                    "window.dccRoguelikeState && window.dccRoguelikeState.game_over",
                    timeout=30000,
                )
                failed = page.evaluate("window.dccRoguelikeState")
                page.keyboard.press("Space")
                page.wait_for_function(
                    "window.dccRoguelikeState && "
                    "window.dccRoguelikeState.restart_count >= 1 && "
                    "!window.dccRoguelikeState.game_over"
                )
                restarted = page.evaluate("window.dccRoguelikeState")
                if restarted["restart_count"] < 1 or restarted["game_over"]:
                    raise AssertionError(f"Web restart state was not observed: {restarted}")
                page.screenshot(path=str(output / "web-browser.png"))
                return {
                    "browser": browser.version,
                    "initial": initial,
                    "moved": moved,
                    "auto_fire_disabled": disabled,
                    "focus_recovered": recovered_focus,
                    "failed": failed,
                    "restarted": restarted,
                    "audio": "not_applicable_no_audio_track_declared",
                    "page_errors": errors,
                    "input_steps": [
                        "ArrowRight down/up moved the player",
                        "Space toggled automatic firing off",
                        "page blur and front restoration preceded ArrowLeft input",
                        "natural enemy contact reached game over",
                        "Space restarted the game after failure",
                    ],
                }
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run(args: argparse.Namespace) -> dict[str, object]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    project = output / "project"
    project.mkdir()
    project_files(
        project,
        args.desktop_platform,
        args.desktop_preset,
        args.desktop_template,
        args.web_template,
    )
    engine_version = subprocess.run(
        [str(args.godot), "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    report: dict[str, object] = {
        "passed": False,
        "contract": "godot-roguelike-qualification-v1",
        "engine_version": engine_version,
        "engine_sha256": sha256(args.godot),
        "template_sha256": {
            name: sha256(TEMPLATE / name) for name in ("main.tscn", "game.gd", "ci_smoke.gd")
        },
        "desktop_preset": args.desktop_preset,
        "desktop_template": str(args.desktop_template)
        if args.desktop_template
        else "installed-by-engine",
        "web_template": str(args.web_template) if args.web_template else "installed-by-engine",
        "scope": "clean generated asset-free roguelike fixture",
    }
    if args.desktop_template:
        report["desktop_template_sha256"] = sha256(args.desktop_template)
    if args.web_template:
        report["web_template_sha256"] = sha256(args.web_template)
    try:
        first_editor = run_command(
            [
                str(args.godot),
                "--headless",
                "--editor",
                "--path",
                str(project),
                "--quit-after",
                "2",
            ],
            output / "editor-first.log",
            60,
        )
        if first_editor.returncode != 0:
            raise RuntimeError("first editor import failed")
        second_editor = run_command(
            [
                str(args.godot),
                "--headless",
                "--editor",
                "--path",
                str(project),
                "--quit-after",
                "2",
            ],
            output / "editor-reopen.log",
            60,
        )
        if second_editor.returncode != 0:
            raise RuntimeError("editor reopen failed")
        project_text = (project / "project.godot").read_text(encoding="utf-8")
        if 'run/main_scene="res://roguelike/main.tscn"' not in project_text:
            raise RuntimeError("reopened project lost its main scene reference")
        native = run_command(
            [
                str(args.godot),
                "--headless",
                "--path",
                str(project),
                "--script",
                "res://roguelike/ci_smoke.gd",
            ],
            output / "native-gameplay.log",
            90,
        )
        if native.returncode != 0 or "ROGUELIKE_SMOKE_OK" not in native.stdout + native.stderr:
            raise RuntimeError("native gameplay qualification failed")
        report["native"] = {"status": "passed", "log": "native-gameplay.log"}

        desktop = output / ("desktop.exe" if os.name == "nt" else "desktop.x86_64")
        desktop_export = run_command(
            [
                str(args.godot),
                "--headless",
                "--path",
                str(project),
                "--export-release",
                args.desktop_preset,
                str(desktop),
            ],
            output / "desktop-export.log",
            180,
        )
        if desktop_export.returncode != 0 or not desktop.is_file() or desktop.stat().st_size == 0:
            raise RuntimeError("desktop export failed or produced no artifact")
        desktop_run = run_command(
            [str(desktop), "--headless", "--quit-after", "2"],
            output / "desktop-runtime.log",
            30,
        )
        if (
            desktop_run.returncode != 0
            or "ROGUELIKE_READY" not in desktop_run.stdout + desktop_run.stderr
        ):
            raise RuntimeError("desktop artifact did not launch the generated scene")
        report["desktop"] = {
            "status": "passed",
            "artifact": str(desktop),
            "sha256": sha256(desktop),
            "log": "desktop-runtime.log",
        }

        web = output / "web"
        web.mkdir()
        web_export = run_command(
            [
                str(args.godot),
                "--headless",
                "--path",
                str(project),
                "--export-release",
                "Web",
                str(web / "index.html"),
            ],
            output / "web-export.log",
            180,
        )
        if web_export.returncode != 0 or not (web / "index.html").is_file():
            raise RuntimeError("Web export failed or produced no index.html")
        report["web"] = browser_lane(web, output, args.browser)
        report["web"]["artifact_sha256"] = {  # type: ignore[index]
            str(path.relative_to(web)): sha256(path)
            for path in sorted(web.rglob("*"))
            if path.is_file()
        }
        report["passed"] = True
        return report
    finally:
        report["project_files"] = {
            str(path.relative_to(project)): sha256(path)
            for path in sorted(project.rglob("*"))
            if path.is_file()
        }
        report["project_godot_sha256"] = sha256(project / "project.godot")
        write_json(output / "report.json", report)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--desktop-preset", default="Windows Desktop")
    parser.add_argument("--desktop-platform", default="Windows Desktop")
    parser.add_argument("--desktop-template", type=Path)
    parser.add_argument("--web-template", type=Path)
    parser.add_argument("--browser", type=Path)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
