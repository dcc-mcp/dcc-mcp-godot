from dcc_mcp_godot.dispatcher import GodotBridgeDispatcher


def test_dispatcher_removes_core_metadata():
    dispatcher = GodotBridgeDispatcher()
    assert (
        dispatcher.dispatch_callable(
            lambda value=7: value,
            affinity="main",
            action_name="test",
            timeout_hint_secs=5,
        )
        == 7
    )
