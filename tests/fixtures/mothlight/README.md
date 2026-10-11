# Mothlight skinned-animation regression

Original Blender rig transfer fixture: 197 weighted mesh objects, 10 bones, and Perch / Unfurl / Flight actions. The compressed base64 transport decodes to the exact SHA-256-verified GLB. Source geometry was authored through dcc-mcp-blender and playback UI through dcc-mcp-godot.

This fixture tests real Godot import, Skeleton3D poses, clip switching, pause/resume, actual keyboard and button input, and native GPU/software-GL screenshots. It is a regression fixture, not a claim of final showcase visual acceptance.

Artwork: CC BY 4.0, attribute “Mothlight, DCC-MCP showcase contributors”. https://creativecommons.org/licenses/by/4.0/
Original test scripts: MIT, same terms as repository LICENSE. No third-party assets or application binaries included.

Decode mothlight.glb.gz.b64 with base64 then gzip, check asset.json, import project.godot with Godot 4.6.3, run with -- --test. Keys 1/2/3 choose clips, Space pauses, R restarts.
