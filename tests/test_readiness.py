from dcc_mcp_godot.readiness import BridgeReadinessMonitor


class RecordingBinder:
    def __init__(self):
        self.states = []

    def mark_dispatcher_ready(self, ready, **kwargs):
        self.states.append({"dispatcher": ready, **kwargs})


def test_bridge_readiness_tracks_disconnect_and_reconnect():
    connected = [False]
    binder = RecordingBinder()
    monitor = BridgeReadinessMonitor(binder, lambda: connected[0])

    assert monitor.refresh() is False
    assert binder.states[-1] == {
        "dispatcher": True,
        "dcc_ready": False,
        "host_execution_bridge_ready": False,
        "main_thread_executor_ready": False,
    }

    connected[0] = True
    assert monitor.refresh() is True
    assert binder.states[-1]["dcc_ready"] is True
    assert binder.states[-1]["host_execution_bridge_ready"] is True
    assert binder.states[-1]["main_thread_executor_ready"] is True

    monitor.stop()
    assert binder.states[-1]["dcc_ready"] is False
