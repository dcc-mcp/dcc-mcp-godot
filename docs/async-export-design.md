# Bounded observable export jobs (proposal for #87)

This proposal is not deployed or tested in a live editor. Existing `export_project` remains the documented synchronous compatibility action; the new tools are the preferred long-export route. No global bridge timeout is increased and no plugin is silently stripped from a user's project.

## Placement and official route

The Python adapter owns a narrowly scoped export-process manager. A new short read-only host action supplies the actual open project root, actual engine executable/version, named preset metadata and hashes of the saved project configuration/preset file. It does not execute an export or block the Godot editor. The adapter uses that verified host context to spawn the same engine with the same preset, release/debug flag and safe project-relative target. This is an official typed adapter implementation, not a caller-side CLI bypass.

Do not put the long `OS.execute` inside the main-thread bridge, or merely wrap that unchanged synchronous call in Core's generic async job wrapper. That still blocks the editor and loses the child outcome after a 60-second bridge timeout.

## API

- `start_export_job(preset, path, request_id, debug=false, timeout_seconds=600)`: validates inputs and returns promptly with a stable ID and queued/running state. `request_id` is a required 32-character lower-case hex identity, also used as job ID, so a lost response can be queried without starting a second child. Same ID and exactly same parameters returns the existing record; conflicting reuse is rejected.
- `get_export_job(job_id)`: returns a bounded state receipt, actual exit code when known, cancellation/timeout reason, log bytes and complete-log hash/path, and output-manifest hash/path. It does not return unbounded stdout or source contents.
- `cancel_export_job(job_id)`: requests cancellation only of this manager's recorded owned child, waits a bounded interval for termination/reaping, and returns the actual resulting state. It never treats a transport timeout as cancellation or safe-to-repeat.

State progression: queued → running → completed / failed / cancelled / timed_out. `unknown` covers recovered ownership uncertainty, uncertain termination or journal finalization. Such records cannot be automatically restarted or killed by PID. Queries and exact request-ID deduplication survive client reconnects. Fresh adapter startup never trusts a historical PID as current ownership.

## Bounds and artifacts

- One export manager owns a given registry journal across all adapter processes, with at most one active export per project and 32 retained records. This v1 does not support simultaneous export owners sharing a registry. No arbitrary executable, shell text, extra arguments or environment options are accepted.
- Target must resolve inside the actual project, with no parent traversal, option-like path, symlink traversal or pre-existing target/output directory contents. A dedicated fresh output directory prevents overwriting existing deliverables. Path reservation and request record creation happen before spawn.
- Timeout range 5–1800 seconds. Log cap 16 MiB, output count/size caps explicit. A log-cap violation stops the child and fails; no truncation is called complete evidence.
- Logs go directly to an owned file, not a pipe that can deadlock. Terminal output manifest records actual relative paths, sizes and SHA-256 hashes. Partial files are retained and explicitly unaccepted after errors/cancel/timeouts.
- Saved project.godot and export_presets.cfg hashes are checked before spawn and at completion. Any change fails acceptance; this does not claim every project asset was immutable. Caller-level source manifests remain required for reproducible production.
- Manager shutdown cancels/reaps its own children. On POSIX the owned child uses a new session and its process group is terminated on cleanup; never target unrelated process groups. Windows cleanup is limited to the actually owned Popen child unless independently validated broader ownership is added.
- Durable small JSON records distinguish known terminal failure from uncertain interrupted work; a journal write/spawn failure is not disguised as successful start.

## Integration and tests

Generate the three tool schemas through the existing generator, keep legacy schemas compatible, dispatch new actions to the Python manager, and bind manager shutdown to the adapter lifecycle. The short host context action validates the preset again and reports host errors instead of success wrappers.

Host-free tests must cover exact request-ID deduplication/conflict, path containment/symlinks/occupied outputs, one-active and retention limits, start without waiting for a slow fake child, nonzero exit, timeout, cancellation/reaping, log cap, source-config changes, output hashes, interrupted durable records, and bounded polling. Test transport uncertainty with a known request ID followed by a query, not an automatic repeated mutation.

Hosted native validation must use a candidate wheel with an explicit commit/hash, fresh owned project, matching official engine/templates, real start/status/cancel and a completed Web export. Verify complete log and manifest hashes, no control-plugin contamination in the test project's PCK, and actual browser startup. The new API is not production-ready merely because host-free tests pass.

### Review refinements

An unknown record continues to occupy the project's active slot. This minimal API has no blind "forget PID" escape hatch. Safe reuse requires an independently established teardown of the old isolated environment and a genuinely fresh project/adapter journal, or a later explicitly reviewed reconciliation API; changing a timeout or reusing the original output does not resolve uncertainty.

The manager constructs the fresh output directory under a hidden staging name with an empty `.gdignore` already present, then renames it into place before spawning. This prevents the live editor from importing exported Web files and prevents recursive packaging. The terminal manifest separates that scanner-control file from deliverable files and verifies it remained unchanged.

Windows records explicitly declare `cleanup_scope=owned_direct_child_only` and never claim all descendant processes were cancelled. POSIX cleanup requires the owned process group to disappear; otherwise state becomes unknown and retains its active slot. These platform boundaries must remain in the published docs and actual status receipts.

Runtime guards sample output size/count without hashing at most twice per second, and require a 64 MiB free-disk reserve (plus the 512 MiB output allowance before starting). The 256-file / 512 MiB caps and 16 MiB log cap are polled safety bounds, not OS-enforced quotas: a burst can overshoot between checks. Terminal hashing is bounded by a prior size/count walk. Startup failures proven to occur before a worker exists remove only that request's fresh reservation; uncertain startup retains an unknown record and slot.

Host-free lifecycle tests include real short owned subprocess cancellation/reaping and an isolated Linux supervisor that demonstrates a parent exiting successfully while its child stays alive. The latter produces unknown and retains the slot; the test then terminates/reaps its own descendant. These are process-lifecycle tests, not live Godot export acceptance.

### Cross-process ownership limitation

Before any journal read/recovery/write, a lazy manager acquires a nonblocking OS lock (POSIX flock or Windows byte lock) on a stable owner.lock file. Another adapter using that registry receives an explicit busy error without reading/relabeling records or spawning a child. Normal adapter startup and unrelated tools do not acquire this lock. The owning manager holds it until shutdown has joined all owned worker threads; uncertain threads or failed lock release raise rather than claim shutdown. OS process death releases the lock, after which the next owner recovers old running records as unknown and retains their project slots. The stable lock file is never deleted or replaced. Use the existing explicit private registry option for genuinely isolated adapters; do not silently change global registry settings. Parallel exports from multiple Godot adapters sharing one registry remain a future improvement, not a capability claimed by this Draft.
