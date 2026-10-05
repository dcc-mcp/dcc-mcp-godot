# Scene previews

`render_scene_preview` renders a `.tscn`/`.scn` offscreen into a project PNG and
reports the fields you judge a frame by: `rendering_method` (which backend actually
produced it) and `unique_colors` (a cheap liveness judgement). Both are diagnostics,
not proof — they rule out a blank or foreign-backend frame, not a frame that renders
the wrong scene. It ships in the `godot-editor` domain skill, runs on the Godot main
thread, and is `read_only`.

The capability needs a **windowed** host. Godot degrades to `rendering/dummy` under
`--headless`, where an offscreen `SubViewport` reads back nothing; the host refuses
the call instead of returning a blank PNG that looks like a success. Unattended runs
therefore start a windowed editor and hide or relocate its window, never `--headless`.

## Inputs

| field | type | default | notes |
|---|---|---|---|
| `scene_path` | `res://…`, `.tscn`/`.scn` | the open edited scene | Errors when no scene is open, or the open scene is unsaved. |
| `path` | `res://…`, `.png` | `res://.dcc-mcp/preview/<md5>-<W>x<H>.png` | Output path under the project. |
| `width`, `height` | int | `1280`, `720` | Clamped to 16–4096. |
| `frame_count` | int | `3` | Real frames the host waits before readback (1–8). It never multiplies the output; the result is one PNG. |
| `camera_path` | string | first camera in the scene | Must resolve to a `Camera2D`/`Camera3D` inside the scene. With no camera, the host frames the scene bounds (≤2000 nodes). |
| `rendering_method` | string | the active method | Must equal the method the host is running, or the call errors. There is no silent fallback. |
| `budget_ms` | int | `40` | Observational main-thread budget (1–50). Only host-thread time counts against it. |
| `include_base64` | bool | `false` | Also return `png_base64`. |

## Outputs

Returned in the tool result `context`:

| field | meaning |
|---|---|
| `path`, `width`, `height`, `bytes` | The written PNG and its size. `width`/`height` are the size actually rendered: the host clamps the request to 16–4096, so they report the clamped value rather than echoing what you asked for. |
| `rendering_method` | The backend that actually rendered the frame. |
| `unique_colors` | Distinct pixel values. A real frame of the reference scene measures ~9.3k; an all-black trap frame collapses to `1`. |
| `display_driver`, `video_adapter`, `has_rendering_device` | Where the frame came from. |
| `scene_path`, `camera_path`, `camera_source` | What was rendered and how the camera was chosen (`explicit`, `scene`, `framed`). |
| `frame_count` | Frames the host waited for. |
| `elapsed_ms`, `thread_ms`, `budget_ms`, `budget_exceeded` | Wall clock, host-thread time, and the budget verdict. The parked wait for real frames is idle time, not a main-thread stall. |

`rendering_method` is not decoration: cross-backend frames differ measurably
(`mean_delta` 0.912/255, 71.2% of pixels different between `gl_compatibility` and
`d3d12`), so a comparison baseline is only meaningful when both frames name the same
backend.

## Platform support matrix

Every row states whether it was **measured** on a real host or is **not measured**.
"Not measured" is never reported as working.

| platform | launch path | status | evidence |
|---|---|---|---|
| Windows | windowed editor | **measured** | tier A, 5/5 calls, 1280×720, `gl_compatibility`, `mean_delta` 0.0, repeats byte-identical. |
| Windows | windowed + hidden main window (`--dcc-mcp-hide-window`, `DCC_MCP_GODOT_HIDE_WINDOW=1`) | **measured** | Byte-identical to a visible window in the run that measured it. No committed probe reproduces that run — `tests/probe_windowed_preview.py` pins `DCC_MCP_GODOT_HIDE_WINDOW=0`, and CI does not cover the Windows hidden-window path — so read this as a qualitative "no visible difference", not a repeat count you can re-derive. |
| Windows | `dcc-mcp-godot unattended` → `mode=private-desktop` | **measured** | Zero windows on the interactive desktop; a render called through `dcc-mcp-cli` was byte-identical (sha256) to the visible-window reference frame. |
| Windows | `--headless` (any `--rendering-driver`) | **measured — refused by design** | Godot drops to `rendering/dummy` and `create_local_rendering_device()` returns null under `--headless`, `--headless --rendering-driver vulkan`, and `--display-driver headless`. This is a Godot architecture limit, not a host configuration problem. |
| Windows | minimized window | **measured — forbidden** | Under `gl_compatibility` a minimized window reports success with an entirely black frame (`unique_colors` 1). Hide with `visible = false` or a private desktop. |
| Windows, Linux, macOS | no logon session (Session 0 / locked) | **not measured** | No evidence on any platform. Do not promise unattended operation there. |
| Linux | windowed editor on Xvfb | **measured** | CI `godot-latest` lane, ubuntu-latest, Godot 4.7.2.stable, llvmpipe: tier B, 5/5 calls, noise floor `mean_delta` 0.0 / `max_delta` 0 / 0.0% different pixels, repeats byte-identical. |
| Linux | `dcc-mcp-godot unattended` → `mode=plain` | **measured** | The host renders; its window belongs to the current display. Under Xvfb that display is already private, so nothing is hidden. |
| Linux | Wayland, Vulkan/lavapipe driver, X11 without Xvfb | **not measured** | Only X11 under Xvfb with the GL software rasteriser has been run. |
| macOS | windowed, hidden window, Metal | **not measured** | No macOS host. The CI Godot lane runs on ubuntu-latest. |

