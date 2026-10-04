"""Windowed lane probe: call ``render_scene_preview`` on a real Godot host.

``tests/live_godot_smoke.py`` starts every editor with ``--headless``, and the
host deliberately refuses scene previews under that display driver
(``capabilities.gd``: rendering degrades to dummy and an offscreen viewport
reads back nothing). The live job therefore never exercises the render path,
and its green light is not coverage of it. This probe is the missing lane: it
starts a windowed editor, calls the tool for real, and measures the frames.

Platform tiers
--------------
The acceptance criteria are tiered because a tolerance measured on one platform
is not transferable to another (see ``preview_frame_metrics``):

* tier ``A`` -- byte-identical frames. Measured on a windowed Windows host.
* tier ``B`` -- ``mean_delta <= 1.0/255`` and ``max_delta <= 32``. The tier for
  a platform with no measured noise floor, which is why this probe writes the
  noise floor it measures into its artifact: the numbers produced by the first
  run *are* that platform's floor.

The reference frame for the delta is frame 0 of this run, rendered by this host
on this platform, not a frame archived elsewhere: pixels legitimately differ
between GPUs, drivers and rasterisers, so a cross-platform pixel diff would
measure the hardware rather than the tool. What is carried across from the
archived baseline is the rendering method, which must match.

Exit codes
----------
``0`` measured and passed, ``1`` measured and failed the criteria, ``2`` not
measured. A platform that cannot create a windowed rendering device reports
``not_measured`` and skips the assertions rather than turning into either a
false green (the exact failure this lane exists to prevent) or a permanent red
that blocks every pull request. The reason is written to the artifact, the job
summary and stdout, so a skipped lane is always visible.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).parents[1]
PROJECT_GODOT = REPO / "tests" / "godot_project" / "project.godot"
SCENE = REPO / "tests" / "godot_project" / "preview_probe.tscn"

SCENE_RESOURCE = "res://preview_probe.tscn"
ALT_CAMERA = "AltCamera"

WIDTH = 1280
HEIGHT = 720
FRAME_COUNT = 3
DEFAULT_CALLS = 5

# xvfb-run's default screen is 8-bit pseudocolour, which cannot host a GLX
# context; Godot needs a 24-bit depth to create one at all.
XVFB_SERVER_ARGS = "-screen 0 1920x1080x24 -ac +extension GLX +render -noreset"

EXIT_MEASURED_PASS = 0
EXIT_MEASURED_FAIL = 1
EXIT_NOT_MEASURED = 2

# The MCP layer refuses tools/call for main-affinity tools until these bits are
# present and true. They are published by the adapter's own readiness monitor,
# not at connect time, so a connected bridge is not by itself a ready backend.
READINESS_BITS = ("dcc", "host_execution_bridge", "main_thread_executor")
READINESS_TIMEOUT = 90.0

# The archived windowed baseline frame. Its pixels are a Windows/NVIDIA
# measurement and are not comparable to another platform's, but its rendering
# method, colour spread and Godot version are the provenance a later run is
# checked against.
ARCHIVED_BASELINE: dict[str, Any] = {
    "platform": "Windows",
    "godot_version": "4.7.2.stable.official.ed1daf0bf",
    "display_driver": "Windows",
    "rendering_method": "gl_compatibility",
    "video_adapter": "NVIDIA GeForce RTX 5080",
    "has_rendering_device": False,
    "width": 1280,
    "height": 720,
    "bytes": 283500,
    "unique_colors": 9317,
    "mean_luma": 150.2451,
    "camera_source": "scene",
    "sha256": "df8cdc296c412b6511d0f5862b38a6d458973053aad4fdabaa5ea5f842731b8c",
    "tier": "A",
    "tier_a_result": "mean_delta=0.000, different_pixels=0, 10/10 renders byte-identical",
    # Discrimination control measured on that host: the same scene rendered
    # through another rendering path differed by mean_delta 8.037 over 96.36%
    # of pixels, which is what makes a 0.000 reading meaningful.
    "discrimination_control": {
        "comparison": "gl_compatibility vs forward_plus",
        "mean_delta": 8.037,
        "different_pixel_pct": 96.36,
    },
}

sys.path.insert(0, str(REPO / "src"))

from preview_frame_metrics import (  # noqa: E402
    TIER_B_MAX_DELTA,
    TIER_B_MEAN_DELTA,
    Frame,  # noqa: E402
    compare,
    judge,
    load,
    measure,
)

from dcc_mcp_godot import bridge  # noqa: E402
from dcc_mcp_godot.install import main as install_main  # noqa: E402
from dcc_mcp_godot.server import GodotMcpServer  # noqa: E402


class NotMeasured(Exception):
    """The lane could not render a frame on this platform; skip the assertions."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason if not detail else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def _mcp_post(mcp_url: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    request = urllib.request.Request(
        mcp_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MCP {method} failed with HTTP {error.code}: {body}") from error


