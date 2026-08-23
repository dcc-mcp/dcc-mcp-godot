from dcc_mcp_godot import bridge


class FakeBridge:
    def call(self, method, **params):
        return {"method": method, "params": params}


def test_call_host_uses_typed_method_and_parameters(monkeypatch):
    monkeypatch.setattr(bridge, "_bridge", FakeBridge())
    assert bridge.call_host("scene.inspect", {"depth": 2}) == {
        "method": "scene.inspect",
        "params": {"depth": 2},
    }


def test_call_host_preserves_public_target_method_without_colliding_with_bridge_method(
    monkeypatch,
):
    monkeypatch.setattr(bridge, "_bridge", FakeBridge())

    assert bridge.call_host(
        "capability.execute_editor_script", {"method": "run", "arguments": {}}
    ) == {
        "method": "capability.execute_editor_script",
        "params": {"__method__": "run", "arguments": {}},
    }
