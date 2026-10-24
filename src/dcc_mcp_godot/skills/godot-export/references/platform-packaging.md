# Godot Cross-platform Packaging

Use this guide at intake, before opening a project or promising a runnable build.
Keep platform credentials and store submission outside the Skill; this guide
covers the reproducible build and validation boundary.

## First-response readiness gate

For packaging, EXE, executable, standalone or playable-delivery requests, return
an initial readiness result: available, blocked, or unknown, with evidence paths.
Do not defer dependency discovery until the end of gameplay work.

- Record the selected engine's absolute path, exact version/build, edition
  (standard or .NET), binary SHA-256 and architecture. Do not silently use a
  different engine from PATH or upgrade the source project.
- Identify target OS/architecture, debug or release, renderer and named preset.
  Inspect existing metadata read-only; use `get_export_info` and
  `list_export_presets` when an authorized editor session already exists. A
  missing live host is not permission to open one or install dependencies.
- Verify the official template matches the exact engine release, edition,
  target architecture and export mode. A Web template cannot build Windows.
  An absent or unreadable dependency blocks export; another version is not a
  fallback. A custom template requires explicit provenance and authorization.
- Report free disk space for source snapshot, imports, template extraction and
  output; report network availability, official URL, download size and extracted
  size (or mark them unknown). Distinguish full archive size from selected
  members. Do not download or install without the required explicit approval.
  Requests to package or produce an EXE do not authorize downloading templates.
  Respect network/permission denials; do not retry through another route.

## Trusted persistent template cache

Reuse a readable, verified, owner-approved persistent cache before proposing a
download. Partition it by exact engine release, edition, target and architecture.
Retain an inventory recording official URL, original archive SHA-256 and size,
selected archive member names, sizes and SHA-256, engine identity, extraction
recipe and verification date. For partial archive retrieval, explicitly mark the
whole archive digest unverified and retain the trusted member digest source;
never present a locally computed hash alone as proof of official provenance.

Check required member bytes against that provenance on reuse; a CI cache hit or
directory name alone is insufficient. Keep rebuild instructions and expected
digests with the project recipe so a missing cache can be reconstructed after
authorization. Do not remove or overwrite existing caches while packaging. If a
previous cache cannot be found, its history is unknown, not cleaned by inference.
Stop at denied resources without changing paths or privileges to bypass denial.

## Isolated output and acceptance receipt

Use an isolated snapshot of the exact source, including authorized dirty bytes,
with a per-file SHA-256 inventory. Import and export there with a separate test
user-data profile; preserve the original project, existing saves and active
windows. Refuse an existing output directory rather than replacing old builds.
Run meaningful import/script checks before export; retain failures and logs.
Keep the existing export-job ID/query/cancellation contract when using MCP.

Record engine/template/source identities, preset/options, included effects and
native dependencies, artifact sizes and hashes, startup logs and test scope.
Verify EXE/PCK pairing (or embedded PCK), required DLLs/GDExtensions and licenses.
Launch the transferred build without the editor/source tree or undeclared host
dependencies, using a separate save profile. Never reset a user's real save as
a test fixture.

Keep import, export, cold launch, visuals/audio and real gameplay as separate
gates with passed/failed/blocked/not-tested results bound to artifact hashes.
Actual input must exercise movement, combat, chest/loot, equipment/skills,
failure/retry, reset/new game and save/reopen when the game supports them.
Use project-owned DCC-CUA/ui-control, fresh provider/runtime/PID/birth/HWND
binding and an authorized available window. Scripted state changes and successful
export commands do not prove those interactions or audiovisual quality.

### Regression example: Relic Courier

| Artifact | Classification | Windows standalone evidence |
| --- | --- | --- |
| RelicCourier-native.zip | Editable source | Requires Godot to open project.godot; no EXE claim |
| Web HTML/JS/WASM/PCK | Web build | Uses Web templates; no Windows EXE claim |
| Windows EXE + required PCK/native libraries | Windows build candidate | Requires matching template, hashes, launch and separate gameplay checks |

In this fixture Godot 4.6.3 and Web templates exist, but the matching
4.6.3 Windows release template is missing. Report blocked before export and seek
specific dependency approval. Do not substitute a 4.7 template, rename a source
ZIP into a Windows build, or infer that an older template was deleted. These
fixture values illustrate a past gap; always probe current availability.

## Shared preflight

1. Record the Godot version, renderer, target architecture, enabled plugins and
   GDExtensions, and the exact named export preset. Export templates must match
   the editor version. Install ICU data when the shipped locales need Chinese,
   Japanese, Korean, emoji, or another language listed by Godot as ICU-backed.
2. Keep `export_presets.cfg` in version control. Never copy, print, or commit
   `.godot/export_credentials.cfg`; signing passwords, encryption keys, and
   store credentials remain operator-owned.
3. Treat `res://` as the packaged resource namespace and `user://` as mutable
   runtime storage. Do not derive packaged resources from the developer's
   current working directory, home directory, drive letter, or an absolute
   editor-machine path. Add required non-resource files such as JSON or CSV to
   the preset's include filters.
4. Prefer a bundled font under `res://` with a compatible redistribution
   license and an explicit fallback chain for every supported script. Never
   hard-code `C:/Windows/Fonts`, `/System/Library/Fonts`, or a Linux distro font
   path. `SystemFont` is host-dependent and is not implemented for every export
   target; on unsupported targets it falls back to the theme font, which may
   omit CJK glyphs. Test representative Chinese, Japanese, Korean, emoji, Latin,
   digits, and punctuation in the exported artifact, not only in the editor.
5. Confirm every native extension and library has a binary for the target OS
   and architecture. A project that imports successfully in the editor can
   still fail after packaging when a target binary or transitive library is
   absent.
