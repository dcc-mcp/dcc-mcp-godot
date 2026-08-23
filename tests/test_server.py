from dcc_mcp_godot.server import GodotMcpServer


def test_server_wires_http_main_affinity_dispatcher():
    server = GodotMcpServer(port=0)
    try:
        assert server._execution_bridge.resolve_host_dispatcher() is server._host_dispatcher
    finally:
        server.stop()


def test_server_starts_with_disconnected_godot_bridge_not_ready():
    server = GodotMcpServer(port=0)
    try:
        report = server._readiness_binder.report_subset()
        assert report["process"] is True
        assert report["skill_catalog"] is True
        assert report["dcc"] is False
        assert report["host_execution_bridge"] is False
        assert report["main_thread_executor"] is False
    finally:
        server.stop()


def test_server_context_publisher_routes_typed_editor_snapshot_to_core(monkeypatch):
    from dcc_mcp_godot import server as server_module

    published = []
    monkeypatch.setattr(
        server_module,
        "call_host",
        lambda method: {
            "version": "4.4.1.stable",
            "display_name": "Server Context Test",
            "scene": "res://main.tscn",
            "documents": ["res://main.tscn"],
        },
        raising=False,
    )
    monkeypatch.setattr(
        server_module.GodotMcpServer,
        "update_gateway_metadata",
        lambda self, **context: published.append(context) or True,
    )

    server = server_module.GodotMcpServer(port=0)
    try:
        assert server._context_publisher.refresh() is True
    finally:
        server.stop()

    assert published == [
        {
            "version": "4.4.1.stable",
            "display_name": "Server Context Test",
            "scene": "res://main.tscn",
            "documents": ["res://main.tscn"],
        }
    ]


def test_start_server_defers_port_resolution_to_core(monkeypatch):
    from types import SimpleNamespace

    from dcc_mcp_godot import server as server_module

    ports = []
    stub = SimpleNamespace(
        is_running=False,
        register_builtin_actions=lambda: None,
        start=lambda: None,
        stop=lambda: None,
    )

    monkeypatch.setattr(server_module, "_server", None)
    monkeypatch.setattr(
        server_module, "GodotMcpServer", lambda port=None: ports.append(port) or stub
    )
    monkeypatch.setenv("DCC_MCP_GODOT_PORT", "8765")

    server_module.start_server(0)
    server_module.stop_server()
    server_module.start_server()
    server_module.stop_server()

    assert ports == [0, None]
