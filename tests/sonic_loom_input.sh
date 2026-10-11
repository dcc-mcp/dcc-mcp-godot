#!/usr/bin/env bash
set -euo pipefail
G="$1"; P="$2"; O="$3"
"$G" --path "$P" --audio-driver Dummy -- --input-report="$O/interaction.json" > "$O/interaction.log" 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT
W=$(timeout 20 xdotool search --sync --onlyvisible --name '^Sonic Loom' | head -1)
xdotool windowfocus --sync "$W"
xdotool key --window "$W" r
xdotool mousemove --window "$W" 359 335 click 1
xdotool mousemove --window "$W" 480 199 click 1
xdotool mousemove --window "$W" 1140 199 click 1
xdotool key --window "$W" space
sleep 1
xdotool key --window "$W" space
xdotool mousemove --window "$W" 114 333 click 1
xdotool key --window "$W" r l
sleep 0.5
python - "$O/interaction.json" <<'PY'
import json,sys
p=sys.argv[1];d=json.load(open(p));events=d['events'];actions=[e['action'] for e in events]
checks={'mouse_step':any(e['action']=='cell' and e.get('step')==1 and e.get('value')==1 for e in events),'tempo_button':any(e['action']=='tempo' and e['bpm']==108 for e in events),'play_pause':all(a in actions for a in ['play','pause']),'mute':any(e['action']=='mute' and e.get('value') for e in events),'saved_pattern_reopened':d['bpm']==108 and d['pattern'][0][1]==1 and not d['playing'],'reset_twice':actions.count('reset')==2}
d['checks']=checks;d['passed']=all(checks.values());open(p,'w').write(json.dumps(d,indent=2));assert d['passed'],checks
PY
