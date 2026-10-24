"""Host-free generated declarations; native persistence is exercised by the probe."""

import runpy
import tempfile
import unittest
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]


class InputActionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = yaml.safe_load(
            (ROOT / "src/dcc_mcp_godot/skills/godot-input/tools.yaml").read_text(encoding="utf-8")
        )
        cls.tools = {tool["name"]: tool for tool in data["tools"]}

    def test_generator_parity(self):
        namespace = runpy.run_path(str(ROOT / "tools/generate_capability_skills.py"))
        with tempfile.TemporaryDirectory() as tmp:
            globals_ = namespace["generate"].__globals__
            globals_["ROOT"] = Path(tmp)
            globals_["CATEGORIES"] = {"input": namespace["CATEGORIES"]["input"]}
            namespace["generate"]()
            for name in ("SKILL.md", "tools.yaml", "scripts/dispatch.py"):
                generated = (Path(tmp) / "godot-input" / name).read_text(encoding="utf-8")
                committed = (ROOT / "src/dcc_mcp_godot/skills/godot-input" / name).read_text(
                    encoding="utf-8"
                )
                self.assertEqual(generated, committed, name)

    def test_explicit_persistence_schema(self):
        schema = self.tools["set_input_action"]["input_schema"]
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertEqual(
            set(schema["properties"]),
            {"action", "keycode", "deadzone", "replace_events", "persist"},
        )
        self.assertFalse(schema["properties"]["persist"]["default"])
        for request in (
            {"action": "jump"},
            {
                "action": "jump",
                "persist": True,
                "keycode": 32,
                "deadzone": 0.25,
                "replace_events": True,
            },
        ):
            jsonschema.validate(request, schema)
        for request in (
            {},
            {"action": ""},
            {"action": "jump", "persist": "true"},
            {"action": "jump", "events": []},
            {"action": "jump", "keycode": True},
            {"action": "jump", "deadzone": 2},
        ):
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(request, schema)

    def test_project_query_is_opt_in(self):
        schema = self.tools["get_input_actions"]["input_schema"]
        self.assertEqual(set(schema["properties"]), {"source"})
        self.assertEqual(schema["properties"]["source"]["default"], "editor")
        for request in ({}, {"source": "editor"}, {"source": "project"}):
            jsonschema.validate(request, schema)
        for request in ({"source": "runtime"}, {"persist": True}):
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(request, schema)

    def test_simulation_contract_not_replaced(self):
        self.assertEqual(len(self.tools), 7)
        for name in (
            "simulate_key",
            "simulate_mouse_click",
            "simulate_mouse_move",
            "simulate_action",
            "simulate_sequence",
        ):
            properties = self.tools[name]["input_schema"]["properties"]
            self.assertIn("events", properties)
            self.assertNotIn("persist", properties)
            self.assertNotIn("source", properties)


if __name__ == "__main__":
    unittest.main()
