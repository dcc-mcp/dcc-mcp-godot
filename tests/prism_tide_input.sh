#!/usr/bin/env bash
set -euo pipefail
G=$1; P=$2; O=$3
"$G" --path "$P" --audio-driver Dummy -- --observe-input --capture-path="$O/interaction.png" > "$O/interaction.log" 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
W=$(timeout 20 xdotool search --sync --onlyvisible --name '^Prism Tide' | head -1)
xdotool windowfocus --sync "$W"
sleep .3
# Wrong orientation, repeated reset, first solution with keyboard.
xdotool key space space r r space Tab space
sleep .3
xdotool key F12
sleep .3
xdotool key n
# Level 2: rotate first two mirrors using the real mouse; gate remains closed.
xdotool mousemove --window "$W" 533 552 click 1
xdotool mousemove --window "$W" 533 324 click 1
sleep .2
xdotool mousemove --window "$W" 685 324 click 1
sleep .2
# Mouse next button and solve level 3.
xdotool mousemove --window "$W" 160 616 click 1
for xy in '457 628' '457 400' '761 400' '761 248' '609 400' '989 476'; do
  xdotool mousemove --window "$W" $xy click 1
  sleep .15
done
sleep .3
xdotool key F12
sleep .3
# Break restored victory, then restore; mouse reset twice.
xdotool mousemove --window "$W" 457 628 click 1 click 1
xdotool mousemove --window "$W" 160 690 click 1 click 1
sleep .3
python - "$O/interaction.log" "$O/interaction-result.json" <<'PY'
import json,sys
from pathlib import Path
states=[json.loads(s.split('PRISM_STATE ',1)[1]) for s in Path(sys.argv[1]).read_text().splitlines() if s.startswith('PRISM_STATE ')]
checks={f'level_{k}_real_input_win':any(s['level']==k and s['won'] for s in states) for k in (1,2,3)}
checks['keyboard_selection']=any(s['action']=='select' and s['selected']==1 for s in states)
checks['closed_shutter_blocks']=any(s['level']==2 and s['moves']==2 and not s['won'] and s['gates']==[False] for s in states)
checks['wrong_rotation_unsolved']=any(s['level']==1 and s['moves']==1 and not s['won'] for s in states)
checks['repeated_keyboard_reset']=sum(s['level']==1 and s['action']=='load' for s in states)>=3
checks['repeated_mouse_reset']=sum(s['level']==3 and s['action']=='load' for s in states)>=3
checks['final_reset_clear']=states[-1]['level']==3 and states[-1]['moves']==0 and not states[-1]['won']
Path(sys.argv[2]).write_text(json.dumps({'passed':all(checks.values()),'checks':checks,'states':states},indent=2)+'\n')
assert all(checks.values()),checks
PY
