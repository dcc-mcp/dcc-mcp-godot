"""Host-free lifecycle tests; no live Godot or exported product is claimed."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "export_jobs_under_test", Path(__file__).parents[1] / "src/dcc_mcp_godot/export_jobs.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class Child:
    def __init__(self, command, *, duration=0.05, exit_code=0, mutate=None, **kwargs):
        self.pid = 999999999
        self.command = command
        self.returncode = None
        self.start = time.monotonic()
        self.duration = duration
        self.exit_code = exit_code
        self.mutate = mutate
        self.waited = False
        self.stopped = False
        kwargs["stdout"].write(b"complete fake export log\n")
        kwargs["stdout"].flush()

    def poll(self):
        if self.returncode is None and time.monotonic() - self.start >= self.duration:
            if self.exit_code == 0:
                Path(self.command[-1]).write_bytes(b"fake product, not native evidence")
            if self.mutate:
                self.mutate()
            self.returncode = self.exit_code
        return self.returncode

    def wait(self, timeout=None):
        self.waited = True
        if self.poll() is None:
            raise subprocess.TimeoutExpired(self.command, timeout)
        return self.returncode


def stop_fake(child):
    if child.poll() is None:
        child.stopped = True
        child.returncode = -15
    return child.wait()


class ExportJobs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "project.godot").write_text("config_version=5\n")
        (self.project / "export_presets.cfg").write_text('[preset.0]\nname="Web"\n')
        self.context = {
            "project_path": str(self.project),
            "executable": sys.executable,
            "engine_version": "fixture",
            "preset_names": ["Web"],
            "project_sha256": module.digest(self.project / "project.godot"),
            "presets_sha256": module.digest(self.project / "export_presets.cfg"),
        }
        self.params = {"preset": "Web", "path": "web/index.html", "request_id": "a" * 32}
        self.children = []
        self.managers = []
        self.stop_patch = patch.object(
            module.ExportJobManager, "_terminate", staticmethod(stop_fake)
        )
        self.stop_patch.start()

    def tearDown(self):
        for manager in self.managers:
            manager.close()
        self.stop_patch.stop()
        self.temp.cleanup()

    def manager(self, **child_options):
        def spawn(command, **kwargs):
            child = Child(command, **child_options, **kwargs)
            self.children.append(child)
            return child

        value = module.ExportJobManager(self.root / "journal", popen=spawn)
        self.managers.append(value)
        return value

    def terminal(self, manager):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            result = manager.get("a" * 32)
            if result["status"] in module.TERMINAL:
                return result
            time.sleep(0.01)
        self.fail("test job did not terminate")

    def test_success_hashes_log_and_separate_control_file(self):
        m = self.manager()
        m.start(self.params, self.context)
        r = self.terminal(m)
        self.assertEqual(r["status"], "completed")
        self.assertTrue(r["child_reaped"])
        self.assertTrue(r["log_complete"])
        self.assertEqual(r["log_sha256"], module.digest(Path(r["log_path"])))
        manifest = json.loads(Path(r["output_manifest_path"]).read_text())
        self.assertEqual([p["path"] for p in manifest["files"]], ["index.html"])
        self.assertEqual(manifest["control_files"][0]["path"], ".gdignore")
        self.assertEqual(r["output_count"], 1)

    def test_slow_start_returns_and_request_deduplicates(self):
        m = self.manager(duration=0.3)
        before = time.monotonic()
        r = m.start(self.params, self.context)
        self.assertLess(time.monotonic() - before, 0.2)
        self.assertIn(r["status"], ("queued", "running"))
        self.assertEqual(m.start(self.params, self.context)["job_id"], "a" * 32)
        self.terminal(m)
        self.assertEqual(len(self.children), 1)

    def test_conflicting_identity_and_second_active_rejected(self):
        m = self.manager(duration=0.3)
        m.start(self.params, self.context)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            m.start({**self.params, "debug": True}, self.context)
        with self.assertRaisesRegex(ValueError, "active"):
            m.start(
                {**self.params, "request_id": "b" * 32, "path": "second/index.html"}, self.context
            )

    def test_cancel_waits_owned_child(self):
        m = self.manager(duration=30)
        m.start(self.params, self.context)
        while not self.children:
            time.sleep(0.005)
        r = m.cancel("a" * 32)
        self.assertEqual(r["status"], "cancelled")
        self.assertTrue(self.children[0].waited)
        self.assertFalse(r["artifacts_accepted"])

    def test_nonzero_is_terminal_failure_with_complete_log(self):
        m = self.manager(exit_code=7)
        m.start(self.params, self.context)
        r = self.terminal(m)
        self.assertEqual((r["status"], r["exit_code"]), ("failed", 7))
        self.assertTrue(r["log_complete"])

    def test_changed_configuration_rejects_product(self):
        m = self.manager(mutate=lambda: (self.project / "project.godot").write_text("changed"))
        m.start(self.params, self.context)
        r = self.terminal(m)
        self.assertEqual(r["status"], "failed")
        self.assertFalse(r["artifacts_accepted"])
        self.assertIn("changed", r["reason"])
        self.assertEqual(r["changed_configuration_files"], ["project.godot"])
        self.assertNotEqual(
            r["configuration_after_sha256"]["project.godot"],
            r["request"]["configuration_sha256"]["project.godot"],
        )

    def test_occupied_output_and_unsafe_paths(self):
        m = self.manager()
        (self.project / "web").mkdir()
        with self.assertRaisesRegex(ValueError, "fresh"):
            m.start(self.params, self.context)
        for path in [
            "../bad/index.html",
            "/tmp/out",
            "-bad/file",
            "C:/bad/file",
            "addons/out/file",
            "index.html",
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                module.validate_start({**self.params, "path": path}, self.context)

    def test_symlink_path_is_rejected(self):
        (self.project / "link").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            module.validate_start({**self.params, "path": "link/out/index.html"}, self.context)

    def test_recovered_active_becomes_unknown_and_keeps_slot(self):
        m = self.manager()
        m.start(self.params, self.context)
        self.terminal(m)
        m.close()
        p = self.root / "journal" / ("a" * 32) / "status.json"
        r = json.loads(p.read_text())
        r["status"] = "running"
        p.write_text(json.dumps(r))
        again = self.manager()
        self.assertEqual(again.get("a" * 32)["status"], "unknown")
        with self.assertRaisesRegex(ValueError, "unresolved"):
            again.start(
                {**self.params, "request_id": "b" * 32, "path": "second/index.html"}, self.context
            )
        with self.assertRaisesRegex(ValueError, "ownership"):
            again.cancel("a" * 32)

    def test_log_cap_fails_closed(self):
        with patch.object(module, "MAX_LOG_BYTES", 1):
            m = self.manager()
            m.start(self.params, self.context)
            r = self.terminal(m)
        self.assertEqual(r["status"], "failed")
        self.assertFalse(r["log_complete"])
        self.assertTrue(r["child_reaped"])

    def test_timeout_is_not_success(self):
        m = self.manager(duration=30)
        ticks = iter([0, 100, 100, 100])
        m._clock = lambda: next(ticks, 100)
        m.start({**self.params, "timeout_seconds": 5}, self.context)
        r = self.terminal(m)
        self.assertEqual(r["status"], "timed_out")
        self.assertTrue(r["child_reaped"])

    def test_runtime_output_cap_stops_before_normal_completion(self):
        def spawn(command, **kwargs):
            child = Child(command, duration=30, **kwargs)
            Path(command[-1]).write_bytes(b"x" * 100)
            self.children.append(child)
            return child

        m = module.ExportJobManager(self.root / "journal", popen=spawn)
        self.managers.append(m)
        with patch.object(module, "MAX_OUTPUT_BYTES", 50):
            m.start(self.params, self.context)
            r = self.terminal(m)
        self.assertEqual(r["status"], "failed")
        self.assertTrue(self.children[0].stopped)
        self.assertIn("Runtime export output cap", r["reason"])

    def test_initial_journal_failure_is_known_not_spawned(self):
        m = self.manager()
        with patch.object(module, "_write_json", side_effect=OSError("injected storage failure")):
            r = m.start(self.params, self.context)
        self.assertEqual(r["status"], "failed")
        self.assertEqual(self.children, [])
        self.assertFalse((self.root / "journal" / ("a" * 32)).exists())

    def test_thread_start_failure_is_known_not_spawned(self):
        m = self.manager()
        with patch.object(
            module.threading.Thread, "start", side_effect=RuntimeError("injected thread failure")
        ):
            r = m.start(self.params, self.context)
        self.assertEqual(r["status"], "failed")
        self.assertEqual(self.children, [])
        self.assertFalse((self.root / "journal" / ("a" * 32)).exists())

    def test_start_raises_after_thread_started_is_initially_unknown(self):
        original = module.threading.Thread.start

        def start_then_raise(thread):
            original(thread)
            raise RuntimeError("injected after thread start")

        m = self.manager(duration=30)
        with patch.object(module.threading.Thread, "start", start_then_raise):
            receipt = m.start(self.params, self.context)
        self.assertEqual(receipt["status"], "unknown")
        m.close()
        self.assertFalse(m.get("a" * 32)["artifacts_accepted"])

    def test_final_log_hash_failure_keeps_terminal_failure(self):
        original = module.digest

        def fail_log(path):
            if path.name == "export.log":
                raise OSError("injected log evidence failure")
            return original(path)

        m = self.manager()
        with patch.object(module, "digest", fail_log):
            m.start(self.params, self.context)
            receipt = self.terminal(m)
        self.assertEqual(receipt["status"], "failed")
        self.assertTrue(receipt["child_reaped"])
        self.assertFalse(receipt["log_complete"])
        self.assertFalse(receipt["artifacts_accepted"])

    def test_incomplete_journal_keeps_all_projects_blocked(self):
        (self.root / "journal" / ("b" * 32)).mkdir(parents=True)
        m = self.manager()
        self.assertEqual(m.get("b" * 32)["status"], "unknown")
        with self.assertRaisesRegex(ValueError, "unresolved"):
            m.start(self.params, self.context)

    def test_persistence_after_spawn_fails_closed(self):
        original = module._write_json

        def fail_running(path, value):
            if value.get("status") == "running":
                raise OSError("injected post-spawn failure")
            return original(path, value)

        m = self.manager(duration=30)
        with patch.object(module, "_write_json", side_effect=fail_running):
            m.start(self.params, self.context)
            r = self.terminal(m)
        self.assertEqual(r["status"], "failed")
        self.assertTrue(self.children[0].waited)
        self.assertFalse(r["artifacts_accepted"])

    def test_cleanup_uncertainty_keeps_slot(self):
        m = self.manager()
        with patch.object(m, "_terminate", side_effect=RuntimeError("unreaped")):
            m.start(self.params, self.context)
            r = self.terminal(m)
        self.assertEqual(r["status"], "unknown")
        self.assertFalse(r["artifacts_accepted"])
        with self.assertRaisesRegex(ValueError, "unresolved"):
            m.start(
                {**self.params, "request_id": "b" * 32, "path": "second/index.html"}, self.context
            )


@unittest.skipUnless(os.name == "posix", "POSIX process-group lifecycle")
class RealProcessLifecycle(unittest.TestCase):
    def test_real_cancel_terminates_and_reaps_owned_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "project.godot").write_text("config_version=5\n")
            (root / "export_presets.cfg").write_text('[preset.0]\nname="Web"\n')
            context = {
                "project_path": str(root),
                "executable": sys.executable,
                "preset_names": ["Web"],
                "engine_version": "process fixture",
                "project_sha256": module.digest(root / "project.godot"),
                "presets_sha256": module.digest(root / "export_presets.cfg"),
            }
            children = []

            def spawn(command, **kwargs):
                child = subprocess.Popen(
                    [sys.executable, "-c", "import time; time.sleep(30)"], **kwargs
                )
                children.append(child)
                return child

            manager = module.ExportJobManager(root / "journal", popen=spawn)
            try:
                manager.start(
                    {"preset": "Web", "path": "web/index.html", "request_id": "a" * 32}, context
                )
                deadline = time.monotonic() + 3
                while not children and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(len(children), 1)
                while manager.get("a" * 32)["status"] == "queued" and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(manager.get("a" * 32)["status"], "running")
                # A genuine second adapter process shares this registry while the
                # first owns an actual live child. It cannot reach a second spawn.
                record_path = root / "journal" / ("a" * 32) / "status.json"
                before = record_path.read_bytes()
                competitor = r"""
