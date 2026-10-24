---
name: godot-resource
description: >-
  Domain skill — Load and serialize a resource property summary. Set properties and save a project resource. Instantiate and save a typed Resource. Generate or return a cached resource preview in a windowed editor. Queues without waiting for the callback, with a 20-second polling deadline; headless and unsupported resources return available=false. Register a project autoload singleton. Remove a project autoload singleton.
license: MIT
compatibility: "Godot 4.4+; dcc-mcp-core 0.19+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: godot
    layer: domain
    version: "0.1.0"
    search-hint: "Godot resource read_resource edit_resource create_resource get_resource_preview add_autoload remove_autoload"
    tags: "godot,resource,game-development"
    tools: tools.yaml
---

# Godot Resource

Use these editor-integrated tools after opening the target Godot project. Paths must remain under `res://`.


## Resource preview contract

`get_resource_preview` keeps its `path` input. For queued windowed requests,
`available` is returned only after Godot's callback completes.
`available: true` always includes `preview_path`;
`available: false` is explicitly unavailable, never image evidence. The editor
must be windowed: Godot disables its resource-preview worker in headless mode.
Only one resource request may be pending; a second call fails busy. Scene-preview
requests use a separate slot. The 20-second polling deadline, bridge disconnect and plugin
unload invalidate late callbacks. It is not a hard wall-clock completion guarantee:
Godot generation and bounded image conversion/PNG writes may use the main thread.
Closing a scene tab does not change this disk
resource operation. There is no native dequeue API or per-call cancel parameter;
HTTP client cancellation does not synchronously stop Godot generation.
Do not automatically retry an uncertain transport outcome.

Paths, including output directories, cannot traverse symlinks. A source or
.import metadata change during the request fails before publication. This follows
Godot's mtime/size cache semantics, not content-addressed freshness: same-second,
equal-length edits, changed dependencies, unsaved edits and changes during native
generation do not guarantee latest pixels. This is a Godot editor cached
thumbnail, not a content-addressed snapshot. Images are bounded to
1024 pixels per dimension and 4 MiB of native image data. PNG writes use a staged
file before rename; an unavailable/failed result never points to an older image.
