"""Schema/generation and source-boundary checks; native behavior has a separate probe."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema
import yaml

ROOT = Path(__file__).parents[1]
CAPABILITIES = ROOT / "src/dcc_mcp_godot/godot_addon/addons/dcc_mcp_godot/capabilities.gd"
SPEC = importlib.util.spec_from_file_location(
    "keyframe_generator", ROOT / "tools/generate_capability_skills.py"
)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class AnimationKeyframeContractTests(unittest.TestCase):
    def setUp(self):
        tools = yaml.safe_load(
            (ROOT / "src/dcc_mcp_godot/skills/godot-animation/tools.yaml").read_text(
                encoding="utf-8"
            )
        )["tools"]
        self.tool = next(tool for tool in tools if tool["name"] == "set_animation_keyframe")

    def test_generated_animation_files_are_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(GENERATOR, "ROOT", Path(temporary)):
                GENERATOR.generate()
            for relative in ("SKILL.md", "tools.yaml", "scripts/dispatch.py"):
                self.assertEqual(
                    (Path(temporary) / "godot-animation" / relative).read_text(encoding="utf-8"),
                    (ROOT / "src/dcc_mcp_godot/skills/godot-animation" / relative).read_text(
                        encoding="utf-8"
                    ),
                )

    def test_generation_parity_accepts_windows_checkout_line_endings(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            relative = Path("src/dcc_mcp_godot/skills/godot-animation")
            for name in ("SKILL.md", "tools.yaml", "scripts/dispatch.py"):
                target = checkout / relative / name
                target.parent.mkdir(parents=True, exist_ok=True)
                content = (ROOT / relative / name).read_text(encoding="utf-8")
                target.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))
            with patch.dict(globals(), {"ROOT": checkout}):
                self.test_generated_animation_files_are_current()

    def test_required_identity_and_payload(self):
        schema = self.tool["input_schema"]
        jsonschema.Draft202012Validator.check_schema(schema)
        request = {"animation": "walk", "track": 0, "value": [1, 2, 3]}
        jsonschema.validate(request, schema)
        for key in request:
            with self.subTest(key=key), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate({k: v for k, v in request.items() if k != key}, schema)

    def test_legacy_payload_shapes_stay_accepted(self):
        for value in (None, True, 4.5, "clip", [1, 0, 0, 0, 0], {"method": "play", "args": []}):
            with self.subTest(value=value):
                jsonschema.validate(
                    {"animation": "walk", "track": 0, "value": value},
                    self.tool["input_schema"],
                )

    def test_native_conversion_contract_is_discoverable(self):
        description = self.tool["input_schema"]["properties"]["value"]["description"]
        for text in ("three finite", "[x,y,z,w]", "without normalization", "stream_path", "cache"):
            self.assertIn(text, description)
        self.assertFalse(self.tool["read_only"])
        self.assertFalse(self.tool["idempotent"])
        self.assertEqual(self.tool["affinity"], "main")

    def test_negative_key_cannot_reach_success_receipt(self):
        source = CAPABILITIES.read_text(encoding="utf-8")
        body = source.split("func _set_animation_keyframe(", 1)[1].split(
            "func _animation_finite_number(", 1
        )[0]
        self.assertLess(body.index("_animation_key_value("), body.index("track_insert_key("))
        self.assertLess(body.index("if key < 0: return _error("), body.index('"inserted": true'))
        self.assertEqual(body.count("track_insert_key("), 1)

    def test_audio_does_not_load_or_parse_resources(self):
        source = CAPABILITIES.read_text(encoding="utf-8")
        body = source.split("func _animation_audio_key(", 1)[1].split(
            "func _get_animation_info(", 1
        )[0]
        for forbidden in (
            "ResourceLoader.load(",
            "ResourceLoader.exists(",
            "ConfigFile",
            "str_to_var(",
            "await ",
            ".scan(",
            "take_over_path(",
        ):
            self.assertNotIn(forbidden, body)
        for required in (
            "get_cached_ref(",
            "get_script() != null",
            "get_file_import_is_valid(",
            "is_link(",
        ):
            self.assertIn(required, body)

    def test_native_probe_is_required_in_real_engine_ci(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python tests/probe_animation_keyframes.py", ci)
        self.assertIn("--out animation-keyframe-probe", ci)
        live = (ROOT / "tests/live_godot_smoke.py").read_text(encoding="utf-8")
        self.assertIn('"godot-animation"', live)
        self.assertIn("Malformed 3D key returned success", live)
        self.assertIn("Saved/reopened typed animation keys changed", live)

    def test_probe_rejects_script_error_despite_a_passing_native_receipt(self):
        # This is a runner unit test, not evidence that any Godot method ran.
        spec = importlib.util.spec_from_file_location(
            "keyframe_probe_contract", ROOT / "tests/probe_animation_keyframes.py"
        )
        assert spec is not None and spec.loader is not None
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)

        def completed(command, **_kwargs):
            if "--import" not in command:
                project = Path(command[command.index("--path") + 1])
                (project / "keyframe-result.json").write_text(
                    json.dumps({"passed": True, "checks": 200, "failures": []}),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, b"SCRIPT ERROR: local helper failed")
            return subprocess.CompletedProcess(command, 0, b"import succeeded")

        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(probe.subprocess, "run", side_effect=completed):
                with patch("builtins.print"):
                    code = probe.run("unused-godot", Path(temporary))
            self.assertEqual(code, 1)
            result = json.loads((Path(temporary) / "result.json").read_text(encoding="utf-8"))
            self.assertFalse(result["passed"])
            self.assertIn("GDScript error", result["error"])


if __name__ == "__main__":
    unittest.main()
