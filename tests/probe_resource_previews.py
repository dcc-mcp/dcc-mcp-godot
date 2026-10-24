"""Native editor probe; callback injection is not a windowed preview-worker test."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot"


def run(godot: str, out: Path, limit: int | None = None, windowed: bool = False) -> int:
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    budget_roots = [ROOT, out.parent] if limit is not None else [out]

    def size() -> int:
        return sum(p.stat().st_size for r in budget_roots for p in r.rglob("*") if p.is_file())

    receipt = {
        "passed": False,
        "windowed_preview_worker_measured": False,
        "windowed_requested": windowed,
        "scope": (
            "native callback/lifecycle contracts; real windowed worker only when flagged; "
            "not MCP acceptance"
        ),
        "source_sha256": {
            n: hashlib.sha256((ADDON / n).read_bytes()).hexdigest()
            for n in ["capabilities.gd", "plugin.gd"]
        },
    }
    with tempfile.TemporaryDirectory(prefix="resource-preview-", dir=out) as temporary:
        project = Path(temporary)
        addon = project / "addons/dcc_mcp_godot"
        addon.mkdir(parents=True)
        for name in ["capabilities.gd", "ui_texture.gd", "plugin.gd", "commands.gd"]:
            shutil.copyfile(ADDON / name, addon / name)
        fixture = project / "addons/probe"
        fixture.mkdir()
        shutil.copyfile(
            ROOT / "tests/godot_project/resource_preview_smoke.gd", fixture / "plugin.gd"
        )
        (fixture / "plugin.cfg").write_text(
            '[plugin]\nname="Preview contracts"\nauthor="DCC-MCP"\n'
            'version="1"\nscript="plugin.gd"\n'
        )
        (project / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Resource preview contracts"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n[editor_plugins]\nenabled=PackedStringArray("res://addons/probe/plugin.cfg")\n'
        )

        def chunk(name: bytes, value: bytes) -> bytes:
            return (
                struct.pack(">I", len(value))
                + name
                + value
                + struct.pack(">I", zlib.crc32(name + value))
            )

        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff\0\0\xff" * 2) * 2))
            + chunk(b"IEND", b"")
        )
        (project / "texture.png").write_bytes(png)
        (project / "linked.png").symlink_to(project / "texture.png")
        (project / "output-link").symlink_to(project, target_is_directory=True)
        env = dict(os.environ, GODOT_SILENCE_ROOT_WARNING="1")
        for key in ["XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME"]:
            path = project / key.lower()
            path.mkdir()
            env[key] = str(path)
        initial = size()
        peak = initial
        stopped = None
        receipt.update(initial_bytes=initial, limit_bytes=limit)
        if limit is not None and initial >= limit:
            receipt["error"] = "static fixture exceeds resource limit"
        else:
            start = time.monotonic()
            with (out / "native.log").open("wb") as log:
                command = [godot, "--editor", "--path", str(project)]
                if not windowed:
                    command.insert(1, "--headless")
                receipt["command"] = command
                process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
                while process.poll() is None:
                    peak = max(peak, size())
                    if (limit is not None and peak > limit) or time.monotonic() - start > 45:
                        stopped = (
                            "resource_limit" if limit is not None and peak > limit else "timeout"
                        )
                        process.terminate()
                        break
                    time.sleep(0.1)
                try:
                    code = process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    code = process.wait()
            receipt.update(exit_code=code, peak_observed_bytes=peak, stopped=stopped)
            log_text = (out / "native.log").read_text()
            result_path = project / "preview-result.json"
            if result_path.is_file():
                receipt["native"] = json.loads(result_path.read_text())
                receipt["windowed_preview_worker_measured"] = receipt["native"].get(
                    "windowed_preview_worker_measured", False
                )
            receipt["script_error_seen"] = "SCRIPT ERROR:" in log_text
            receipt["passed"] = (
                code == 0
                and stopped is None
                and not receipt["script_error_seen"]
                and receipt.get("native", {}).get("passed") is True
                and (not windowed or receipt["windowed_preview_worker_measured"])
            )
    receipt["after_cache_cleanup_bytes"] = size()
    (out / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-workspace-bytes", type=int)
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Requires a real display or an existing xvfb-run wrapper",
    )
    args = parser.parse_args()
    raise SystemExit(run(args.godot, args.out, args.max_workspace_bytes, args.windowed))
