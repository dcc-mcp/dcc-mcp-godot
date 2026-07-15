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
