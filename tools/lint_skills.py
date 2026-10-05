from pathlib import Path

import yaml
from dcc_mcp_core import validate_skill

skills_root = Path(__file__).parents[1] / "src" / "dcc_mcp_godot" / "skills"

reports = [validate_skill(str(path)) for path in skills_root.iterdir() if path.is_dir()]
assert all(report.is_clean for report in reports), [report.issues for report in reports]

# validate_skill checks the package shape, not that the tool manifest is
# parseable by the loader that ships it. A description containing an unquoted
# ": " still passes shape validation and then breaks tools.yaml at runtime,
# which takes the whole skill's tool list down with it. Parse every manifest the
# way the runtime does before calling a skill clean.
for path in sorted(skills_root.glob("*/tools.yaml")):
    with path.open(encoding="utf-8") as stream:
        manifest = yaml.safe_load(stream)
    assert isinstance(manifest, dict), f"{path}: tools.yaml did not load as a mapping"
    tools = manifest.get("tools")
    assert isinstance(tools, list) and tools, f"{path}: tools.yaml declares no tools"
    for tool in tools:
        assert isinstance(tool, dict) and tool.get("name"), f"{path}: a tool has no name"
        assert tool.get("description"), f"{path}: tool {tool['name']} has no description"

print(f"validated {len(reports)} bundled skills")
