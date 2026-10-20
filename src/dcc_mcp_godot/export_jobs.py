"""Bounded adapter-owned export children; no long operation runs on Godot's editor tick."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

TERMINAL = frozenset({"completed", "failed", "cancelled", "timed_out", "unknown"})
MAX_RECORDS = 32
MAX_LOG_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 512 * 1024 * 1024
MAX_OUTPUT_FILES = 256
MIN_FREE_BYTES = 64 * 1024 * 1024
RESOURCE_POLL_SECONDS = 0.5


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _identity(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise ValueError("job/request ID must be 32 lower-case hexadecimal characters")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(path)


def validate_start(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if set(params) - {"preset", "path", "request_id", "debug", "timeout_seconds"}:
        raise ValueError("Unknown export job parameter")
    identifier = _identity(params.get("request_id"))
    preset = params.get("preset")
    if not isinstance(preset, str) or not preset or len(preset) > 500:
        raise ValueError("A named preset is required")
    if preset not in context.get("preset_names", []):
        raise ValueError("Preset is absent from the actual open project")
    relative = params.get("path")
    if not isinstance(relative, str) or not relative or len(relative) > 500:
        raise ValueError("A bounded project-relative export path is required")
    if relative.startswith(("/", "\\", "-")) or ":" in relative or "\\" in relative:
        raise ValueError("Export path must be project-relative without options or drive prefixes")
    parts = Path(relative).parts
    if any(part in {".", ".."} or part.startswith("-") for part in parts) or len(parts) < 2:
        raise ValueError("Export needs a dedicated project-relative output directory")
    if parts[0] in {".godot", "addons"}:
        raise ValueError("Export cannot target editor metadata or addons")
    debug = params.get("debug", False)
    timeout = params.get("timeout_seconds", 600)
    if type(debug) is not bool or type(timeout) is not int or not 5 <= timeout <= 1800:
        raise ValueError("debug must be boolean and timeout_seconds an integer in [5, 1800]")
    project = Path(context["project_path"])
    engine = Path(context["executable"])
    if not project.is_absolute() or not engine.is_absolute():
        raise ValueError("Actual host must return absolute project and engine paths")
    project = project.resolve(strict=True)
    if not engine.is_file():
        raise ValueError("Actual host engine executable is not available to this adapter")
    target = project.joinpath(*parts)
    for parent in (target, *target.parents):
        if parent == project:
            break
        if parent.is_symlink():
            raise ValueError("Export path may not traverse symlinks")
    try:
        target.resolve().relative_to(project)
    except ValueError as error:
        raise ValueError("Export target escaped the project") from error
    configs = {}
    for name, field in (
        ("project.godot", "project_sha256"),
        ("export_presets.cfg", "presets_sha256"),
    ):
        path = project / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError("Expected bounded saved project/preset configuration")
        configs[name] = digest(path)
        if configs[name] != context.get(field):
            raise ValueError("Saved project configuration changed after host validation")
    return {
        "job_id": identifier,
        "preset": preset,
        "path": relative,
        "debug": debug,
        "timeout_seconds": timeout,
        "project_path": str(project),
        "executable": str(engine),
        "engine_version": context.get("engine_version"),
        "configuration_sha256": configs,
    }


class _JournalLock:
    """Nonblocking OS ownership; the stable lock file is never unlinked."""

    def __init__(self, directory: Path):
        path = directory / "owner.lock"
        if path.is_symlink():
            raise ValueError("Export journal lock must not be a symlink")
        self.stream = path.open("a+b")
        try:
            if os.name == "posix":
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif os.name == "nt":
                import msvcrt

                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                raise RuntimeError("Export journal ownership is unsupported on this platform")
        except Exception as error:
            self.stream.close()
            raise RuntimeError(
                "Export journal busy or lock unavailable; another adapter may own it"
            ) from error

    def close(self) -> None:
        if self.stream.closed:
            return
        if os.name == "posix":
            import fcntl

            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        else:
            import msvcrt

            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.stream.close()


class ExportJobManager:
    """One adapter's small journal and owned child set; historical PIDs never grant ownership."""

    def __init__(self, directory: Path, *, popen=subprocess.Popen, clock=time.monotonic):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._popen = popen
        self._clock = clock
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._closed = False
        # Acquisition precedes reading or recovering any journal record. The manager
        # is lazy, so lock contention never prevents normal adapter startup/tools.
        self._journal_lock = _JournalLock(self.directory)
        try:
            self._load_records()
        except Exception:
            self._journal_lock.close()
            raise

    def _load_records(self) -> None:
        folders = [p for p in self.directory.iterdir() if p.is_dir()]
        if len(folders) > MAX_RECORDS:
            raise ValueError(
                "Export journal retention limit exceeded; retain/clear terminal records explicitly"
            )
        for folder in folders:
            identifier = _identity(folder.name)
            path = folder / "status.json"
            if not path.exists() and not folder.is_symlink():
                record = {
                    "job_id": identifier,
                    "status": "unknown",
                    "request": {"project_path": ""},
                    "reason": (
                        "Incomplete journal: child ownership and source project "
                        "cannot be established"
                    ),
                    "artifacts_accepted": False,
                    "child_reaped": False,
                    "exit_code": None,
                }
                self._jobs[identifier] = {
                    "record": record,
                    "cancel": threading.Event(),
                    "thread": None,
                    "process": None,
                }
                continue
            if folder.is_symlink() or path.is_symlink() or path.stat().st_size > 64 * 1024:
                raise ValueError("Invalid export journal")
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("job_id") != identifier or record.get("status") not in TERMINAL | {
                "queued",
                "running",
            }:
                raise ValueError("Malformed export journal record")
            if record["status"] not in TERMINAL:
                record.update(
                    status="unknown", reason="Adapter restarted without live child ownership"
                )
                _write_json(path, record)
            self._jobs[identifier] = {
                "record": record,
                "cancel": threading.Event(),
                "thread": None,
                "process": None,
            }

    def _persist(self, job: dict[str, Any]) -> None:
        _write_json(self.directory / job["record"]["job_id"] / "status.json", job["record"])

    def start(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        request = validate_start(params, context)
        identifier = request["job_id"]
        with self._lock:
            if self._closed:
                raise RuntimeError("Export manager is closed")
            if identifier in self._jobs:
                old = self._jobs[identifier]["record"]
                if old["request"] != request:
                    raise ValueError("Conflicting reuse of export request ID")
                return self.get(identifier)
            if len(self._jobs) >= MAX_RECORDS:
                raise ValueError("Export journal retention limit reached")
            for job in self._jobs.values():
                old = job["record"]
                if old["request"]["project_path"] in {"", request["project_path"]} and old[
                    "status"
                ] in {"queued", "running", "unknown"}:
                    raise ValueError("Project already has an active or unresolved export")
            output = Path(request["project_path"]) / request["path"]
            if output.parent.exists():
                raise ValueError("Output directory must be fresh, not an existing directory")
            folder = self.directory / identifier
            folder.mkdir()  # Exclusive reservation; never overwrite a previous request journal.
            record = {
                "job_id": identifier,
                "status": "queued",
                "request": request,
                "exit_code": None,
                "child_reaped": False,
                "artifacts_accepted": False,
            }
            job = {"record": record, "cancel": threading.Event(), "thread": None, "process": None}
            self._jobs[identifier] = job
            try:
                self._persist(job)
                thread = threading.Thread(
                    target=self._run,
                    args=(job,),
                    daemon=True,
                    name=f"godot-export-{identifier[:8]}",
                )
                job["thread"] = thread
                thread.start()
            except Exception as error:
                thread = job["thread"]
                if thread is not None and (thread.ident is not None or thread.is_alive()):
                    job["cancel"].set()
                    record.update(
                        status="unknown", reason=f"Thread startup outcome uncertain: {error}"
                    )
                    try:
                        self._persist(job)
                    except Exception:
                        pass
                else:
                    # No worker ever started: cleanup only the just-created journal's own files.
                    job["thread"] = None
                    record.update(
                        status="failed", reason=f"No child spawned: {error}", child_reaped=True
                    )
                    try:
                        for name in ("status.json", "status.tmp"):
                            (folder / name).unlink(missing_ok=True)
                        folder.rmdir()
                    except OSError as cleanup_error:
                        record.update(
                            status="unknown",
                            reason=(
                                "No child spawned, but reservation cleanup uncertain: "
                                f"{cleanup_error}"
                            ),
                        )
            return self.get(identifier)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(_identity(job_id))
            if job is None:
                raise ValueError("Unknown export job ID")
            # JSON copy keeps callers from mutating manager ownership/state.
            return json.loads(json.dumps(job["record"]))

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(_identity(job_id))
            if job is None:
                raise ValueError("Unknown export job ID")
            if job["record"]["status"] == "unknown":
                raise ValueError(
                    "No live process ownership; inspect uncertain export, "
                    "do not kill historical PID"
                )
            job["cancel"].set()
            thread = job["thread"]
        if thread is not None:
            thread.join(timeout=12)
        return self.get(job_id)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            jobs = list(self._jobs.values())
            for job in jobs:
                job["cancel"].set()
        for job in jobs:
            if job["thread"] is not None:
                job["thread"].join(timeout=12)
        if any(job["thread"] is not None and job["thread"].is_alive() for job in jobs):
            raise RuntimeError("Export child shutdown remains uncertain")
        self._journal_lock.close()

    @staticmethod
    def _terminate(process) -> int:
        def send(sig):
            if os.name == "posix":
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                (process.terminate if sig == signal.SIGTERM else process.kill)()

        if process.poll() is None:
            send(signal.SIGTERM)
        try:
            result = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            send(getattr(signal, "SIGKILL", 9))
            result = process.wait(timeout=5)
        if os.name == "posix":
            deadline = time.monotonic() + 5
            while True:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    break
                # Parent is already reaped: never signal a possibly recycled group ID.
                if time.monotonic() >= deadline:
                    raise RuntimeError("Owned export process group has not disappeared")
                time.sleep(0.05)
        return result

    def _run(self, job: dict[str, Any]) -> None:
        record = json.loads(json.dumps(job["record"]))
        request = record["request"]
        folder = self.directory / record["job_id"]
        project = Path(request["project_path"])
        target = project / request["path"]
        log_path = folder / "export.log"
        process = None
        final_status = "failed"
        try:
            if job["cancel"].is_set():
                final_status = "cancelled"
                return
            for name, expected in request["configuration_sha256"].items():
                if digest(project / name) != expected:
                    raise ValueError("Saved configuration changed before export spawn")
            if shutil.disk_usage(project).free < MAX_OUTPUT_BYTES + MIN_FREE_BYTES:
                raise ValueError(
                    "Insufficient free disk for bounded export output and safety reserve"
                )
            target.parent.parent.mkdir(parents=True, exist_ok=True)
            staging = target.parent.parent / (".dcc-export-" + record["job_id"])
            staging.mkdir()
            (staging / ".gdignore").write_bytes(b"")
            if target.parent.exists():
                raise ValueError("Export output directory became occupied before spawn")
            staging.rename(
                target.parent
            )  # .gdignore is present before the visible directory appears.
            command = [
                request["executable"],
                "--path",
                str(project),
                "--headless",
                "--export-debug" if request["debug"] else "--export-release",
                request["preset"],
                str(target),
            ]
            with log_path.open("xb") as stream:
                process = self._popen(
                    command,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=os.name == "posix",
                )
                job["process"] = process
                with self._lock:
                    record.update(status="running", pid=process.pid)
                    job["record"] = json.loads(json.dumps(record))
                    self._persist(job)
                started = self._clock()
                last_resource_check = started - RESOURCE_POLL_SECONDS
                while process.poll() is None:
                    if job["cancel"].is_set():
                        final_status = "cancelled"
                        break
                    if self._clock() - started >= request["timeout_seconds"]:
                        final_status = "timed_out"
                        break
                    if self._clock() - last_resource_check >= RESOURCE_POLL_SECONDS:
                        sizes = self._output_sizes(target.parent)
                        record["last_output_sample"] = sizes
                        with self._lock:
                            job["record"].update(
                                last_output_sample=sizes,
                                elapsed_seconds=self._clock() - started,
                                current_log_bytes=log_path.stat().st_size,
                            )
                        if shutil.disk_usage(project).free < MIN_FREE_BYTES:
                            raise ValueError("Free disk safety reserve exhausted during export")
                        last_resource_check = self._clock()
                    if log_path.stat().st_size > MAX_LOG_BYTES:
                        raise ValueError("Export log cap exceeded; output is not accepted")
                    time.sleep(0.05)
                if process.poll() is None:
                    self._terminate(process)
                record.update(exit_code=process.wait(timeout=5), child_reaped=True)
                if final_status in {"cancelled", "timed_out"}:
                    return
                if record["exit_code"] != 0:
                    raise ValueError("Export child exited unsuccessfully")
            if log_path.stat().st_size > MAX_LOG_BYTES:
                raise ValueError("Export log cap exceeded; output is not accepted")
            record["configuration_after_sha256"] = {
                name: digest(project / name) for name in request["configuration_sha256"]
            }
            changed = [
                name
                for name, expected in request["configuration_sha256"].items()
                if record["configuration_after_sha256"][name] != expected
            ]
            if changed:
                record["changed_configuration_files"] = changed
                raise ValueError("Saved configuration changed during export: " + ", ".join(changed))
            if not target.is_file() or target.stat().st_size == 0:
                raise ValueError("Requested export artifact is missing or empty")
            if (target.parent / ".gdignore").read_bytes() != b"":
                raise ValueError("Export output scanner exclusion changed")
            manifest = self._outputs(target.parent)
            manifest_path = folder / "outputs.json"
            _write_json(manifest_path, manifest)
            record.update(
                output_manifest_path=str(manifest_path),
                output_manifest_sha256=digest(manifest_path),
                output_count=len(manifest["files"]),
                output_bytes=manifest["bytes"],
                artifacts_accepted=True,
            )
            final_status = "completed"
        except Exception as error:
            record["reason"] = str(error)
        finally:
            try:
                if process is not None:
                    record.update(exit_code=self._terminate(process), child_reaped=True)
            except Exception as error:
                final_status = "unknown"
                record.update(
                    reason=f"Child cleanup uncertain: {error}",
                    child_reaped=False,
                    artifacts_accepted=False,
                )
            try:
                if log_path.exists():
                    record.update(
                        log_path=str(log_path),
                        log_bytes=log_path.stat().st_size,
                        log_sha256=digest(log_path),
                        log_complete=record["child_reaped"]
                        and log_path.stat().st_size <= MAX_LOG_BYTES,
                    )
            except Exception as error:
                record.update(
                    log_complete=False, artifacts_accepted=False, log_evidence_error=str(error)
                )
                if final_status == "completed":
                    final_status = "failed"
            record["cleanup_scope"] = (
                "owned_posix_process_group" if os.name == "posix" else "owned_direct_child_only"
            )
            record["descendant_cleanup_confirmed"] = os.name == "posix" and record["child_reaped"]
            if target.parent.exists() and not record.get("output_manifest_path"):
                try:
                    manifest = self._outputs(target.parent)
                    manifest_path = folder / "partial-outputs.json"
                    _write_json(manifest_path, manifest)
                    record.update(
                        partial_manifest_path=str(manifest_path),
                        partial_manifest_sha256=digest(manifest_path),
                        partial_manifest_is_snapshot=True,
                    )
                except Exception as error:
                    record["partial_manifest_error"] = str(error)
            with self._lock:
                record["status"] = final_status
                job["record"] = record
                try:
                    self._persist(job)
                except Exception as error:
                    record.update(
                        status="unknown",
                        artifacts_accepted=False,
                        reason=f"Terminal journal persistence failed; retain slot: {error}",
                    )

    @staticmethod
    def _output_sizes(directory: Path) -> dict[str, int]:
        files = 0
        total = 0
        visited = 0
        for path in directory.rglob("*"):
            visited += 1
            if visited > MAX_OUTPUT_FILES * 8 or path.is_symlink():
                raise ValueError("Unbounded or symlinked export output tree")
            if path.is_file():
                files += 1
                total += path.stat().st_size
                if files > MAX_OUTPUT_FILES + 1 or total > MAX_OUTPUT_BYTES:
                    raise ValueError("Runtime export output cap exceeded")
        return {"files_including_control": files, "bytes": total}

    @staticmethod
    def _outputs(directory: Path) -> dict[str, Any]:
        ExportJobManager._output_sizes(directory)
        files = []
        control_files = []
        total = 0
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError("Symlink in export output")
            if not path.is_file():
                continue
            if path.relative_to(directory).as_posix() == ".gdignore":
                if path.read_bytes() != b"":
                    raise ValueError("Changed export control file")
                control_files.append({"path": ".gdignore", "bytes": 0, "sha256": digest(path)})
                continue
            total += path.stat().st_size
            if len(files) >= MAX_OUTPUT_FILES or total > MAX_OUTPUT_BYTES:
                raise ValueError("Export output cap exceeded")
            files.append(
                {
                    "path": path.relative_to(directory).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": digest(path),
                }
            )
        return {"files": files, "bytes": total, "control_files": control_files}


_manager: ExportJobManager | None = None
_manager_directory: Path | None = None
_manager_lock = threading.RLock()


def configure_export_jobs(directory: Path) -> None:
    global _manager_directory
    with _manager_lock:
        if _manager is not None:
            raise RuntimeError("An export manager already owns this adapter process")
        _manager_directory = Path(directory)


def export_job_manager() -> ExportJobManager:
    global _manager
    with _manager_lock:
        if _manager_directory is None:
            raise RuntimeError("Export job lifecycle has not been configured by the server")
        if _manager is None:
            _manager = ExportJobManager(_manager_directory)
        return _manager


def shutdown_export_jobs() -> None:
    global _manager, _manager_directory
    with _manager_lock:
        if _manager is not None:
            _manager.close()
        _manager = None
        _manager_directory = None