def _error_message(payload: Any, *, limit: int = 800) -> str:
    """Flatten one tool error to its message so the receipt stays readable.

    The raw envelope carries the full bridge traceback on every refusal; keeping
    it would bury the one line that says why the call failed.
    """
    if isinstance(payload, dict):
        for key in ("message", "error", "prompt"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:limit]
            if isinstance(value, dict):
                nested = _error_message(value, limit=limit)
                if nested:
                    return nested
        for value in payload.values():
            nested = _error_message(value, limit=limit)
            if nested:
                return nested
        return json.dumps(payload, default=str)[:limit]
    if isinstance(payload, str):
        return payload.strip()[:limit]
    return ""


def _tool_error(envelope: Any) -> dict[str, Any] | None:
    """Recognise the host's own error shapes, not only JSON-RPC errors.

    The Godot addon reports refusals inside an otherwise successful envelope, so
    treating only transport-level errors as failures would record a refusal as a
    frame with no file behind it.
    """
    if not isinstance(envelope, dict):
        return {"unshaped": repr(envelope)}
    if envelope.get("isError") is True or envelope.get("success") is False:
        return envelope
    if envelope.get("status") in {"failed", "error"}:
        return envelope
    for key in ("error", "errors"):
        value = envelope.get(key)
        if isinstance(value, dict) and value:
            return value
        if isinstance(value, str) and value.strip():
            return {"message": value}
    inner = envelope.get("result")
    if isinstance(inner, dict):
        return _tool_error(inner)
    return None


def _unwrap(envelope: Any) -> dict[str, Any] | None:
    """Return the tool payload from an MCP envelope, or None if it has none."""
    if not isinstance(envelope, dict):
        return None
    if envelope.get("status") == "completed" and isinstance(envelope.get("result"), dict):
        body = envelope["result"]
        return {**body, **body["context"]} if isinstance(body.get("context"), dict) else body
    if isinstance(envelope.get("context"), dict):
        return {**envelope, **envelope["context"]}
    return envelope