### Capability boundaries

- **Headless rendering is not available**, on any platform. "Unattended" here means a
  windowed host whose window is hidden or placed on a private desktop — it does not
  mean no display.
- **Only the Windows private desktop is measured to be invisible.** Off Windows the
  launcher reports `mode=plain`: reduced visibility, not invisible, and on the editor
  main window the hide request is best-effort.
- **Never hide by minimizing** (all-black frame, above).
- On Linux, Xvfb needs a 24-bit screen — `xvfb-run -a -s "-screen 0 1920x1080x24 -ac
  +extension GLX +render -noreset"`. The default 8-bit pseudocolour screen cannot host
  a GLX context. Set `LIBGL_ALWAYS_SOFTWARE=1` where there is no GPU, so a failed GLX
  context fails loudly instead of degrading the renderer.

## Calling it through an MCP client

The tool belongs to the `godot-editor` skill, so a client loads that skill first.
`search` returns `requires_load_skill: true` with a machine-executable `load_hint`
and `next_step`; follow them rather than guessing the slug.

```bash
dcc-mcp-cli list
dcc-mcp-cli search --query "render scene preview" --dcc-type godot
# follow the load_hint/next_step the search returned, then:
dcc-mcp-cli call godot.<instance>.render_scene_preview --dcc-type godot \
  --json '{"scene_path":"res://preview_probe.tscn","width":1280,"height":720,
           "frame_count":3,"path":"res://.dcc-mcp/preview/frame.png"}'
```

A successful call returns `rendering_method` and `unique_colors` alongside
`path`, `width`, `height` and `bytes`. Judge the frame before trusting it:

- the PNG's own size matches the returned `width`/`height` and `bytes > 0` — the host
  clamps the request to 16–4096, so compare against the response, not the request;
- `unique_colors > 1000` — this is what rejects a blank trap frame;
- the frame matches this platform's noise floor (below).

## Unattended launch

```bash
dcc-mcp-godot unattended --godot /path/to/godot --project /path/to/project --timeout 300 --json
```

The receipt reports `mode`: `private-desktop` (Windows only, zero visible windows) or
`plain` (everywhere else). `--no-hide-window` and `--no-private-desktop` are
debugging escapes, not unattended configurations.

## Re-measuring the noise floor

Frames are compared against frame 0 of the same run on the same host, not against a
frame archived elsewhere: pixels legitimately differ between GPUs, drivers and
rasterisers, so a cross-platform diff would measure the hardware instead of the tool.
What carries across platforms is the rendering method, which must match.

```bash
# Windows (tier A: byte-identical)
python tests/probe_windowed_preview.py --godot "$GODOT" --out preview-probe --tier A

# Linux (tier B: mean_delta <= 1.0/255, max_delta <= 32)
xvfb-run -a -s "-screen 0 1920x1080x24 -ac +extension GLX +render -noreset" \
  python tests/probe_windowed_preview.py --godot "$GODOT" --out preview-probe --tier B
```

Exit codes: `0` measured and passed, `1` measured and failed, `2` not measured. `2`
skips the assertions rather than faking a green light or blocking every pull request,
and writes the reason to the artifact and the job summary. The artifact also carries
the noise floor the run measured, which is the evidence needed before a tier can be
tightened — never copy another platform's tolerance.
