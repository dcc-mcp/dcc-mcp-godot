#!/usr/bin/env bash
set -euo pipefail
G=$1; P=$2; O=$3
"$G" --path "$P" --audio-driver Dummy -- --capture="$O" > "$O/input.log" 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
for i in $(seq 1 80); do
  wid=$(xdotool search --onlyvisible --name 'Mothlight' 2>/dev/null | head -1 || true)
  [ -z "$wid" ] || break
  sleep .2
done
[ -n "$wid" ]
xdotool windowfocus "$wid"
xdotool key 2
sleep .5
xdotool key 3
sleep .5
xdotool key space
sleep .2
xdotool key space
xdotool mousemove --window "$wid" 1110 298 click 1
sleep .5
xdotool mousemove --window "$wid" 1110 357 click 1
sleep .5
xdotool key r
sleep .3
for motion in Perch Unfurl Flight; do grep -q "MOTION_SELECTED:$motion" "$O/input.log"; done
for marker in 'INPUT_KEY:2' 'INPUT_KEY:3' 'INPUT_KEY:Space' 'INPUT_KEY:R' 'INPUT_BUTTON:Perch' 'INPUT_BUTTON:Unfurl' 'PAUSE_STATE:true' 'PAUSE_STATE:false'; do grep -q "$marker" "$O/input.log"; done
printf '{"keyboard_clip_switch":true,"mouse_buttons":true,"runtime":"real X11 input"}\n' > "$O/input-check.json"