def _call_tool(mcp_url: str, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call one MCP tool, returning ``{"ok": bool, "payload": ..., "error": str}``."""
    response = _mcp_post(mcp_url, "tools/call", {"name": name, "arguments": arguments or {}})
    if response.get("error"):
        return {"ok": False, "payload": None, "error": _error_message(response["error"])}
    result = response.get("result", {})
    if result.get("isError") is True:
        return {"ok": False, "payload": None, "error": _error_message(result)}
    envelope = result.get("structuredContent")
    if envelope is None and result.get("content"):
        envelope = json.loads(result["content"][0]["text"])
    detected = _tool_error(envelope)
    if detected is not None:
        return {"ok": False, "payload": None, "error": _error_message(detected)}
    if not isinstance(envelope, dict):
        return {"ok": False, "payload": None, "error": f"unshaped envelope: {envelope!r}"}
    job_id = envelope.get("job_id")
    if job_id:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            poll = _mcp_post(
                mcp_url,
                "tools/call",
                {
                    "name": "jobs_get_status",
                    "arguments": {"job_id": job_id, "include_result": True},
                },
            )
            if poll.get("error"):
                return {"ok": False, "payload": None, "error": _error_message(poll["error"])}
            status = poll.get("result", {}).get("structuredContent")
            if status is None and poll.get("result", {}).get("content"):
                status = json.loads(poll["result"]["content"][0]["text"])
            if status.get("status") == "completed":
                envelope = status
                break
            if status.get("status") in {"failed", "cancelled", "interrupted"}:
                return {"ok": False, "payload": None, "error": _error_message(status)}
            time.sleep(0.05)
        else:
            return {"ok": False, "payload": None, "error": f"job {job_id} did not complete"}
    payload = _unwrap(envelope)
    if payload is None:
        return {"ok": False, "payload": None, "error": f"unshaped envelope: {envelope!r}"}
    return {"ok": True, "payload": payload, "error": ""}


def _resolve_tool_name(mcp_url: str, suffix: str) -> str:
    names: list[str] = []
    cursor: str | None = None
    for _ in range(20):
        response = _mcp_post(mcp_url, "tools/list", {"cursor": cursor} if cursor else None)
        result = response.get("result", {})
        names.extend(tool["name"] for tool in result.get("tools", []))
        cursor = result.get("nextCursor")
        if not cursor:
            break
    matches = [name for name in names if name == suffix or name.endswith(f"__{suffix}")]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one MCP tool ending in {suffix!r}, found {matches!r}")
    return matches[0]


def _readiness_ready(report: dict[str, Any]) -> bool:
    """Report whether a /v1/readyz payload has every execution bit set."""
    return all(bool(report.get(bit)) for bit in READINESS_BITS)


def _wait_for_ready(mcp_url: str, timeout: float = READINESS_TIMEOUT) -> dict[str, Any]:
    """Wait for the adapter to report the host execution path as ready.

    ``render_scene_preview`` runs with main-thread affinity, and the MCP layer
    gates those calls on readiness. Seeing the editor attach to the loopback
    bridge is not enough: the adapter publishes the bits from its own monitor,
    so a call made immediately after connect can be refused outright.
    """
    url = f"{mcp_url.rsplit('/mcp', 1)[0]}/v1/readyz"
    deadline = time.monotonic() + timeout
    report: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict):
                report = payload
                if _readiness_ready(report):
                    return report
        except (urllib.error.URLError, OSError, ValueError):
            report = {}
        time.sleep(0.1)
    raise NotMeasured(
        "backend_not_ready",
        f"{url} never reported {', '.join(READINESS_BITS)} ready: "
        f"{json.dumps(report, default=str)}",
    )


def _godot_version(godot: Path) -> str:
    completed = subprocess.run(
        [str(godot), "--version"], capture_output=True, text=True, check=False, timeout=120
    )
    return completed.stdout.strip() or completed.stderr.strip()


def _editor_command(godot: Path, project: Path, driver: str, wrap_xvfb: bool) -> list[str]:
    command = [
        str(godot),
        "--editor",
        "--path",
        str(project),
        "--rendering-driver",
        driver,
        "--quit-after",
        "3600",
    ]
    if wrap_xvfb:
        command = ["xvfb-run", "-a", "-s", XVFB_SERVER_ARGS, *command]
    return command


def _blank_frame_control(width: int, height: int) -> dict[str, Any]:
    """Prove the criteria still reject an all-black frame that has a right size.

    A blank PNG is the failure mode the whole comparison guards against: it
    satisfies bytes > 0 and the requested dimensions while carrying no scene at
    all. If this control ever passes, the gate is worthless.
    """
    from dcc_mcp_godot.screenshot import _encode_png

    pixels = bytes(width * height * 4)
    png = _encode_png(pixels, width=width, height=height, channels=4, color_type=6)
    path = Path(tempfile.mkdtemp(prefix="dcc-mcp-godot-trap-")) / "blank.png"
    path.write_bytes(png)
    frame = load(path)
    metrics = measure(frame)
    verdict = judge(
        metrics,
        None,
        tier="B",
        expected_width=width,
        expected_height=height,
        expected_rendering_method="gl_compatibility",
        observed_rendering_method="gl_compatibility",
    )
    blank = [item for item in verdict["failures"] if "unique_colors" in item]
    return {
        "frame": "all-black PNG encoded by the adapter's own encoder",
        "metrics": metrics.as_dict(),
        "rejected": bool(blank),
        # Named, because the control exists to prove this one criterion bites.
        # The frame is judged without a delta, which is itself a recorded
        # failure and would otherwise mask the signal.
        "rejected_by": "unique_colors" if blank else "",
        "failures": verdict["failures"],
    }


def _noise_floor(deltas: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise the repeat-to-reference deltas: this platform's noise floor."""
    if not deltas:
        return {"status": "not_measured", "repeats": 0}
    return {
        "status": "measured",
        "repeats": len(deltas),
        "mean_delta_max": max(item["mean_delta"] for item in deltas),
        "max_delta_max": max(item["max_delta"] for item in deltas),
        "different_pixel_pct_max": max(item["different_pixel_pct"] for item in deltas),
        "repeats_byte_identical": all(item["sha256_match"] for item in deltas),
        "tier_b_mean_delta_limit": TIER_B_MEAN_DELTA,
        "tier_b_max_delta_limit": TIER_B_MAX_DELTA,
    }


def probe(
    *,
    godot: Path,
    out: Path,
    calls: int,
    tier: str,
    width: int,
    height: int,
    driver: str,
    rendering_method: str,
    xvfb: str,
) -> dict[str, Any]:
    """Run the lane and return its receipt. Raises :class:`NotMeasured`."""
    workspace = Path(tempfile.mkdtemp(prefix="dcc-mcp-godot-preview-"))
    project = workspace / "project"
    project.mkdir(parents=True)
    shutil.copy2(PROJECT_GODOT, project)
    shutil.copy2(SCENE, project / SCENE_RESOURCE.replace("res://", ""))

    receipt: dict[str, Any] = {
        "lane": "windowed-render-scene-preview",
        "measured": False,
        "tier": tier,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "display": os.environ.get("DISPLAY", ""),
            "wayland_display": os.environ.get("WAYLAND_DISPLAY", ""),
        },
        "godot_version": _godot_version(godot),
        "request": {
            "scene_path": SCENE_RESOURCE,
            "width": width,
            "height": height,
            "frame_count": FRAME_COUNT,
            "rendering_method": rendering_method,
            "rendering_driver_arg": driver,
            "calls": calls,
            "hide_window_env": "0",
        },
        "archived_baseline": ARCHIVED_BASELINE,
        "reference": "frame 0 rendered by this host in this run",
        "frames": [],
        "errors": [],
        "repeats": [],
        "noise_floor": {"status": "not_measured", "repeats": 0},
        "controls": {},
        "verdict": {"passed": False, "failures": []},
        "not_measured": None,
    }

    install_output = io.StringIO()
    with contextlib.redirect_stdout(install_output):
        install_exit = install_main(
            ["install", str(project), "--dcc-path", str(godot), "--yes", "--json"]
        )
    install_result = json.loads(install_output.getvalue())
    if install_exit != 50 or install_result.get("status") != "requires_restart":
        raise NotMeasured("install_failed", json.dumps(install_result, default=str)[:2000])
    receipt["install"] = {"exit_code": install_exit, "status": install_result.get("status")}

    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        bridge_port = probe_socket.getsockname()[1]
    os.environ["DCC_MCP_GODOT_BRIDGE_PORT"] = str(bridge_port)
    os.environ["DCC_MCP_GODOT_BRIDGE_URL"] = f"ws://127.0.0.1:{bridge_port}"

    server = GodotMcpServer(port=0)
    server.register_builtin_actions()
    server.start(install_atexit_hook=False)
    editor: subprocess.Popen[str] | None = None
    log_stream: Any = None
    log_path = out / "editor.log"
    try:
        log_stream = log_path.open("w", encoding="utf-8")
        mcp_url = server.mcp_url
        if not mcp_url:
            raise NotMeasured("server_not_published", "the adapter did not publish an MCP URL")

        wrap_xvfb = (
            xvfb == "auto" and not os.environ.get("DISPLAY") and bool(shutil.which("xvfb-run"))
        )
        environment = os.environ.copy()
        # Under Xvfb the display is already private, so there is nothing to hide
        # from. Hiding is a Windows concern, and unmapping the editor's main
        # window on X11 risks starving the render loop this lane measures.
        environment["DCC_MCP_GODOT_HIDE_WINDOW"] = "0"
        command = _editor_command(godot, project, driver, wrap_xvfb)
        receipt["editor_command"] = command
        receipt["xvfb_wrapped"] = wrap_xvfb
        editor = subprocess.Popen(
            command, env=environment, stdout=log_stream, stderr=subprocess.STDOUT, text=True
        )
        receipt["editor_pid"] = editor.pid

        deadline = time.monotonic() + 120
        while not bridge.get_bridge().is_connected() and time.monotonic() < deadline:
            if editor.poll() is not None:
                break
            time.sleep(0.1)
        if not bridge.get_bridge().is_connected():
            raise NotMeasured("editor_did_not_connect", _tail(log_path))
        receipt["bridge_connected"] = True

        bootstrap_path = project / ".godot" / "dcc_mcp_godot_bootstrap.json"
        deadline = time.monotonic() + 60
        while not bootstrap_path.is_file() and time.monotonic() < deadline:
            if editor.poll() is not None:
                break
            time.sleep(0.1)
        bootstrap: dict[str, Any] = (
            json.loads(bootstrap_path.read_text(encoding="utf-8"))
            if bootstrap_path.is_file()
            else {}
        )
        receipt["bootstrap"] = bootstrap
        if bootstrap.get("status") != "ready":
            raise NotMeasured("bootstrap_not_ready", json.dumps(bootstrap, default=str)[:2000])

        load_skill = _call_tool(mcp_url, "load_skill", {"skill_names": ["godot-editor"]})
        if not load_skill["ok"]:
            raise NotMeasured("skill_not_loaded", load_skill["error"])
        tool_name = _resolve_tool_name(mcp_url, "render_scene_preview")
        receipt["tool_name"] = tool_name
        receipt["readiness"] = _wait_for_ready(mcp_url)

        frames: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for index in range(calls):
            relative = f".dcc-mcp/preview/probe-{index:02d}.png"
            target = project / relative
            started = time.monotonic()
            response = _call_tool(
                mcp_url,
                tool_name,
                {
                    "scene_path": SCENE_RESOURCE,
                    "width": width,
                    "height": height,
                    "frame_count": FRAME_COUNT,
                    "rendering_method": rendering_method,
                    "path": f"res://{relative}",
                },
            )
            elapsed = round(time.monotonic() - started, 3)
            if not response["ok"]:
                errors.append(
                    {
                        "call": index,
                        "elapsed_s": elapsed,
                        "kind": "tool_error",
                        "error": response["error"],
                    }
                )
                continue
            if not target.is_file():
                errors.append(
                    {
                        "call": index,
                        "elapsed_s": elapsed,
                        "kind": "missing_output",
                        "error": str(target),
                        "payload": response["payload"],
                    }
                )
                continue
            frames.append(
                {
                    "call": index,
                    "elapsed_s": elapsed,
                    "file": str(target),
                    "tool": response["payload"],
                }
            )

        receipt["frames"] = [
            {
                "call": frame["call"],
                "elapsed_s": frame["elapsed_s"],
                "metrics": measure(_loaded(frame)).as_dict(),
                "rendering_method": str(frame["tool"].get("rendering_method", "")),
                "display_driver": str(frame["tool"].get("display_driver", "")),
                "video_adapter": str(frame["tool"].get("video_adapter", "")),
                "has_rendering_device": frame["tool"].get("has_rendering_device"),
                "camera_source": str(frame["tool"].get("camera_source", "")),
                "camera_path": str(frame["tool"].get("camera_path", "")),
                "frame_count": frame["tool"].get("frame_count"),
                "thread_ms": frame["tool"].get("thread_ms"),
                "budget_exceeded": frame["tool"].get("budget_exceeded"),
            }
            for frame in frames
        ]
        receipt["errors"] = errors
        receipt["calls_ok"] = len(frames)
        receipt["calls_failed"] = len(errors)
        if frames:
            receipt["host"] = {
                "display_driver": receipt["frames"][0]["display_driver"],
                "rendering_method": receipt["frames"][0]["rendering_method"],
                "video_adapter": receipt["frames"][0]["video_adapter"],
                "has_rendering_device": receipt["frames"][0]["has_rendering_device"],
            }
        if not frames:
            raise NotMeasured("no_frames_rendered", json.dumps(errors, default=str)[:2000])
        if len(frames) != calls:
            # Every call is sequential and fully awaited, so a partial run means
            # the host refused a render it had just performed successfully.
            errors.append(
                {
                    "call": None,
                    "kind": "incomplete_run",
                    "error": f"{len(frames)} of {calls} calls produced a frame",
                }
            )
            receipt["errors"] = errors
        receipt["measured"] = True

        reference = _loaded(frames[0])
        reference_metrics = measure(reference)
        receipt["reference_frame"] = {
            "file": frames[0]["file"],
            "metrics": reference_metrics.as_dict(),
        }
        shutil.copy2(frames[0]["file"], out / "reference-frame.png")

        deltas: list[dict[str, Any]] = []
        for frame in frames[1:]:
            candidate = _loaded(frame)
            delta = compare(reference, candidate)
            deltas.append(delta.as_dict())
            receipt["repeats"].append(
                {
                    "call": frame["call"],
                    "delta": delta.as_dict(),
                    "judgement": judge(
                        measure(candidate),
                        delta,
                        tier=tier,
                        expected_width=width,
                        expected_height=height,
                        expected_rendering_method=rendering_method,
                        observed_rendering_method=str(frame["tool"].get("rendering_method", "")),
                    ),
                }
            )
        receipt["noise_floor"] = _noise_floor(deltas)
        receipt["controls"] = {
            "blank_trap": _blank_frame_control(width, height),
            "alt_camera": _alt_camera_control(
                mcp_url, tool_name, reference, width, height, rendering_method, project, out
            ),
        }

        reference_verdict = judge(
            reference_metrics,
            None,
            tier=tier,
            expected_width=width,
            expected_height=height,
            expected_rendering_method=rendering_method,
            observed_rendering_method=str(frames[0]["tool"].get("rendering_method", "")),
        )
        failures: list[str] = []
        # The reference frame has no repeat delta of its own, so only the shared
        # criteria apply to it; the "no baseline delta" reason is expected here.
        failures.extend(
            item for item in reference_verdict["failures"] if "no baseline delta" not in item
        )
        for repeat in receipt["repeats"]:
            failures.extend(
                f"frame {repeat['call']}: {item}" for item in repeat["judgement"]["failures"]
            )
        if receipt["errors"]:
            failures.append(f"{len(receipt['errors'])} of {calls} render calls failed")
        trap = receipt["controls"]["blank_trap"]
        if trap.get("rejected") is not True:
            failures.append("blank trap frame was accepted; the criteria no longer bite")
        control = receipt["controls"]["alt_camera"]
        if control.get("status") == "measured" and not control.get("discriminating"):
            failures.append(
                "alt-camera control was not detected as a different frame "
                f"(mean_delta={control.get('mean_delta_vs_reference')}); the comparison is vacuous"
            )
        receipt["verdict"] = {"passed": not failures, "failures": failures}
        return receipt
    finally:
        if editor is not None and editor.poll() is None:
            editor.terminate()
            try:
                editor.wait(timeout=30)
            except subprocess.TimeoutExpired:
                editor.kill()
                editor.wait(timeout=15)
        if log_stream is not None:
            log_stream.close()
        with contextlib.suppress(Exception):
            server.stop()
        shutil.rmtree(workspace, ignore_errors=True)


