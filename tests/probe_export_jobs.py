"""Hosted candidate-only real MCP export lifecycle and Web startup acceptance."""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import importlib.metadata
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

from live_godot_smoke import _mcp_post, _tool_context


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def run(godot, template, output, wheel, commit):
    output.mkdir(parents=True, exist_ok=False)
    project = output / "project"
    project.mkdir()
    session = output / "session"
    for name in ("home", "cache", "config", "data", "registry"):
        (session / name).mkdir(parents=True)
    os.environ.update(
        HOME=str(session / "home"),
        XDG_CACHE_HOME=str(session / "cache"),
        XDG_CONFIG_HOME=str(session / "config"),
        XDG_DATA_HOME=str(session / "data"),
        DCC_MCP_REGISTRY_DIR=str(session / "registry"),
        DCC_MCP_CLI_NO_AUTO_GATEWAY="true",
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    os.environ.update(
        DCC_MCP_GODOT_BRIDGE_PORT=str(port), DCC_MCP_GODOT_BRIDGE_URL=f"ws://127.0.0.1:{port}"
    )
    import dcc_mcp_godot
    from dcc_mcp_godot.bridge import get_bridge
    from dcc_mcp_godot.server import GodotMcpServer

    clean = """config_version=5
[application]
config/name="Observable export fixture"
run/main_scene="res://main.tscn"
[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
"""
    (project / "main.gd").write_text("""extends Node2D
var frames := 0
func _process(_delta: float) -> void:
 frames += 1
 if OS.has_feature("web"):
  JavaScriptBridge.eval("window.exportJobFrames=" + str(frames))
func _draw() -> void:
 draw_rect(Rect2(20,20,200,120), Color(0.1,0.8,0.5))
""")
    (project / "main.tscn").write_text("""[gd_scene load_steps=2 format=3]
[ext_resource type="Script" path="res://main.gd" id="1"]
[node name="ExportFixture" type="Node2D"]
script = ExtResource("1")
""")
    (project / "export_presets.cfg").write_text(
        """[preset.0]
name="Web"
platform="Web"
runnable=true
export_filter="all_resources"
exclude_filter="addons/*,export_probe.gd,web-*/*"
script_export_mode=2
[preset.0.options]
variant/extensions_support=false
variant/thread_support=false
vram_texture_compression/for_desktop=true
vram_texture_compression/for_mobile=false
custom_template/release="""
        + json.dumps(str(template))
        + "\n"
    )
    shutil.copytree(Path(dcc_mcp_godot.__file__).parent / "godot_addon/addons", project / "addons")
    (project / "project.godot").write_text(
        clean
        + '\n[editor_plugins]\nenabled=PackedStringArray("res://addons/dcc_mcp_godot/plugin.cfg")\n'
    )
    (project / "export_probe.gd").write_text("""@tool
extends RefCounted
func inspect(_arguments: Dictionary) -> Dictionary:
 return {"scanning":EditorInterface.get_resource_filesystem().is_scanning(),
  "frame":Engine.get_process_frames()}
func prepare(arguments: Dictionary) -> Dictionary:
 var f := FileAccess.open("res://project.godot", FileAccess.WRITE)
 if f == null: return {"error":"Cannot save clean configuration"}
 f.store_string(String(arguments.source))
 f.close()
 return {"sha256":FileAccess.get_sha256("res://project.godot")}
""")
    receipts = []
    names = {}
    report = {
        "passed": False,
        "candidate_commit": commit,
        "candidate_wheel_sha256": sha(wheel),
        "adapter_version": importlib.metadata.version("dcc-mcp-godot"),
        "core_version": importlib.metadata.version("dcc-mcp-core"),
        "engine_sha256": sha(godot),
        "template_sha256": sha(template),
        "scope": "isolated fixture, not Showcase game acceptance",
    }
    server = None
    editor = None
    log = (output / "editor.log").open("w")

    def rpc(method, params):
        request = {"method": method, "params": params}
        try:
            response = _mcp_post(server.mcp_url, method, params)
        except Exception as error:
            receipts.append({"request": request, "transport_error": str(error)})
            write(output / "mcp-receipts.json", receipts)
            raise
        receipts.append({"request": request, "response": response})
        write(output / "mcp-receipts.json", receipts)
        if response.get("error") or response.get("result", {}).get("isError"):
            raise RuntimeError(str(response))
        return response

    def inventory():
        cursor = None
        for _ in range(20):
            result = rpc("tools/list", {"cursor": cursor} if cursor else {})["result"]
            names.update({tool["name"]: tool for tool in result["tools"]})
            cursor = result.get("nextCursor")
            if not cursor:
                return
        raise RuntimeError("Tool inventory unbounded")

    def call(name, params):
        matches = [n for n in names if n == name or n.endswith("__" + name)]
        assert len(matches) == 1, (name, matches)
        return _tool_context(rpc("tools/call", {"name": matches[0], "arguments": params}))

    def poll(identifier):
        deadline = time.monotonic() + 660
        while time.monotonic() < deadline:
            result = call("get_export_job", {"job_id": identifier})
            if result["status"] not in ("queued", "running"):
                return result
            assert editor.poll() is None
            time.sleep(0.25)
        raise TimeoutError("Export job did not reach observable terminal state; do not replay")

    try:
        server = GodotMcpServer(
            port=0,
            gateway_port=0,
            registry_dir=str(session / "registry"),
            enable_gateway_failover=False,
            enable_telemetry=False,
            enable_checkpoint_persistence=False,
        )
        server.register_builtin_actions()
        server.start(install_atexit_hook=False)
        editor = subprocess.Popen(
            [str(godot), "--headless", "--editor", "--path", str(project)],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        deadline = time.monotonic() + 90
        while not get_bridge().is_connected():
            assert editor.poll() is None and time.monotonic() < deadline
            time.sleep(0.1)
        inventory()
        call("load_skill", {"skill_names": ["godot-export", "godot-script"]})
        inventory()
        previous = None
        while True:
            sample = call(
                "execute_editor_script",
                {
                    "path": "res://export_probe.gd",
                    "method": "inspect",
                    "arguments": {},
                    "budget_ms": 50,
                    "chunked": False,
                },
            )["result"]
            if sample["scanning"] is False:
                if previous is not None and sample["frame"] >= previous["frame"] + 2:
                    break
                if previous is None:
                    previous = sample
            else:
                previous = None
            assert editor.poll() is None and time.monotonic() < deadline
            time.sleep(0.1)
        prepared = call(
            "execute_editor_script",
            {
                "path": "res://export_probe.gd",
                "method": "prepare",
                "arguments": {"source": clean},
                "budget_ms": 50,
                "chunked": False,
            },
        )
        assert prepared["result"]["sha256"] == hashlib.sha256(clean.encode()).hexdigest()
        assert (project / "project.godot").read_bytes() == clean.encode()
        first = call(
            "start_export_job",
            {
                "request_id": "a" * 32,
                "preset": "Web",
                "path": "web-cancel/index.html",
                "timeout_seconds": 600,
            },
        )
        assert first["job_id"] == "a" * 32
        running = first
        running_deadline = time.monotonic() + 30
        while running["status"] == "queued":
            if time.monotonic() >= running_deadline:
                raise TimeoutError("Known export ID did not start in 30s; preserve, never resubmit")
            time.sleep(0.1)
            running = call("get_export_job", {"job_id": "a" * 32})
        assert running["status"] == "running" and running["pid"] > 0
        cancelled = call("cancel_export_job", {"job_id": "a" * 32})
        if cancelled["status"] in ("queued", "running"):
            cancelled = poll("a" * 32)
        report["cancel"] = cancelled
        assert cancelled["child_reaped"] and cancelled["descendant_cleanup_confirmed"]
        assert cancelled["status"] == "cancelled" and not cancelled["artifacts_accepted"]
        second = call(
            "start_export_job",
            {
                "request_id": "b" * 32,
                "preset": "Web",
                "path": "web-complete/index.html",
                "timeout_seconds": 600,
            },
        )
        assert second["job_id"] == "b" * 32
        result = poll("b" * 32)
        report["export"] = result
        assert result["status"] == "completed" and result["exit_code"] == 0
        assert result["child_reaped"] and result["descendant_cleanup_confirmed"]
        assert result["log_complete"] and result["artifacts_accepted"]
        assert sha(Path(result["log_path"])) == result["log_sha256"]
        assert sha(Path(result["output_manifest_path"])) == result["output_manifest_sha256"]
        manifest = json.loads(Path(result["output_manifest_path"]).read_text())
        web = project / "web-complete"
        for item in manifest["files"]:
            path = web / item["path"]
            assert path.stat().st_size == item["bytes"] and sha(path) == item["sha256"]
        assert (project / "project.godot").read_bytes() == clean.encode()
        export_log = Path(result["log_path"]).read_text()
        assert "ERROR:" not in export_log and "SCRIPT ERROR:" not in export_log
        report["pck"] = inspect_clean_pck(web / "index.pck")
        log.flush()
        assert "ERROR:" not in (output / "editor.log").read_text()
        report["browser"] = browser(web, output)
        report["passed"] = True
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        try:
            if server is not None:
                server.stop()
        except Exception as error:
            report.update(passed=False, cleanup_error=str(error))
            raise
        finally:
            try:
                if editor is not None:
                    editor.terminate()
                    try:
                        editor.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        editor.kill()
                        editor.wait(timeout=5)
            except Exception as error:
                report.update(passed=False, editor_cleanup_error=str(error))
                raise
            finally:
                log.close()
                report["editor_exit"] = editor.returncode if editor else None
                write(output / "report.json", report)


def inspect_clean_pck(path):
    """Read v2/v3 standalone PCK index per Godot 4.6.3 file_access_pack.cpp."""
    import struct

    entries = []
    total = path.stat().st_size
    with path.open("rb") as stream:

        def take(n):
            b = stream.read(n)
            if len(b) != n:
                raise ValueError("Truncated PCK index")
            return b

        def u32():
            return struct.unpack("<I", take(4))[0]

        def u64():
            return struct.unpack("<Q", take(8))[0]

        if take(4) != b"GDPC":
            raise ValueError("Not standalone Godot PCK")
        version = u32()
        engine = (u32(), u32(), u32())
        flags = u32()
        base = u64()
        if version not in (2, 3) or engine != (4, 6, 3) or flags not in (0, 2):
            raise ValueError("Unexpected PCK format/engine/flags")
        if version == 3:
            offset = u64()
            if not 40 <= offset < total:
                raise ValueError("Invalid PCK directory offset")
            stream.seek(offset)
        else:
            take(64)
        count = u32()
        if not 1 <= count <= 10000:
            raise ValueError("Unexpected PCK entry count")
        for _ in range(count):
            n = u32()
            if not 1 <= n <= 4096:
                raise ValueError("Invalid PCK path size")
            name = take(n).rstrip(b"\0").decode("utf-8")
            offset = u64() + base
            size = u64()
            digest = take(16)
            entry_flags = u32()
            if entry_flags != 0 or offset + size > total:
                raise ValueError("Unsupported or out-of-bounds PCK entry")
            if any(
                x in name.lower() for x in ("addons/", "dcc_mcp", "export_probe", "web-complete/")
            ):
                raise ValueError("Control/export artifact entered PCK: " + name)
            entries.append((name, offset, size, digest))
        configs = [
            x
            for x in entries
            if x[0]
            in ("res://project.binary", "project.binary", "res://project.godot", "project.godot")
        ]
        if len(configs) != 1:
            raise ValueError("Expected one exported project configuration")
        name, offset, size, digest = configs[0]
        if size > 1024 * 1024:
            raise ValueError("Unexpected configuration size")
        stream.seek(offset)
        config = take(size)
        if hashlib.md5(config).digest() != digest:
            raise ValueError("PCK project configuration digest mismatch")
        if any(
            x in config.lower()
            for x in (b"dcc_mcp", b"dccmcpruntimepeer", b"export_probe", b"addons/")
        ):
            raise ValueError("Control addon/autoload entered PCK configuration")
    return {
        "format": version,
        "engine": engine,
        "entries": [x[0] for x in entries],
        "project_configuration": name,
        "project_configuration_sha256": hashlib.sha256(config).hexdigest(),
        "pck_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def browser(web, output):
    from playwright.sync_api import sync_playwright

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(web))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            chrome = playwright.chromium.launch(
                executable_path="/opt/google/chrome/chrome", headless=True, chromium_sandbox=True
            )
            try:
                page = chrome.new_page(viewport={"width": 640, "height": 360})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "console",
                    lambda message: (
                        errors.append(message.text) if message.type == "error" else None
                    ),
                )
                page.goto(f"http://127.0.0.1:{httpd.server_port}/index.html")
                page.wait_for_function("window.exportJobFrames >= 3", timeout=90000)
                frames = page.evaluate("window.exportJobFrames")
                page.screenshot(path=str(output / "browser.png"))
                assert not errors, errors
                return {"frames": frames, "page_errors": errors, "browser": chrome.version}
            finally:
                chrome.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("godot", "template", "output", "wheel"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    run(
        args.godot.resolve(),
        args.template.resolve(),
        args.output.resolve(),
        args.wheel.resolve(),
        args.commit,
    )
