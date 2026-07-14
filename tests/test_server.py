from dcc_mcp_godot.server import GodotMcpServer


def test_server_wires_http_main_affinity_dispatcher():
    server = GodotMcpServer(port=0)
    try:
        assert server._execution_bridge.resolve_host_dispatcher() is server._host_dispatcher
    finally:
        server.stop()