_FRAMES: dict[str, Frame] = {}


def _loaded(frame: dict[str, Any]) -> Frame:
    """Decode once per file and cache it: each frame is measured and compared."""
    key = frame["file"]
    if key not in _FRAMES:
        _FRAMES[key] = load(key)
    return _FRAMES[key]


def _alt_camera_control(
    mcp_url: str,
    tool_name: str,
    reference: Frame,
    width: int,
    height: int,
    rendering_method: str,
    project: Path,
    out: Path,
) -> dict[str, Any]:
    """Render the same scene through another camera and check the comparator.

    A tight tolerance is only evidence if the comparator that produced it can
    see a real difference. This is the end-to-end form of that check: the same
    tool, the same host, the same rendering method, a different camera, so any
    delta it reports came from the render path rather than from a fixture.
    """
    relative = ".dcc-mcp/preview/control-alt-camera.png"
    response = _call_tool(
        mcp_url,
        tool_name,
        {
            "scene_path": SCENE_RESOURCE,
            "width": width,
            "height": height,
            "frame_count": FRAME_COUNT,
            "rendering_method": rendering_method,
            "camera_path": ALT_CAMERA,
            "path": f"res://{relative}",
        },
    )
    if not response["ok"]:
        return {"status": "inconclusive", "reason": response["error"]}
    target = project / relative
    if not target.is_file():
        return {"status": "inconclusive", "reason": f"no output at {target}"}
    control = load(target)
    delta = compare(reference, control)
    return {
        "status": "measured",
        "camera_path": ALT_CAMERA,
        "camera_source": str(response["payload"].get("camera_source", "")),
        "metrics": measure(control).as_dict(),
        "mean_delta_vs_reference": delta.mean_delta,
        "max_delta_vs_reference": delta.max_delta,
        "different_pixel_pct": delta.different_pixel_pct,
        "discriminating": delta.mean_delta > TIER_B_MEAN_DELTA or delta.different_pixel_pct > 5.0,
    }


