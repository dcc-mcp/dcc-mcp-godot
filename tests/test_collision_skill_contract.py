"""Documentation/package regression gates, not a game physics acceptance test.

These tests also run with stdlib unittest when the adapter is not installed.
"""

from __future__ import annotations

import importlib.util
import io
import re
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SKILLS_ROOT = ROOT / "src/dcc_mcp_godot/skills"


def _load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load_tool("generate_capability_skills")
ARTIFACTS = _load_tool("check_collision_skill_artifacts")


class CollisionSkillContractTests(unittest.TestCase):
    def test_generated_skills_match_committed_instructions_and_manifests(self):
        with tempfile.TemporaryDirectory() as temporary:
            generated = Path(temporary)
            with patch.object(GENERATOR, "ROOT", generated):
                GENERATOR.generate()
            for skill in ARTIFACTS.SKILLS:
                for name in ("SKILL.md", "tools.yaml", "scripts/dispatch.py"):
                    with self.subTest(skill=skill, name=name):
                        self.assertEqual(
                            (generated / skill / name).read_text(encoding="utf-8"),
                            (SKILLS_ROOT / skill / name).read_text(encoding="utf-8"),
                        )

    def test_every_entry_point_requires_explicit_intent_and_reason(self):
        for skill in ARTIFACTS.SKILLS:
            text = (SKILLS_ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill):
                for intent in ("solid", "trigger", "query-only", "none"):
                    self.assertIn(f"`{intent}`", text)
                self.assertIn("reason", text)
                self.assertIn('version: "0.2.0"', text)
                self.assertIn("collision intent", text)

    def test_one_reference_is_discoverable_without_cross_skill_file_links(self):
        reference = SKILLS_ROOT / ARTIFACTS.REFERENCE
        self.assertEqual(list(SKILLS_ROOT.glob("*/references/collision-intent.md")), [reference])
        physics = (SKILLS_ROOT / "godot-physics/SKILL.md").read_text(encoding="utf-8")
        self.assertIn('skill-reference-docs:\n      - "references/*.md"', physics)
        for skill in ARTIFACTS.SKILLS:
            root = SKILLS_ROOT / skill
            text = (root / "SKILL.md").read_text(encoding="utf-8")
            # Local links must work when only this skill is present. A sibling
            # reference may exist in source but is outside Core's read boundary.
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                path = target.split("#", 1)[0]
                self.assertNotIn("..", Path(path).parts)
                self.assertTrue((root / path).is_file(), (skill, target))
            if skill != "godot-physics":
                self.assertIn("load-skill godot-physics --dcc-type godot", text)
                self.assertIn("skill_refs__list", text)
                self.assertIn("skill: godot-physics", text)
                self.assertIn("skill_refs__read", text)
                self.assertIn("leave collision acceptance\nunverified", text)

    def test_reference_preserves_counterexamples_and_evidence_limits(self):
        text = (SKILLS_ROOT / ARTIFACTS.REFERENCE).read_text(encoding="utf-8")
        for requirement in (
            "## 1. Declare intent before implementation",
            "## 2. Build and inspect actual physics",
            "## 3. Share interaction reachability",
            "## 4. Collision regression gate",
            "tree trunks",
            "chest",
            "water",
            "foliage",
            "particles",
            "backdrops",
            "UI",
            "non-disabled `CollisionShape3D`",
            "non-null",
            "layers and masks",
            "XZ-only distance",
            "target's own collider",
            "**Native physics:**",
            "**Visual alignment:**",
            "**Save/reopen:**",
            "**Off-script exploration:**",
            "**Pickup height and line of sight:**",
            "**passed**",
            "**failed**",
            "**not measured**",
            "not real-input proof",
            "do not run this project-specific gameplay gate",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, text)

    def test_built_artifacts_are_a_ci_gate(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python tools/check_collision_skill_artifacts.py dist/*", workflow)

    def _write_artifact(self, path, contents):
        if path.name.endswith(".whl"):
            with zipfile.ZipFile(path, "w") as archive:
                for name, content in contents.items():
                    archive.writestr(name, content)
        else:
            with tarfile.open(path, "w:gz") as archive:
                for name, content in contents.items():
                    info = tarfile.TarInfo(f"dcc_mcp_godot-test/src/{name}")
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))

    def test_artifact_gate_accepts_exact_files_and_rejects_lost_or_stale_reference(self):
        expected = ARTIFACTS.expected_files()
        reference = f"dcc_mcp_godot/skills/{ARTIFACTS.REFERENCE}"
        with tempfile.TemporaryDirectory() as temporary:
            for extension in (".whl", ".tar.gz"):
                artifact = Path(temporary) / f"package{extension}"
                with self.subTest(extension=extension, case="valid"):
                    self._write_artifact(artifact, expected)
                    ARTIFACTS.verify_artifact(artifact, expected)
                for case in ("missing", "stale"):
                    changed = expected.copy()
                    if case == "missing":
                        changed.pop(reference)
                    else:
                        changed[reference] = b"Old instructions"
                    with self.subTest(extension=extension, case=case):
                        self._write_artifact(artifact, changed)
                        with self.assertRaisesRegex(ValueError, "collision-intent.md"):
                            ARTIFACTS.verify_artifact(artifact, expected)


if __name__ == "__main__":
    unittest.main()
