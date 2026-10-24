"""Real HTTP typed MCP input authoring, failed-save rollback and fresh-engine readback."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(godot, out, budget_roots=(), max_bytes=0):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "runtime"
    if work.exists():
        raise RuntimeError("Refusing to reuse an existing runtime directory")
    work.mkdir()
    addon = ROOT / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot"
    uid_before = set(addon.rglob("*.uid"))
    for name in ("XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
        folder = work / name.lower()
        folder.mkdir()
        os.environ[name] = str(folder)
    os.environ.update(
        GODOT_SILENCE_ROOT_WARNING="1",
        DCC_MCP_REGISTRY_DIR=str(work / "registry"),
        DCC_MCP_LOG_DIR=str(work / "logs"),
        DCC_MCP_JOB_DIR=str(work / "jobs"),
        DCC_MCP_LOG_LEVEL="WARN",
    )
    bridge_port = free_port()
    os.environ["DCC_MCP_GODOT_BRIDGE_PORT"] = str(bridge_port)
    os.environ["DCC_MCP_GODOT_BRIDGE_URL"] = f"ws://127.0.0.1:{bridge_port}"
    sys.path.insert(0, str(ROOT / "src"))
    from dcc_mcp_godot import bridge
    from dcc_mcp_godot.server import GodotMcpServer

    (work / "addons").mkdir()
    (work / "addons/dcc_mcp_godot").symlink_to(addon, target_is_directory=True)
    project = work / "project.godot"
    project.write_text(
        'config_version=5\n[application]\nconfig/name="Input action contract"\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
        '[editor_plugins]\nenabled=PackedStringArray("res://addons/dcc_mcp_godot/plugin.cfg")\n',
        encoding="utf-8",
    )
    shutil.copyfile(ROOT / "tests/godot_project/input_action_fixture.gd", work / "fixture.gd")
    result = {
        "passed": False,
        "checks": 0,
        "scope": "real HTTP typed MCP editor, actual save failure, reopen, fresh game InputMap",
        "versions": {
            "core": importlib.metadata.version("dcc-mcp-core"),
            "mcp": importlib.metadata.version("mcp"),
            "python": sys.version.split()[0],
        },
        "source_sha256": hashlib.sha256((addon / "capabilities.gd").read_bytes()).hexdigest(),
        "calls": [],
    }
    process = None
    server = None
    logs = []
    stop = threading.Event()
    peak = 0
    exceeded = False

    monitor_error = None

    def size():
        total = 0
        for root in budget_roots:
            for directory, _, files in os.walk(root):
                for name in files:
                    try:
                        metadata = (Path(directory) / name).lstat()
                    except FileNotFoundError:
                        continue  # Godot can replace a temporary file between samples.
                    if stat.S_ISREG(metadata.st_mode):
                        total += metadata.st_size
        return total

    def monitor():
        nonlocal peak, exceeded, monitor_error
        while not stop.wait(0.1):
            try:
                peak = max(peak, size())
            except Exception as error:
                monitor_error = repr(error)
                if process and process.poll() is None:
                    process.terminate()
                return
            if max_bytes and peak > max_bytes:
                exceeded = True
                if process and process.poll() is None:
                    process.terminate()
                return

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()

    def check(condition, label):
        if not condition:
            raise AssertionError(label)
        result["checks"] += 1

    def rpc(method, params=None):
        payload = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params is not None:
            payload["params"] = params
        request = urllib.request.Request(
            server.mcp_url,
            data=json.dumps(payload).encode(),
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read())

    def payload(response):
        data = response.get("result", {})
        if "structuredContent" in data:
            return data["structuredContent"]
        if data.get("content"):
            text = data["content"][0]["text"]
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"message": text}
        return data

    names = {}

    def call(action, params, error=False):
        response = rpc("tools/call", {"name": names.get(action, action), "arguments": params})
        failed = bool(response.get("error") or response.get("result", {}).get("isError"))
        data = payload(response)
        check(failed == error, f"{action} expected error={error}: {response}")
        context = data.get("context", {})
        receipt = {"tool": action, "arguments": params, "isError": failed}
        if failed:
            receipt["error"] = data
        elif action == "get_input_actions":
            receipt["source"] = context["source"]
            receipt["actions"] = [x for x in context["actions"] if x["name"].startswith("dcc_")]
        else:
            receipt["context"] = context
        result["calls"].append(receipt)
        return context

    def launch(tag):
        nonlocal process
        log = (out / f"{tag}.log").open("wb")
        logs.append(log)
        process = subprocess.Popen(
            [godot, "--headless", "--editor", "--path", str(work)],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 25
        while not bridge.get_bridge().is_connected() and time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError("editor exited before bridge connection")
            time.sleep(0.1)
        check(bridge.get_bridge().is_connected(), "bridge connection")
        ready = False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    server.mcp_url.rsplit("/", 1)[0] + "/v1/readyz", timeout=2
                ) as response:
                    ready = response.status == 200
            except urllib.error.HTTPError as error:
                if error.code != 503:
                    raise
            if ready:
                break
            time.sleep(0.05)
        check(ready, "HTTP readiness synchronized after editor connection")

    def shutdown():
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        deadline = time.monotonic() + 5
        while bridge.get_bridge().is_connected() and time.monotonic() < deadline:
            time.sleep(0.05)
        check(not bridge.get_bridge().is_connected(), "editor disconnected after own shutdown")

    def native(mode):
        nonlocal process
        log = (out / f"{mode}.log").open("wb")
        logs.append(log)
        process = subprocess.Popen(
            [godot, "--headless", "--path", str(work), "--script", "res://fixture.gd", "--", mode],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        process.wait(timeout=25)
        check(process.returncode == 0, f"native {mode} exit")
        file = work / f"{mode}.json"
        check(file.exists(), f"native {mode} receipt (exit0 alone is insufficient)")
        data = json.loads(file.read_text(encoding="utf-8"))
        (out / file.name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return data

    def actions(source):
        return {x["name"]: x for x in call("get_input_actions", {"source": source})["actions"]}

    try:
        result["initial_bytes"] = size()
        check(not max_bytes or size() + 4_350_000 < max_bytes, "static resource estimate")
        before = native("setup")
        result["engine"] = before["engine"]
        validation = native("host_validation")
        check(validation["passed"], "host invalid-input assertions")
        result["native_validation_checks"] = validation["checks"]
        server = GodotMcpServer(
            port=0,
            gateway_port=free_port(),
            registry_dir=str(work / "registry"),
            enable_gateway_failover=False,
            strict_gateway=False,
            enable_file_logging=False,
            enable_job_persistence=False,
            enable_telemetry=False,
            enable_checkpoint_persistence=False,
            enable_checkpoint_tools=False,
        )
        server.register_builtin_actions()
        server.start(install_atexit_hook=False)
        launch("editor-create")
        rpc("tools/call", {"name": "load_skill", "arguments": {"skill_names": ["godot-input"]}})
        catalog = []
        cursor = None
        for _ in range(10):
            listing = rpc("tools/list", {"cursor": cursor} if cursor else {})["result"]
            catalog.extend(listing["tools"])
            cursor = listing.get("nextCursor")
            if not cursor:
                break
        check(not cursor, "bounded tools/list pagination")
        for action in ("set_input_action", "get_input_actions"):
            names[action] = next(
                t["name"]
                for t in catalog
                if t["name"] == action or t["name"].endswith("__" + action)
            )
        original_bytes = project.read_bytes()
        transient = call(
            "set_input_action",
            {"action": "dcc_input_mix", "keycode": 69, "deadzone": 0.75, "replace_events": True},
        )
        call("set_input_action", {"action": "dcc_unsaved", "keycode": 70})
        check(
            transient["source"] == "editor" and transient["persisted"] is False,
            "legacy editor scope explicit",
        )
        check(project.read_bytes() == original_bytes, "legacy does not save")
        default_project = call(
            "set_input_action", {"action": "dcc_default", "keycode": 65, "persist": True}
        )
        check(default_project["deadzone"] == 0.5, "new project action keeps legacy 0.5 default")
        implicit = call(
            "set_input_action", {"action": "dcc_implicit", "keycode": 32, "persist": True}
        )
        check(implicit["deadzone"] == 0.2, "missing existing deadzone follows native 0.2 default")
        editor_before = actions("editor")
        project_before = actions("project")
        check(editor_before["dcc_input_mix"]["deadzone"] == 0.75, "editor sentinel")
        check(project_before["dcc_input_mix"]["deadzone"] == 0.25, "project distinct from editor")
        check("dcc_unsaved" not in project_before, "editor-only not copied")
        fresh = call(
            "set_input_action",
            {"action": "dcc_new", "keycode": 32, "deadzone": 0.2, "persist": True},
        )
        check(
            fresh["source"] == "project" and fresh["persisted"] is True,
            "explicit project save receipt",
        )
        for _ in range(2):
            call("set_input_action", {"action": "dcc_input_mix", "keycode": 32, "persist": True})
        call("set_input_action", {"action": "dcc_input_mix", "deadzone": 0.4, "persist": True})
        call("set_input_action", {"action": "dcc_replace", "replace_events": True, "persist": True})
        check(actions("editor") == editor_before, "project writes leave editor InputMap unchanged")
        persisted = actions("project")
        check(len(persisted["dcc_input_mix"]["events"]) == 8, "append distinct logical key once")
        check(persisted["dcc_input_mix"]["deadzone"] == 0.4, "deadzone update")
        check(persisted["dcc_replace"]["events"] == [], "explicit replace clears all event classes")
        invalid = [
            {"keycode": 0},
            {"keycode": -1},
            {"keycode": 97},
            {"keycode": 128},
            {"keycode": 4194304},
            {"keycode": 8388607},
            {"keycode": 33554497},
            {"keycode": 1.5},
            {"keycode": True},
            {"deadzone": -0.1},
            {"deadzone": 1.1},
            {"persist": "true"},
            {"replace_events": 1},
            {"action": "bad/name"},
            {"action": ""},
            {"events": []},
        ]
        for case in invalid:
            request = {"action": "dcc_invalid", "persist": True, **case}
            saved_bytes = project.read_bytes()
            call("set_input_action", request, error=True)
            check(project.read_bytes() == saved_bytes, "invalid input cannot save")
            check("dcc_invalid" not in actions("project"), "invalid input cannot mutate settings")
        for persist in (False, True):
            for change in ({"keycode": 0}, {"deadzone": 2}):
                call(
                    "set_input_action",
                    {
                        "action": "dcc_input_mix",
                        "replace_events": True,
                        "persist": persist,
                        **change,
                    },
                    error=True,
                )
                check(
                    actions("project") == persisted, "invalid update preserves entire project view"
                )
                check(
                    actions("editor") == editor_before,
                    "invalid update preserves entire editor view",
                )
        check(
            actions("project") == persisted, "all rejected action names leave project map unchanged"
        )
        check(
            actions("editor") == editor_before,
            "all rejected action names leave editor map unchanged",
        )
        call("get_input_actions", {"source": "runtime"}, error=True)
        saved_bytes = project.read_bytes()
        backup = work / "project.saved"
        project.rename(backup)
        project.mkdir()
        try:
            call(
                "set_input_action",
                {
                    "action": "dcc_input_mix",
                    "deadzone": 0.9,
                    "replace_events": True,
                    "persist": True,
                },
                error=True,
            )
            call(
                "set_input_action",
                {"action": "dcc_save_failure", "keycode": 32, "persist": True},
                error=True,
            )
            check(
                actions("project") == persisted,
                "actual save failures roll back existing and new setting",
            )
            check(
                actions("editor") == editor_before, "save failure does not mutate editor bindings"
            )
        finally:
            project.rmdir()
            backup.rename(project)
        check(
            project.read_bytes() == saved_bytes,
            "fixture restores prior disk file after save failures",
        )
        shutdown()
        launch("editor-reopen")
        check(actions("project") == persisted, "fresh editor reads identical persisted actions")
        check(
            "dcc_unsaved" not in actions("editor"),
            "legacy editor-only action disappears on restart",
        )
        shutdown()
        after = native("readback")
        mixed = after["actions"]["dcc_input_mix"]
        check(
            mixed["events"][:7] == before["actions"]["dcc_input_mix"]["events"],
            "all original native resource properties and order survive save/reopen",
        )
        check(
            len(mixed["events"]) == 8 and mixed["events"][7]["keycode"] == 32,
            "one actual saved logical Space event",
        )
        check(mixed["fixture_marker"] == "keep", "extra action metadata retained")
        check(
            mixed["input_event_count"] == 8 and abs(mixed["input_deadzone"] - 0.4) < 1e-6,
            "fresh game InputMap loads project binding",
        )
        check(after["actions"]["dcc_new"]["in_input_map"], "new persistent action in fresh game")
        check(
            after["actions"]["dcc_replace"]["input_event_count"] == 0,
            "cleared action in fresh game",
        )
        check(
            not after["actions"]["dcc_unsaved"]["in_input_map"],
            "editor temporary binding never enters game",
        )
        check(
            not after["actions"]["dcc_save_failure"]["in_project_settings"],
            "failed new action not persisted",
        )
        implicit_after = after["actions"]["dcc_implicit"]
        check(implicit_after["events"][0] is None, "null event entry preserved on disk")
        check(
            implicit_after["events"][1] == before["actions"]["dcc_implicit"]["events"][1],
            "physical event attributes survive alongside null",
        )
        check(
            implicit_after["events"][2]["keycode"] == 32,
            "logical Space appended after null and physical event",
        )
        check(
            implicit_after["input_event_count"] == 2,
            "fresh game skips null event like native InputMap",
        )
        check(
            abs(implicit_after["input_deadzone"] - 0.2) < 1e-6,
            "fresh game native fallback deadzone retained",
        )
        check(
            after["description"] == "unrelated sentinel", "unrelated project setting value retained"
        )
        check(not exceeded and monitor_error is None, "sampled resource budget and healthy monitor")
        result["passed"] = True
    except Exception as exc:
        result["error"] = repr(exc)
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if server:
            server.stop()
        else:
            bridge.stop_bridge()
        for log in logs:
            log.close()
        stop.set()
        thread.join(timeout=2)
        result["peak_observed_bytes"] = peak
        result["resource_limit_exceeded"] = exceeded
        result["resource_monitor_error"] = monitor_error
        for path in set(addon.rglob("*.uid")) - uid_before:
            path.unlink()
        shutil.rmtree(work)
        result["runtime_cache_removed"] = not work.exists()
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "calls"}, indent=2))
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--budget-root", type=Path, action="append", default=[])
    parser.add_argument("--max-bytes", type=int, default=0)
    args = parser.parse_args()
    return run(args.godot, args.out, args.budget_root, args.max_bytes)


if __name__ == "__main__":
    raise SystemExit(main())