import importlib.util, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("jobs",sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
try:
    manager=m.ExportJobManager(Path(sys.argv[2]))
except RuntimeError as error:
    assert "busy" in str(error)
    print("BUSY_NO_SPAWN")
else:
    manager.close()
    raise AssertionError("second adapter acquired owned journal")
"""
                other = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        competitor,
                        str(Path(module.__file__)),
                        str(root / "journal"),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                self.assertEqual(other.returncode, 0, other.stderr)
                self.assertEqual(other.stdout.strip(), "BUSY_NO_SPAWN")
                self.assertEqual(record_path.read_bytes(), before)
                receipt = manager.cancel("a" * 32)
                self.assertEqual(receipt["status"], "cancelled")
                self.assertTrue(receipt["child_reaped"])
                self.assertTrue(receipt["descendant_cleanup_confirmed"])
                self.assertIsNotNone(children[0].returncode)
                with self.assertRaises(ProcessLookupError):
                    os.killpg(children[0].pid, 0)
            finally:
                manager.close()

    def test_two_processes_share_registry_without_mutation_and_crash_recovers_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = root / "journal"
            holder_script = r"""
import importlib.util, json, sys, time
from pathlib import Path
spec = importlib.util.spec_from_file_location("jobs", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
manager = m.ExportJobManager(Path(sys.argv[2]))
# Persisted running record is an explicit crash-recovery fixture, not an export claim.
folder = Path(sys.argv[2]) / ("a" * 32); folder.mkdir()
m._write_json(folder / "status.json", {
    "job_id":"a"*32, "status":"running", "request":{"project_path":sys.argv[3]},
    "artifacts_accepted":False, "child_reaped":False, "exit_code":None})
print("LOCKED", flush=True)
time.sleep(30)
"""
            holder = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    holder_script,
                    str(Path(module.__file__)),
                    str(journal),
                    str(root),
                ],
                stdout=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertEqual(holder.stdout.readline().strip(), "LOCKED")
                status = journal / ("a" * 32) / "status.json"
                before = status.read_bytes()
                with self.assertRaisesRegex(RuntimeError, "busy"):
                    module.ExportJobManager(journal)
                self.assertEqual(status.read_bytes(), before)
                # A second process cannot reach start/spawn for any output in this registry.
                self.assertEqual(json.loads(before)["status"], "running")
            finally:
                holder.kill()
                holder.wait(timeout=3)
                holder.stdout.close()
            recovered = module.ExportJobManager(journal)
            try:
                self.assertEqual(recovered.get("a" * 32)["status"], "unknown")
                (root / "project.godot").write_text("config_version=5")
                (root / "export_presets.cfg").write_text("preset")
                context = {
                    "project_path": str(root),
                    "executable": sys.executable,
                    "preset_names": ["Web"],
                    "project_sha256": module.digest(root / "project.godot"),
                    "presets_sha256": module.digest(root / "export_presets.cfg"),
                }
                with self.assertRaisesRegex(ValueError, "unresolved"):
                    recovered.start(
                        {"preset": "Web", "path": "web/index.html", "request_id": "b" * 32}, context
                    )
            finally:
                recovered.close()

    @unittest.skipUnless(sys.platform == "linux", "isolated Linux subreaper fixture")
    def test_real_exited_parent_with_live_descendant_retains_unknown_slot(self):
        # The isolated test supervisor alone becomes a subreaper, allowing it to reap
        # its deliberately orphaned fixture. No process outside this fixture is signalled.
        script = r"""
import ctypes, importlib.util, json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path
assert ctypes.CDLL(None).prctl(36, 1, 0, 0, 0) == 0
spec = importlib.util.spec_from_file_location("jobs", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    (root / "project.godot").write_text("config_version=5")
    (root / "export_presets.cfg").write_text("preset")
    context = {"project_path": str(root), "executable": sys.executable,
               "preset_names": ["Web"], "engine_version": "real descendant fixture",
               "project_sha256": m.digest(root / "project.godot"),
               "presets_sha256": m.digest(root / "export_presets.cfg")}
    pidfile = root / "descendant.pid"
    parent_code = ("import subprocess,sys; from pathlib import Path; "
                   "p=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
                   "Path(sys.argv[1]).write_text(str(p.pid)); "
                   "Path(sys.argv[2]).write_bytes(b'fixture')")
    children = []
    def spawn(command, **kwargs):
        child = subprocess.Popen(
            [sys.executable, "-c", parent_code, str(pidfile), command[-1]], **kwargs)
        children.append(child)
        return child
    manager = m.ExportJobManager(root / "journal", popen=spawn)
    try:
        manager.start({"preset":"Web", "path":"web/index.html", "request_id":"a"*32}, context)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            receipt = manager.get("a"*32)
            if receipt["status"] in m.TERMINAL:
                break
            time.sleep(.02)
        assert receipt["status"] == "unknown", receipt
        assert not receipt["artifacts_accepted"]
        assert not receipt["descendant_cleanup_confirmed"]
        assert children[0].returncode == 0
        os.kill(int(pidfile.read_text()), 0)  # Actual descendant remains live.
        try:
            manager.start({"preset":"Web", "path":"next/index.html", "request_id":"b"*32}, context)
        except ValueError as error:
            assert "unresolved" in str(error)
        else:
            raise AssertionError("unknown job released its slot")
        print(json.dumps({"status":receipt["status"], "parent_exit":children[0].returncode,
                          "descendant_alive":True}))
    finally:
        manager.close()
        if pidfile.exists():
            pid = int(pidfile.read_text())
            os.kill(pid, signal.SIGTERM)
            assert os.waitpid(pid, 0)[0] == pid
"""
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script), str(Path(module.__file__))],
            text=True,
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt, {"status": "unknown", "parent_exit": 0, "descendant_alive": True})


if __name__ == "__main__":
    unittest.main()