def _tail(path: Path, limit: int = 4000) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-limit:]


def _summary(receipt: dict[str, Any]) -> str:
    """Render the job-summary markdown for one lane run."""
    lines = ["## Windowed `render_scene_preview` lane", ""]
    if not receipt.get("measured"):
        reason = receipt.get("not_measured") or {}
        lines += [
            "**Not measured** — the assertions were skipped, so this lane is not coverage.",
            "",
            f"- reason: `{reason.get('reason', 'unknown')}`",
            f"- godot: `{receipt.get('godot_version', 'unknown')}`",
            f"- platform: {receipt.get('platform', {}).get('system', 'unknown')}",
        ]
        detail = str(reason.get("detail", "")).strip()
        if detail:
            lines += ["", "```", detail[:2000], "```"]
        return "\n".join(lines) + "\n"

    host = receipt.get("host", {})
    floor = receipt.get("noise_floor", {})
    metrics = receipt.get("reference_frame", {}).get("metrics", {})
    request = receipt.get("request", {})
    verdict = receipt.get("verdict", {})
    size = f"{request.get('width')}x{request.get('height')}"
    outcome = "PASS" if verdict.get("passed") else "FAIL"
    system = receipt.get("platform", {}).get("system")
    lines += [
        f"**{outcome}** — tier {receipt.get('tier')}, "
        f"Godot `{receipt.get('godot_version')}` on {system}.",
        "",
        "| field | value |",
        "|---|---|",
        f"| display_driver | `{host.get('display_driver')}` |",
        f"| rendering_method | `{host.get('rendering_method')}` |",
        f"| video_adapter | {host.get('video_adapter')} "
        f"(rendering device: {host.get('has_rendering_device')}) |",
        f"| frames | {receipt.get('calls_ok')}/{request.get('calls')} calls, {size} |",
        f"| reference frame | {metrics.get('bytes')} bytes, "
        f"{metrics.get('unique_colors')} unique colours, mean_luma {metrics.get('mean_luma')} |",
        f"| noise floor | mean_delta max {floor.get('mean_delta_max')} "
        f"(limit {TIER_B_MEAN_DELTA}), max_delta max {floor.get('max_delta_max')} "
        f"(limit {TIER_B_MAX_DELTA}), different_pixels max "
        f"{floor.get('different_pixel_pct_max')}% |",
        f"| byte-identical repeats | {floor.get('repeats_byte_identical')} |",
    ]
    control = receipt.get("controls", {}).get("alt_camera", {})
    if control.get("status") == "measured":
        lines.append(
            f"| alt-camera control | mean_delta {control.get('mean_delta_vs_reference')}, "
            f"{control.get('different_pixel_pct')}% of pixels (discriminating: "
            f"{control.get('discriminating')}) |"
        )
    trap = receipt.get("controls", {}).get("blank_trap", {})
    lines.append(f"| blank trap frame | rejected: {trap.get('rejected')} |")
    if verdict.get("failures"):
        lines += ["", "Failures:", ""]
        lines += [f"- {item}" for item in verdict["failures"]]
    lines += [
        "",
        "The noise floor above is this platform's measurement: tighten the tier only with "
        "numbers from a run like this one, never by copying another platform's tolerance.",
    ]
    return "\n".join(lines) + "\n"


