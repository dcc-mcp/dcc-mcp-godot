"""Run bounded native addon-method regressions, without claiming MCP or A/V coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).parents[1]
ADDON = ROOT / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot"


def run(godot: str, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    receipt = {
        "passed": False,
        "scope": "native addon methods, not MCP transport or audiovisual playback",
        "source_sha256": {
            name: hashlib.sha256((ADDON / name).read_bytes()).hexdigest()
            for name in ("capabilities.gd", "ui_texture.gd")
        },
    }
    with tempfile.TemporaryDirectory(prefix="animation-keyframes-") as temporary:
        project = Path(temporary)
        addon = project / "addons/dcc_mcp_godot"
        addon.mkdir(parents=True)
        for name in ("capabilities.gd", "ui_texture.gd"):
            shutil.copyfile(ADDON / name, addon / name)
        (project / "project.godot").write_text(
            'config_version=5\n\n[application]\nconfig/name="Animation keyframe regression"\n'
            '\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',
            encoding="utf-8",
        )
        for name in ("step", "cold", "wrong", "scripted"):
            with wave.open(str(project / f"{name}.wav"), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(b"\x00\x10" * 800)
        try:
            (project / "linked.wav").symlink_to(project / "step.wav")
        except (OSError, NotImplementedError):
            pass  # The native receipt reports this one case as not measured.
        (project / "audio_fixture.gd").write_text("extends AudioStreamWAV\n", encoding="utf-8")
        env = dict(os.environ)
        # Keep every generated engine cache/config in this owned disposable fixture.
        for name in ("XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
            location = project / name.lower()
            location.mkdir()
            env[name] = str(location)
        env["GODOT_SILENCE_ROOT_WARNING"] = "1"
        try:
            imported = subprocess.run(
                [godot, "--headless", "--editor", "--path", str(project), "--import", "--quit"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=45,
                check=False,
            )
            (out / "import.log").write_bytes(imported.stdout)
            if imported.returncode != 0:
                raise RuntimeError(f"Native import exited {imported.returncode}")
            if b"SCRIPT ERROR:" in imported.stdout:
                raise RuntimeError("Native import reported a GDScript error")
            fixture = project / "addons/keyframe_regression"
            fixture.mkdir()
            shutil.copyfile(
                ROOT / "tests/godot_project/animation_keyframe_smoke.gd", fixture / "plugin.gd"
            )
            (fixture / "plugin.cfg").write_text(
                '[plugin]\nname="Keyframe regression"\ndescription="Native regression"\n'
                'author="DCC-MCP"\nversion="1"\nscript="plugin.gd"\n',
                encoding="utf-8",
            )
            with (project / "project.godot").open("a", encoding="utf-8") as config:
                config.write(
                    "\n[editor_plugins]\nenabled=PackedStringArray("
                    '"res://addons/keyframe_regression/plugin.cfg")\n'
                )
            executed = subprocess.run(
                [godot, "--headless", "--editor", "--path", str(project)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=45,
                check=False,
            )
            (out / "native.log").write_bytes(executed.stdout)
            if b"SCRIPT ERROR:" in executed.stdout:
                raise RuntimeError("Native assertions reported a GDScript error")
            result = project / "keyframe-result.json"
            if not result.is_file():
                raise RuntimeError("Native engine produced no assertion receipt")
            native = json.loads(result.read_text(encoding="utf-8"))
            receipt["native"] = native
            receipt["passed"] = (
                executed.returncode == 0
                and native.get("passed") is True
                and native.get("checks", 0) >= 100
                and not native.get("failures")
            )
        except (OSError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            receipt["error"] = str(exc)
            if isinstance(exc, subprocess.TimeoutExpired) and exc.stdout:
                (out / "timeout.log").write_bytes(exc.stdout)
    (out / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True)
    parser.add_argument("--out", type=Path, default=Path("animation-keyframe-probe"))
    options = parser.parse_args()
    raise SystemExit(run(options.godot, options.out))
