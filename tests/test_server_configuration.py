"""Constructor contract checks; no server or native editor is started."""

import inspect

import pytest
from dcc_mcp_core import DccServerOptions

from dcc_mcp_godot.server import GodotMcpServer


@pytest.fixture
def isolated_core_environment(monkeypatch, tmp_path):
    for name, value in {
        "DCC_MCP_LOG_DIR": str(tmp_path / "logs"),
        "DCC_MCP_REGISTRY_DIR": str(tmp_path / "registry"),
        "DCC_MCP_JOB_STORAGE_PATH": str(tmp_path / "jobs.sqlite"),
        "DCC_MCP_DISABLE_TELEMETRY": "1",
        "DCC_MCP_DISABLE_JOB_PERSISTENCE": "1",
        "DCC_MCP_CHECKPOINT_IN_MEMORY": "1",
    }.items():
        monkeypatch.setenv(name, value)
    return tmp_path


def test_constructor_exposes_only_supported_core_options():
    adapter = inspect.signature(GodotMcpServer)
    core = inspect.signature(DccServerOptions.from_env)
    for name, parameter in adapter.parameters.items():
        assert name in core.parameters
        assert parameter.default == core.parameters[name].default
    for owned in (
        "dcc_name",
        "server_name",
        "server_version",
        "builtin_skills_dir",
        "execution_bridge",
        "dispatcher",
        "standalone_main_thread",
        "options",
    ):
        with pytest.raises(TypeError):
            GodotMcpServer(**{owned: None})


def test_explicit_configuration_is_resolved_without_starting(isolated_core_environment):
    root = isolated_core_environment
    server = GodotMcpServer(
        port=0,
        gateway_port=0,
        registry_dir=str(root / "registry"),
        enable_gateway_failover=False,
        strict_gateway=True,
        enable_file_logging=False,
        enable_job_persistence=False,
        enable_telemetry=False,
        enable_checkpoint_persistence=False,
        enable_checkpoint_tools=False,
        job_retention_hours=2,
        checkpoint_path=str(root / "checkpoint.json"),
    )
    try:
        options = server.options
        assert options.port == 0
        assert options.dcc_name == "godot"
        assert options.server_name == "dcc-mcp-godot"
        assert options.builtin_skills_dir.name == "skills"
        assert options.gateway.port == 0
        assert options.gateway.registry_dir == str(root / "registry")
        assert options.gateway.enable_failover is False
        assert options.gateway.strict_gateway is True
        assert options.observability.enable_file_logging is False
        assert options.observability.enable_job_persistence is False
        assert options.observability.enable_telemetry is False
        assert options.observability.enable_checkpoint_persistence is False
        assert options.observability.enable_checkpoint_tools is False
        assert options.observability.job_retention_hours == 2
        assert options.observability.checkpoint_path == str(root / "checkpoint.json")
        assert server.is_running is False
        assert server._execution_bridge.resolve_host_dispatcher() is server._host_dispatcher
        with pytest.raises(AttributeError):
            server.options = options
    finally:
        server.stop()