def _write_artifacts(out: Path, receipt: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "preview-probe.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    (out / "summary.md").write_text(_summary(receipt), encoding="utf-8")


def _exit_code(receipt: dict[str, Any]) -> int:
    if not receipt.get("measured"):
        return EXIT_NOT_MEASURED
    return EXIT_MEASURED_PASS if receipt.get("verdict", {}).get("passed") else EXIT_MEASURED_FAIL


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True, type=Path)
    parser.add_argument("--out", default=Path("preview-probe"), type=Path)
    parser.add_argument("--calls", type=int, default=DEFAULT_CALLS)
    parser.add_argument("--tier", default="B", choices=["A", "B"])
    parser.add_argument("--width", type=int, default=WIDTH)
    parser.add_argument("--height", type=int, default=HEIGHT)
    parser.add_argument("--driver", default="opengl3")
    parser.add_argument("--rendering-method", default="gl_compatibility")
    parser.add_argument(
        "--xvfb",
        default="auto",
        choices=["auto", "never"],
        help="Wrap the editor in xvfb-run when DISPLAY is unset (auto, the default).",
    )
    arguments = parser.parse_args()

    out = arguments.out
    out.mkdir(parents=True, exist_ok=True)
    try:
        receipt = probe(
            godot=arguments.godot.resolve(),
            out=out,
            calls=arguments.calls,
            tier=arguments.tier,
            width=arguments.width,
            height=arguments.height,
            driver=arguments.driver,
            rendering_method=arguments.rendering_method,
            xvfb=arguments.xvfb,
        )
    except NotMeasured as error:
        receipt = {
            "lane": "windowed-render-scene-preview",
            "measured": False,
            "tier": arguments.tier,
            "request": {"width": arguments.width, "height": arguments.height},
            "not_measured": {"reason": error.reason, "detail": error.detail},
            "verdict": {"passed": False, "failures": []},
        }
        _write_artifacts(out, receipt)
        print(_summary(receipt))
        print(
            "NOT MEASURED: windowed scene preview assertions skipped "
            f"({error.reason}); see {out / 'preview-probe.json'}",
            file=sys.stderr,
        )
        return EXIT_NOT_MEASURED
    except Exception:  # noqa: BLE001 - a harness fault must not fake a measurement
        receipt = {
            "lane": "windowed-render-scene-preview",
            "measured": False,
            "tier": arguments.tier,
            "request": {"width": arguments.width, "height": arguments.height},
            "not_measured": {
                "reason": "harness_error",
                "detail": traceback.format_exc(limit=12),
            },
            "verdict": {"passed": False, "failures": []},
        }
        _write_artifacts(out, receipt)
        print(_summary(receipt))
        print(
            "NOT MEASURED: the probe harness failed before it could render "
            f"({out / 'preview-probe.json'})",
            file=sys.stderr,
        )
        return EXIT_NOT_MEASURED

    _write_artifacts(out, receipt)
    print(_summary(receipt))
    code = _exit_code(receipt)
    if code == EXIT_MEASURED_FAIL:
        print(
            "FAILED: a rendered frame did not meet the tier "
            f"{receipt['tier']} criteria; see {out / 'preview-probe.json'}",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
