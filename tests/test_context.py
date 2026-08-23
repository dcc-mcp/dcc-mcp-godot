import threading

from dcc_mcp_godot.context import GodotContextMonitor, GodotContextPublisher


def test_context_publisher_reads_typed_host_snapshot_and_updates_gateway_metadata():
    host_calls = []
    published = []

    def call_host(method):
        host_calls.append(method)
        return {
            "version": "4.4.1.stable",
            "display_name": "Scene Context Test",
            "scene": "res://levels/current.tscn",
            "documents": ["res://levels/current.tscn", "res://ui/menu.tscn"],
        }

    publisher = GodotContextPublisher(
        call_host=call_host,
        publish=lambda **context: published.append(context) or True,
    )

    assert publisher.refresh() is True
    assert host_calls == ["context.snapshot"]
    assert published == [
        {
            "version": "4.4.1.stable",
            "display_name": "Scene Context Test",
            "scene": "res://levels/current.tscn",
            "documents": ["res://levels/current.tscn", "res://ui/menu.tscn"],
        }
    ]


def test_context_publisher_rejects_incomplete_host_snapshot_without_erasing_metadata():
    published = []
    publisher = GodotContextPublisher(
        call_host=lambda _method: {
            "version": "unknown",
            "display_name": "",
            "scene": "res://current.tscn",
            "documents": ["res://current.tscn"],
        },
        publish=lambda **context: published.append(context) or True,
    )

    assert publisher.refresh() is False
    assert published == []


def test_context_monitor_waits_for_connection_then_refreshes_and_stops():
    connected = threading.Event()
    refreshed = threading.Event()
    refresh_count = 0

    class Publisher:
        def refresh(self):
            nonlocal refresh_count
            refresh_count += 1
            refreshed.set()
            return True

    monitor = GodotContextMonitor(
        Publisher(),
        is_connected=connected.is_set,
        poll_interval_secs=0.01,
    )
    monitor.start()
    assert not refreshed.wait(0.05)
    connected.set()
    assert refreshed.wait(0.5)
    monitor.stop()
    stopped_count = refresh_count
    assert not monitor.is_running
    assert refresh_count == stopped_count


def test_context_monitor_reports_transient_host_failure_and_can_retry(caplog):
    attempts = 0

    class Publisher:
        def refresh(self):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("editor is reloading")
            return True

    monitor = GodotContextMonitor(Publisher(), is_connected=lambda: True)

    assert monitor.refresh() is False
    assert "editor is reloading" in caplog.text
    assert monitor.refresh() is True
