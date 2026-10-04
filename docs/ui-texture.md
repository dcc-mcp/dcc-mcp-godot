# Assign imported PNGs to UI controls

`godot-node.assign_ui_texture` assigns an existing project PNG to either
`TextureRect.texture` or `Button.icon`. The tool determines the property from
the actual native node class. It accepts exactly:

```json
{"node_path":"Panel/MailIcon","texture_path":"res://assets/mail.png"}
```

`node_path` is relative to the current edited scene (`.` names the root), with
at most 500 characters. Only existing native TextureRect and Button nodes without
attached scripts are supported. Absolute paths, traversal, subnames, unique-name
lookups, empty components and additional property/type parameters are rejected.

The adapter and editor must share a local project filesystem. PNGs must be regular
project-contained files with the lowercase `.png` extension, at most 16 MiB,
1–4096 pixels per side and at most 4,194,304 total pixels. Animated PNGs, corrupt
images, missing files, symlinks, junctions and reparse points are rejected. Header
sizes are checked before decoding. Pillow performs bounded format validation in
the adapter and Godot decodes the source again before mutation.

Finish the normal editor import first, using the built-in **Texture2D** importer,
**Lossless** compression, and **Mipmaps / Generate** disabled. The tool checks the
PNG's current import source digest and the CTEX destination digest, and validates the CTEX image payload
(maximum 32 MiB). Supported CTEX version 1 contains a single PNG or lossless VP8L WebP image with
matching dimensions. Size overrides, mipmaps, custom importers, VRAM compression,
Basis Universal, arbitrary `.res`/`.tres`, scripts and scene loading are outside
this capability. Import settings are never changed by assignment. Import metadata must already
reflect a completed editor import. Source/destination digests detect image and
cache changes; they do not attest arbitrary edits to import settings. After
changing import settings, finish the editor's normal reimport before assigning.

The tool reads import metadata as bounded text, then calls the native
`CompressedTexture2D.load()` method on the validated imported file. It does not
use a generic resource loader, instantiate a scene, execute an editor script,
fetch a URL or trigger project-wide scanning. A current native cached texture is
reused so other scene references retain their resource path and identity. A stale
or incompatible cache entry returns `import_pending`; refresh it using the normal
editor import workflow and retry. The capability never takes over a resource path
or reloads an already-referenced texture itself. Normal editor reimport may update
all references to that PNG, as it does for hand-authored projects.

## Results and retry contract

The MCP structured result uses Core's skill envelope: `success`, `message` and
`context`, with optional nullable `error` and `prompt` fields. The typed fields
below are inside `context`. Outer `success: true` means the capability returned
its result; check `context.assigned` and `context.status` to determine whether a
texture was assigned. Rejections and pending imports also use that envelope.

- `assigned: true`, `status: assigned`: the property readback matches the loaded
  Texture2D, its PNG resource path and dimensions; a native editor undo action was
  registered. `changed` and `undo_registered` are true
- `assigned: true`, `status: unchanged`: the exact resource was already assigned;
  there is no extra undo action
- `assigned: false`, `status: import_pending`: import files are missing, stale or
  changing, a scan is running, or the native cache needs refresh. Complete the
  normal editor import and retry. An acknowledged scan alone is not completion
- `assigned: false`, `status: rejected`, `import_failed`, or `assignment_failed`:
  inspect `reason`. Rejection occurs before changing the destination. A failed
  assignment readback restores the previous resource and reports `rollback_verified`

Successful results include node path/class, derived property, native resource
class/path, an opaque resource instance ID string (valid only in that editor
process; its numeric-looking value may be negative),
source SHA-256, dimensions and a digest of the native RGBA8 readback.
`source_native_rgba8_matches_import` compares the source decoded by Godot with the
imported texture in that same host. It is an observation, not a promise of
cross-renderer or cross-color-management pixel identity. Import processing can
legitimately change transparent pixels. Do not use this boolean as an alpha or
artwork quality certificate.

Undo restores the previous reference, including null, and redo restores the new
one. Repeating an unchanged call is idempotent. This undo action covers the property
assignment, not changes made separately to the PNG or its editor import. Saving a
scene after assignment retains the external `res://...png` reference. Verify with
`save_scene`, `get_scene_file_content`, and `get_scene_dependencies`, then reopen
and read the native property again. Do not use `get_scene_tree(scene_path)` as a
script-free file validator: that existing operation instantiates a PackedScene.

A client validation or transport error after a mutation request does not prove
that the assignment did not execute. Inspect the native property before deciding
whether to retry. The output schema validates the complete skill envelope and
retains the strict assignment/failure contract under `context`.

File paths, sizes and hashes are checked again in the host before loading and
before property assignment. This contract assumes an owned editor project without
hostile concurrent filesystem replacement or scripts mutating the scene during a
request. It is not a sandbox for untrusted projects. Native decode/import work is
bounded by image/file size; it is synchronous and has no preemptive millisecond
runtime guarantee.

## Validation

`tests/test_ui_texture.py` covers file rejection, import freshness, bounded image
payloads, dispatcher behavior, schema generation and native source contracts.
These Python tests do not prove editor execution. Native acceptance must separately
exercise null-to-texture transitions on both controls, undo/redo, repeated calls,
rejection without destination changes, changed PNG imports, save/reopen external
references and actual rendered pixels on a windowed Godot 4.4+ editor.
