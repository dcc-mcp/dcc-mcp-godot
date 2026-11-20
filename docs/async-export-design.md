# Bounded observable export jobs

The Godot adapter implements the `godot-export-job-v1` contract for exports
that can outlive an MCP bridge request. The asynchronous path is the preferred
route for long exports. The legacy `export_project` action remains available
for compatibility and can still exceed a bridge deadline.

## Contract

`start_export_job` validates the named preset, project-relative output path,
saved configuration hashes and the actual host executable before it reserves a
fresh output directory. It accepts a required 32-character lower-case
hexadecimal `request_id`. The request ID is the stable job ID. Repeating the
same ID with identical parameters returns the existing receipt. Reusing it
with different parameters fails closed.

The call returns a bounded receipt with `queued` or `running` status. Polling
uses `get_export_job`. Terminal states are `completed`, `failed`, `cancelled`,
`timed_out` and `unknown`. A transport timeout does not imply that no child
started and never authorizes an automatic replay.

Each terminal receipt records the child exit code, cleanup scope, reaping
result, complete log path and SHA-256, and an output manifest path and
SHA-256. Successful artifacts are accepted only after the saved project and
export preset hashes match their preflight values. Partial output remains
explicitly unaccepted after failure, cancellation or timeout.

`cancel_export_job` signals and reaps only a child owned by the current
manager. POSIX uses the owned process group. Windows reports
`owned_direct_child_only` because descendant cleanup is not claimed. If
ownership or journal finalization becomes uncertain, the result is `unknown`,
the project slot remains occupied, and the historical PID is never reused for
cleanup.

## Bounds and ownership

The manager owns one locked journal per registry and allows one active or
unresolved export per project. It retains at most 32 records. Paths cannot
traverse symlinks, target editor metadata or addons, or overwrite an existing
output directory. The export process receives only the engine path, project,
mode, preset and target path. Logs are capped at 16 MiB. Output is capped at
256 files and 512 MiB with a 64 MiB free-space reserve.

The manager creates a staging directory containing `.gdignore` before the
visible output directory exists. This prevents the open editor from importing
the export while it is being produced. The control file is listed separately
from deliverable files and is included in the receipt.

The journal lock is acquired before records are read or recovered. An adapter
restart converts an unfinished record to `unknown` because a new process does
not own the historical child. Adapter shutdown requests cancellation, waits for
all owned workers, and preserves the lock if teardown remains uncertain.

## Verification

Host-free tests cover request identity, path and symlink safety, journal
retention, slow start, nonzero exit, timeout, cancellation and reaping, log and
output caps, configuration drift, recovery to `unknown`, process ownership,
and terminal receipt hashes.

The `Observable export candidate` workflow runs
`tests/probe_export_jobs.py` against the exact candidate wheel, Godot
`4.6.3-stable`, and the pinned `web_nothreads_release` template. The probe
records the candidate commit, wheel hash, adapter and core versions, engine
version and hash, template ID and hash, configuration snapshots, MCP receipts,
complete logs, output manifests, a clean PCK inspection and a browser startup
receipt. Its browser fixture reaches multiple runtime frames through localhost
and fails on page or console errors.

This workflow qualifies the export lifecycle and a clean Web fixture. It does
not claim acceptance of a production Showcase project. Production callers
still need a fresh project, a pinned engine/template pair, an independent
artifact review and the target runtime's own input and persistence checks.