6. Export to a clean staging directory and record the preset, Godot version,
   artifact names, sizes, and SHA-256 digests. Do not call a PCK/ZIP resource
   pack a playable build; it has no platform executable.

For CI or diagnosis outside the editor, the equivalent release shape is:

```text
godot --headless --path <project> --export-release "<preset>" <target-path>
```

The preset must already exist. The output extension is part of the platform
contract: `.exe` for Windows, `.app` or `.zip` for macOS (`.dmg` only when
exporting from macOS), commonly `.x86_64` for Linux, `.zip` for Web and iOS,
and `.apk` or `.aab` as selected for Android.

## Windows

- Select the intended `x86_64`, `x86_32`, or `arm64` template; do not infer the
  architecture from the build machine.
- Preserve the executable and its external PCK together when PCK embedding is
  disabled. Verify the icon and product metadata on the produced executable.
- Configure signing through the export preset and operator environment. Godot
  uses Windows SDK SignTool on Windows or `osslsigncode` on other hosts; never
  put certificate passwords in `export_presets.cfg` or command output.
- Run a case-sensitive resource-path audit even if development occurs on a
  case-insensitive Windows filesystem, because the same project may later ship
  to Linux or Web.

## macOS

- Official templates produce a Universal 2 `.app` bundle. Use `.zip` when
  exporting the bundle from Windows; a raw `.app` created on Windows loses the
  executable permission on its binaries. DMG creation is supported only on
  macOS.
- Set a stable reverse-DNS bundle identifier. Distribution outside local
  development requires the appropriate signing, hardened-runtime entitlements,
  notarization, and stapling flow.
- Validate the final transferred archive on both Apple Silicon and Intel when
  both architectures are claimed. Check that GDExtensions and helper binaries
  are universal or have matching per-architecture slices.

## Linux

- Name the main binary consistently (commonly `.x86_64`) and preserve its
  executable bit in the archive. Launch from a clean environment instead of a
  developer shell that supplies extra libraries or environment variables.
- Verify native libraries on the oldest supported distribution/runtime ABI.
  Do not rely on a desktop font package, locale package, or library that is not
  declared as a product prerequisite.
- Audit exact filename case and `res://` references. Windows-only path and case
  assumptions commonly surface first in Linux exports.

## Web

- Godot 4 Web export uses the Compatibility renderer and WebGL 2. Export to an
  `index.html` entry point and keep its generated `.wasm`, `.pck`, `.js`, and
  other sibling filenames together; do not validate by opening `file://`.
- Prefer the default single-threaded export unless the product demonstrably
  needs threads. Thread support and Web GDExtensions require a secure context
  and cross-origin isolation (`Cross-Origin-Opener-Policy: same-origin` and
  `Cross-Origin-Embedder-Policy: require-corp`). A PWA service worker can supply
  Godot's documented workaround, but HTTPS is still required.
- Serve `.wasm` as `application/wasm` and `.pck` as
  `application/octet-stream`; enable compression for large payloads. Test the
  real hosting headers, base path, cache policy, and iframe policy.
- Bundle fonts and their CJK fallback glyphs. Browser exports cannot assume
  access to Windows system fonts. Clear or unregister an old service worker
  before accepting a rebuilt artifact, and inspect the browser console for
  engine, WebGL, MIME, and resource errors.
- Account for browser user-gesture rules for audio, fullscreen, pointer capture,
  clipboard, and gamepad initialization. Godot 4 C# projects are not currently
  supported by the stable Web export.

## Android

- Pin the Android SDK/JDK and export-template inputs in CI. Use a unique package
  name and monotonically increasing version code; choose APK for direct testing
  and the store-required AAB path for release when applicable.
- Keep keystore material and passwords outside the repository. Verify requested
  permissions, ABI coverage, texture compression choices, orientation, touch
  input, lifecycle pause/resume, and `user://` persistence on a real device.
- Test a release-signed artifact, not only a debug export. Include the bundled
  fonts and validate CJK text on at least one low-memory device profile.

## iOS

- Export the Xcode project using the intended team, bundle identifier,
  provisioning profile, architecture, and privacy usage descriptions. Signing
  and App Store submission remain operator-controlled steps.
- Validate the archive on a physical device. Check safe areas, touch input,
  lifecycle transitions, `user://` persistence, native extensions, and the
  same bundled-font/CJK smoke used on other targets.

## Release verification matrix

For every claimed target, preserve evidence from the packaged artifact:

- cold launch succeeds without the editor, source tree, developer fonts, or
  undeclared environment variables;
- the first scene and critical resources load with no missing-resource or
  native-library errors;
- representative localized UI, including CJK and fallback glyphs, renders
  correctly;
- input, audio unlock, fullscreen/window behavior, and `user://` save/load work
  under the target runtime's rules;
- version, architecture, signing/notarization state, artifact digest, and
  startup logs match the release manifest;
- Web builds are served from the intended HTTPS host with production headers
  and a fresh cache/service-worker state.

Stop the release when a fallback font hides a missing glyph, a resource resolves
only from an absolute machine path, a native dependency comes from the build
host, or the packaged artifact was not launched. An editor screenshot or a
successful export command alone is insufficient evidence.

## Official references

- [Exporting projects](https://docs.godotengine.org/en/stable/tutorials/export/exporting_projects.html)
- [SystemFont](https://docs.godotengine.org/en/stable/classes/class_systemfont.html)
- [Exporting for Windows](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_windows.html)
- [Exporting for macOS](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_macos.html)
- [Exporting for Linux](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_linux.html)
- [Exporting for the Web](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)
- [Exporting for Android](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_android.html)
