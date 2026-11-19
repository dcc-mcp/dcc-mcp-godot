from __future__ import annotations

import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from dcc_mcp_core.skill import skill_entry, skill_success
from dcc_mcp_godot.bridge import call_host

ALLOWED_PROPERTIES = {
    "priority", "follow_damping", "look_at_damping", "follow_offset",
    "look_at_offset", "dead_zone_width", "dead_zone_height",
    "dead_zone_depth", "blend_duration", "tween_duration",
}


def project_path() -> Path:
    result = call_host("project.inspect", {})
    path = Path(str(result.get("project_path", ""))).resolve()
    if not path.is_dir():
        raise ValueError("Connected Godot project path is unavailable")
    return path


def scene_tree() -> dict[str, Any]:
    result = call_host("scene.inspect", {})
    if result.get("__error__"):
        raise ValueError(str(result["__error__"]))
    return result


def walk(node: dict[str, Any]):
    yield node
    for child in node.get("children", []):
        yield from walk(child)


def find_type(tree: dict[str, Any], type_name: str, name: str = ""):
    for node in walk(tree.get("root", {})):
        if node.get("type") == type_name and (not name or node.get("name") == name):
            return node
    return None


def inspect_camera(_params: dict[str, Any]) -> dict[str, Any]:
    project = project_path()
    cfg = project / "addons" / "phantom_camera" / "plugin.cfg"
    version = ""
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version="):
                version = line.split("=", 1)[1].strip().strip('"')
                break
    tree = scene_tree()
    return {
        "installed": cfg.is_file(),
        "version": version,
        "project_path": str(project),
        "hosts": [n for n in walk(tree.get("root", {})) if n.get("type") == "PhantomCameraHost"],
        "cameras": [
            n for n in walk(tree.get("root", {}))
            if n.get("type") in {"PhantomCamera2D", "PhantomCamera3D"}
        ],
        "scene_path": tree.get("scene_path", ""),
    }


def safe_extract(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as zf:
        root = destination.resolve()
        for member in zf.infolist():
            target = (destination / member.filename).resolve()
            if not str(target).startswith(str(root) + str(Path.sep)):
                raise ValueError("Phantom Camera archive contains an unsafe path")
        zf.extractall(destination)
    roots = [p for p in destination.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise ValueError("Unexpected Phantom Camera archive layout")
    addon = roots[0] / "addons" / "phantom_camera"
    if not (addon / "plugin.cfg").is_file():
        raise ValueError("Downloaded archive lacks addons/phantom_camera/plugin.cfg")
    return addon


def install_camera(params: dict[str, Any]) -> dict[str, Any]:
    version = str(params["version"])
    if version not in {"v0.11", "v0.11.0.1", "v0.11.0.2", "v0.11.0.3", "v0.11.0.4"}:
        raise ValueError("Only verified Phantom Camera tags are allowed: v0.11, v0.11.0.1, v0.11.0.2, v0.11.0.3, v0.11.0.4")
    project = project_path()
    destination = project / "addons" / "phantom_camera"
    if destination.exists() and not bool(params.get("replace_existing", False)):
        raise ValueError("Phantom Camera already installed; set replace_existing=true to replace it")
    with tempfile.TemporaryDirectory(prefix="dcc-mcp-phantom-camera-") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "phantom-camera.zip"
        url = f"https://github.com/ramokz/phantom-camera/archive/refs/tags/{version}.zip"
        request = urllib.request.Request(url, headers={"User-Agent": "dcc-mcp-godot"})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        addon = safe_extract(archive, tmp_path / "unpacked")
        if destination.exists():
            backup = project / "addons" / ".phantom_camera.backup"
            if backup.exists():
                shutil.rmtree(backup)
            destination.rename(backup)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(addon, destination)
    refresh = call_host("assets.refresh", {})
    enabled = call_host("assets.set_plugin_enabled", {"plugin_name": "phantom_camera", "enabled": True})
    return {
        "installed": True,
        "version": version,
        "plugin_cfg_sha256": hashlib.sha256((destination / "plugin.cfg").read_bytes()).hexdigest(),
        "refresh": refresh,
        "enabled": enabled,
    }


def configure_camera(params: dict[str, Any]) -> dict[str, Any]:
    inspection = inspect_camera({})
    if not inspection["installed"]:
        raise ValueError("Phantom Camera is not installed; run install first")
    tree = scene_tree()
    camera_name = str(params.get("camera_name", "Camera3D"))
    host_name = str(params.get("host_name", "PhantomCameraHost"))
    phantom_name = str(params.get("phantom_name", "PhantomCamera3D"))
    camera = find_type(tree, "Camera3D", camera_name)
    camera_path = str(camera["path"]) if camera else str(call_host(
        "scene.create_node", {"type": "Camera3D", "parent_path": ".", "name": camera_name}
    )["path"])
    host = find_type(scene_tree(), "PhantomCameraHost", host_name)
    host_path = str(host["path"]) if host else str(call_host(
        "scene.create_node", {"type": "PhantomCameraHost", "parent_path": camera_path, "name": host_name}
    )["path"])
    phantom = find_type(scene_tree(), "PhantomCamera3D", phantom_name)
    phantom_path = str(phantom["path"]) if phantom else str(call_host(
        "scene.create_node", {"type": "PhantomCamera3D", "parent_path": host_path, "name": phantom_name}
    )["path"])
    updates = {"priority": int(params.get("priority", 10))}
    for key, value in dict(params.get("properties") or {}).items():
        if key not in ALLOWED_PROPERTIES:
            raise ValueError(f"Property is not allowlisted: {key}")
        updates[key] = value
    applied = [
        call_host("scene.set_property", {"node_path": phantom_path, "property": key, "value": value})
        for key, value in updates.items()
    ]
    saved = call_host("scene.save", {}) if bool(params.get("save_scene", False)) else None
    return {
        "configured": True, "version": inspection["version"],
        "camera_path": camera_path, "host_path": host_path,
        "phantom_camera_path": phantom_path, "applied": applied,
        "saved": saved, "readback": inspect_camera({}),
    }


@skill_entry
def main(_action_name: str = "", **params):
    action = (_action_name or "").rsplit("__", 1)[-1]
    if action == "inspect":
        return skill_success("Phantom Camera inspection completed.", **inspect_camera(params))
    if action == "install":
        return skill_success("Phantom Camera installed.", **install_camera(params))
    if action == "configure":
        return skill_success("Phantom Camera configured.", **configure_camera(params))
    raise ValueError(f"Unknown Phantom Camera action: {action}")
