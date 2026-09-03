# Godot Size Optimization Guidance

The profile helper turns static project evidence into a reviewable starting
point. It intentionally does not guess about features created through
reflection, string-based class loading, downloaded content, custom modules, or
GDExtensions. Re-run the scan after project changes and keep the generated
report with the build inputs.

## Compile-time options

The baseline profile uses `target="template_release"`,
`debug_symbols="no"`, and `lto="full"`. Godot 4.5 and later use
`optimize="size_extra"`; older versions use `optimize="size"`. The option
names belong to the Godot engine source version being compiled, so confirm
them with `scons --help` and do not mix a profile with another engine version.

The helper can add these conditional options when static evidence permits it:

| Option | Do not disable it when | Why it is conditional |
| --- | --- | --- |
| `disable_3d` | Any 3D node, resource, renderer path, or extension is used | Removing 3D breaks those projects. |
| `disable_advanced_gui` | Rich text, editor-like controls, or their dynamic equivalents are used | The flag removes controls such as `RichTextLabel`, `TextEdit`, and `SpinBox`. |
| `module_text_server_adv_enabled=no` | RTL, complex scripts, OpenType features, or non-Latin text is needed | The fallback server is intended for Latin, Greek, and Cyrillic based text. Always pair the disabled advanced server with `module_text_server_fb_enabled=yes`. |
| `vulkan=no`, `use_volk=no` | The project is confirmed to use the Compatibility renderer | Forward+ and Mobile rendering need Vulkan support. |
| `disable_navigation_2d/3d` | Navigation APIs or scenes are used | These switches are available in Godot 4.5 and later. |
| XR, ZIP, AccessKit, Graphite options | The corresponding API or product requirement is absent | Static detection cannot see every dynamic call. |

`--minimal-modules` is deliberately opt-in. It changes the default from all
modules enabled to a small allowlist for GDScript, text, fonts, SVG, WebP, and
detected physics. The allowlist is a build experiment, not proof that the
project does not use another module. Godot's Engine Compilation Configuration
Editor can detect project features and save a `.gdbuild` file, but its
autodetection can be too aggressive; remove accidentally disabled classes and
retest the packaged artifact.

## Platform-specific post-processing

These steps are not run by the helper because they change distribution and
runtime behavior:

- **Windows / UPX:** `upx <game>.exe` can greatly reduce the executable, but it
  can increase memory use and trigger antivirus heuristics. Keep an uncompressed
  artifact, record the hash after packing, and test startup and memory before
  sharing it.
- **Web / Wasm-opt:** `wasm-opt <game>.wasm -o <optimized>.wasm -all
  --post-emscripten -Oz` can reduce the uncompressed WebAssembly file. Measure
  the final archive because ZIP compression may hide most of the gain.
- **Web / Brotli:** compress the `.wasm` and `.pck` only when the production
  host serves the correct `Content-Encoding` and Godot MIME types. A ZIP file
  alone does not establish that the deployed host can decode Brotli.

An exported PCK/ZIP is resource data, not a playable build. For each claimed
platform, retain the executable or web entry point, its sibling data files,
the exact Godot/template version, artifact sizes, SHA-256 digests, and a cold
launch result.

## Sources

- [Godot: Optimizing a build for size](https://docs.godotengine.org/en/latest/engine_details/development/compiling/optimizing_for_size.html)
- [Godot: Engine compilation configuration editor](https://docs.godotengine.org/en/4.5/tutorials/editor/using_engine_compilation_configuration_editor.html)
- [Godot: Introduction to the buildsystem](https://docs.godotengine.org/en/stable/engine_details/development/compiling/introduction_to_the_buildsystem.html)
- [Popcar: How to Minify Godot's Build Size](https://popcar.bearblog.dev/how-to-minify-godots-build-size/)
