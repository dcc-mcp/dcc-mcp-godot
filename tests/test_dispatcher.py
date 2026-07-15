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


def test_dispatcher_exposes_action_name_to_shared_skill_script():
    dispatcher = GodotBridgeDispatcher()
    from dcc_mcp_godot.capability_dispatch import current_action_name

    assert (
        dispatcher.dispatch_callable(
            current_action_name.get,
            action_name="get_project_info",
        )
        == "get_project_info"
    )
