extends Node2D

const BG = Color('#10191e')
const PANEL = Color('#18262c')
const TEXT = Color('#edece3')
const MUTED = Color('#879b9e')
const AMBER = Color('#f4ca79')
const COLORS = [Color('#ed8c72'), Color('#e4c279'), Color('#84bfae'), Color('#92aeda')]
const NAMES = ['EARTH', 'DUST', 'AIR', 'GLASS']
const TYPES = ['ROUND KICK', 'BRUSH SNARE', 'CLOSED HAT', 'BELL / A MINOR']
const DEFAULT = [[1,0,0,0,1,0,0,0,1,0,0,0,1,0,1,0], [0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0], [0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,1], [1,0,0,1,0,0,1,0,1,0,0,0,1,0,0,1]]
const RATE = 44100
var pattern = DEFAULT.duplicate(true)
var bpm = 104
var playing = false
var step = -1
var clock_s = 0.0
var time_s = 0.0
var pulses = [0.0, 0.0, 0.0, 0.0]
var muted = [false, false, false, false]
var players: Array[AudioStreamPlayer] = []
var samples: Array[PackedFloat32Array] = []
var note_players: Array[AudioStreamPlayer] = []
var font: Font = ThemeDB.fallback_font
var hover = Vector2(-1,-1)
var status = 'READY TO WEAVE'
var demo = false
var screenshot_path = ''
var input_report = ''
var frame = 0
var events: Array = []
var screenshot_done = false
var export_path = ''

func _ready():
	get_window().title = 'Sonic Loom'
	for arg in OS.get_cmdline_user_args():
		if arg == '--demo': demo = true
		if arg.begins_with('--screenshot='): screenshot_path = arg.trim_prefix('--screenshot=')
		if arg.begins_with('--input-report='): input_report = arg.trim_prefix('--input-report=')
		if arg.begins_with('--export-audio='): export_path = arg.trim_prefix('--export-audio=')
	for lane in range(4):
		var data = synth(lane, 220.0)
		samples.append(data)
		var p = AudioStreamPlayer.new()
		p.stream = make_wav(data)
		p.volume_db = -5.0
		add_child(p)
		players.append(p)
	for hz in [220.0, 261.6256, 329.6276, 391.9954]:
		var p = AudioStreamPlayer.new()
		p.stream = make_wav(synth(3, hz))
		p.volume_db = -8.0
		add_child(p)
		note_players.append(p)
	if '--test' in OS.get_cmdline_user_args():
		run_tests()
		get_tree().quit()
		return
	load_pattern(false)
	if demo: toggle_play()
	if export_path != '': export_pattern(export_path)

func synth(lane: int, hz: float) -> PackedFloat32Array:
	var data = PackedFloat32Array()
	var n = int([0.48,0.24,0.09,0.72][lane] * RATE)
	data.resize(n)
	var rng = RandomNumberGenerator.new()
	rng.seed = 7291 + lane
	var phase = 0.0
	var last_noise = 0.0
	for i in range(n):
		var t = float(i)/RATE
		var noise = rng.randf_range(-1,1)
		var value = 0.0
		if lane == 0:
			phase += TAU * (48.0 + 115.0*exp(-t*42.0))/RATE
			value = sin(phase)*exp(-t*9.0)*0.78 + noise*exp(-t*140.0)*0.12
		elif lane == 1:
			value = (noise-last_noise)*exp(-t*22.0)*0.22 + sin(TAU*185*t)*exp(-t*32.0)*0.15
		elif lane == 2:
			value = (noise-last_noise)*exp(-t*72.0)*0.15
		else:
			value = (sin(TAU*hz*t)*0.35+sin(TAU*hz*2.005*t)*0.13+sin(TAU*hz*3.99*t)*0.055)*exp(-t*5.8)
		value *= min(1.0, t*900.0) * min(1.0, float(n-i)/100.0)
		data[i] = value
		last_noise = noise
	return data

func make_wav(data: PackedFloat32Array) -> AudioStreamWAV:
	var wav = AudioStreamWAV.new()
	wav.format = AudioStreamWAV.FORMAT_16_BITS
	wav.mix_rate = RATE
	var bytes = PackedByteArray()
	bytes.resize(data.size()*2)
	for i in range(data.size()): bytes.encode_s16(i*2, int(clampf(data[i],-1,1)*32767))
	wav.data = bytes
	return wav

func trigger(index: int):
	for lane in range(4):
		if pattern[lane][index] and not muted[lane]:
			pulses[lane] = 1.0
			if lane == 3: note_players[[0,0,1,2,0,1,2,3,2,1,0,1,3,2,1,0][index]].play()
			else: players[lane].play()

func toggle_play():
	playing = not playing
	if playing and step == -1:
		step = 0
		clock_s = 0
		trigger(step)
	status = 'WEAVING / LIVE' if playing else 'PAUSED / RESUME ANYTIME'
	log_event('play' if playing else 'pause')

func reset_pattern():
	pattern = DEFAULT.duplicate(true)
	bpm = 104
	muted = [false,false,false,false]
	step = -1
	clock_s = 0
	playing = false
	for p in players: p.stop()
	for p in note_players: p.stop()
	status = 'ORIGINAL PATTERN RESTORED'
	log_event('reset')

func toggle_cell(lane: int, index: int):
	pattern[lane][index] = 1 - int(pattern[lane][index])
	status = '%s / STEP %02d %s' % [NAMES[lane], index+1, 'ON' if pattern[lane][index] else 'OFF']
	log_event('cell', {'lane':lane,'step':index,'value':pattern[lane][index]})

func set_tempo(value: int):
	bpm = clampi(value,60,160)
	status = 'TEMPO / %d BPM' % bpm
	log_event('tempo')

func save_pattern(path: String = 'user://sonic-loom.json') -> bool:
	var f = FileAccess.open(path,FileAccess.WRITE)
	if not f: return false
	f.store_string(JSON.stringify({'pattern':pattern,'bpm':bpm,'muted':muted}))
	f.close()
	status = 'PATTERN SAVED / LOCAL DEVICE'
	log_event('save')
	return true

func load_pattern(announce: bool = true, path: String = 'user://sonic-loom.json') -> bool:
	if not FileAccess.file_exists(path):
		if announce: status = 'NO SAVED PATTERN YET'
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not d is Dictionary or not d.has('pattern') or d.pattern.size() != 4: return false
	for row in d.pattern:
		if not row is Array or row.size()!=16: return false
		for v in row:
			if v!=0 and v!=1: return false
	pattern = d.pattern
	bpm = clampi(int(d.get('bpm',104)),60,160)
	var m = d.get('muted',[false,false,false,false])
	if m is Array and m.size()==4: muted = m
	if announce:
		status = 'SAVED PATTERN RESTORED'
		log_event('load')
	return true

func log_event(action: String, extra: Dictionary = {}):
	var e = {'action':action,'bpm':bpm,'playing':playing,'step':step}
	e.merge(extra, true)
	events.append(e)
	if input_report != '':
		var f = FileAccess.open(input_report,FileAccess.WRITE)
		f.store_string(JSON.stringify({'events':events,'pattern':pattern,'bpm':bpm,'playing':playing,'muted':muted},'  '))

func _process(delta):
	frame += 1
	time_s += delta
	for lane in range(4): pulses[lane] = max(0,pulses[lane]-delta*4.8)
	if playing:
		clock_s += delta
		var duration = 60.0/bpm/4.0
		while clock_s >= duration:
			clock_s -= duration
			step = (step+1)%16
			trigger(step)
	if demo:
		if frame == 95: toggle_cell(1,10)
		if frame == 155: set_tempo(120)
		if frame == 235: toggle_cell(3,14)
		if frame == 295: toggle_play()
		if frame == 330: toggle_play()
	queue_redraw()
	if screenshot_path != '' and not screenshot_done and frame >= 65:
		screenshot_done = true
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(screenshot_path)

func _unhandled_input(event):
	if event is InputEventMouseMotion: hover = event.position
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE: toggle_play()
		if event.keycode == KEY_R: reset_pattern()
		if event.keycode == KEY_S: save_pattern()
		if event.keycode == KEY_L: load_pattern()
		if event.keycode == KEY_UP: set_tempo(bpm+1)
		if event.keycode == KEY_DOWN: set_tempo(bpm-1)
	if event is InputEventMouseButton and event.pressed and event.button_index==MOUSE_BUTTON_LEFT:
		var m = event.position
		if Rect2(46,173,170,52).has_point(m): toggle_play()
		elif Rect2(334,173,42,52).has_point(m): set_tempo(bpm-4)
		elif Rect2(462,173,42,52).has_point(m): set_tempo(bpm+4)
		elif Rect2(776,173,134,52).has_point(m): reset_pattern()
		elif Rect2(924,173,132,52).has_point(m): load_pattern()
		elif Rect2(1070,173,164,52).has_point(m): save_pattern()
		for lane in range(4):
			if Rect2(46,300+lane*82,197,66).has_point(m):
				muted[lane] = not muted[lane]
				log_event('mute',{'lane':lane,'value':muted[lane]})
			for i in range(16):
				if cell_rect(lane,i).has_point(m): toggle_cell(lane,i)

func cell_rect(lane: int, index: int) -> Rect2:
	return Rect2(274+index*59,300+lane*82,51,66)

func box(rect: Rect2, color: Color, radius: int = 10, border: Color = Color.TRANSPARENT):
	var style = StyleBoxFlat.new()
	style.bg_color = color
	style.set_corner_radius_all(radius)
	style.border_color = border
	style.set_border_width_all(1 if border.a>0 else 0)
	draw_style_box(style,rect)

func txt(pos: Vector2, value: String, size: int, color: Color = TEXT):
	draw_string(font,pos,value,HORIZONTAL_ALIGNMENT_LEFT,-1,size,color)

func _draw():
	draw_rect(Rect2(0,0,1280,800),BG)
	for x in range(18): draw_line(Vector2(x*80,0),Vector2(x*80-280,800),Color(0.35,0.6,0.6,0.025),1)
	txt(Vector2(46,43),'SONIC STUDIES     /     INSTRUMENT 001',13,MUTED)
	txt(Vector2(43,105),'Sonic Loom',50)
	txt(Vector2(47,137),'Weave a little rhythm. Leave some room for air.',17,MUTED)
	box(Rect2(984,41,250,83),PANEL,12)
	txt(Vector2(1004,65),'A MINOR  /  FOUR VOICES',12,MUTED)
	for i in range(34):
		var amp = 4+abs(sin(i*0.8+time_s*3))*19*(0.25+float(playing)*0.75)
		draw_line(Vector2(1006+i*6,94-amp/2),Vector2(1006+i*6,94+amp/2),AMBER,2)
	box(Rect2(46,173,170,52),AMBER,10)
	txt(Vector2(72,206),'II   PAUSE' if playing else '>   PLAY',18,BG)
	txt(Vector2(240,205),'TEMPO',12,MUTED)
	box(Rect2(334,173,170,52),PANEL)
	txt(Vector2(350,205),'-',20)
	txt(Vector2(392,206),str(bpm),24)
	txt(Vector2(477,205),'+',20)
	txt(Vector2(530,196),'16 STEPS',13)
	txt(Vector2(530,216),'4 / 4   ·   SIXTEENTHS',11,MUTED)
	for b in [[776,134,'RESET'],[924,132,'LOAD'],[1070,164,'SAVE PATTERN']]:
		box(Rect2(b[0],173,b[1],52),PANEL,10,Color('#304249'))
		txt(Vector2(b[0]+20,205),b[2],13)
	draw_line(Vector2(46,251),Vector2(1234,251),Color('#2c3b40'),1)
	txt(Vector2(46,282),'VOICE  /  TAP TO MUTE',11,MUTED)
	for i in range(16):
		txt(Vector2(288+i*59,282),'%02d'%(i+1),12,AMBER if i==step and playing else MUTED)
		if i%4==0: draw_line(Vector2(267+i*59,300),Vector2(267+i*59,612),Color('#415056'),1)
	for lane in range(4):
		var y = 300+lane*82
		box(Rect2(46,y,197,66),PANEL,10)
		draw_circle(Vector2(65,y+21),4+3*pulses[lane],MUTED if muted[lane] else COLORS[lane])
		txt(Vector2(79,y+27),NAMES[lane],18,MUTED if muted[lane] else TEXT)
		txt(Vector2(63,y+50),'MUTED' if muted[lane] else TYPES[lane],10,MUTED)
		for i in range(16):
			var r = cell_rect(lane,i)
			var active = bool(pattern[lane][i])
			var c = COLORS[lane] if active else Color('#1d2b31')
			if muted[lane] and active: c = c.darkened(0.6)
			box(r,c,7,Color('#7e9196') if r.has_point(hover) else Color.TRANSPARENT)
			if active:
				var mid = r.position+Vector2(25,33)
				if lane==0: draw_circle(mid,9,BG)
				elif lane==1:
					for j in range(3): draw_line(mid+Vector2(-9,j*5-5),mid+Vector2(9,j*5-5),BG,2)
				elif lane==2:
					draw_line(mid+Vector2(-7,-7),mid+Vector2(7,7),BG,2)
					draw_line(mid+Vector2(-7,7),mid+Vector2(7,-7),BG,2)
				else:
					draw_arc(mid,10,0,TAU,24,BG,2)
					draw_circle(mid,3,BG)
			else: draw_circle(r.get_center(),2,Color('#42545a'))
			if i==step and playing:
				draw_line(r.position+Vector2(6,60),r.position+Vector2(45,60),TEXT,3)
	box(Rect2(46,648,1188,96),PANEL,12)
	txt(Vector2(68,676),'THE THREAD',11,MUTED)
	for i in range(16):
		var x = 258+i*49
		var density = 0
		for lane in range(4): density += int(pattern[lane][i])
		var top = 703-density*8
		draw_line(Vector2(x,717),Vector2(x,top),AMBER if i==step else Color('#557477'),5)
		if i<15: draw_line(Vector2(x,top),Vector2(x+49,703),Color('#344b50'),1)
	txt(Vector2(68,716),'%02d / 16' % (step+1 if step>=0 else 1),22)
	txt(Vector2(1074,681),'GENERATIVE',11,MUTED)
	txt(Vector2(1074,703),'BY YOUR HAND',11,MUTED)
	txt(Vector2(46,779),status,11,AMBER)
	txt(Vector2(674,779),'SPACE  PLAY / PAUSE     ↑ ↓  TEMPO     S  SAVE     L  LOAD     R  RESET',11,MUTED)

func export_pattern(path: String):
	var length = 16*60.0/bpm/4.0
	var mix = PackedFloat32Array()
	mix.resize(int((length+0.8)*RATE))
	for i in range(16):
		for lane in range(4):
			if not pattern[lane][i] or muted[lane]: continue
			var data = samples[lane]
			if lane==3: data = synth(3,[220.0,261.6256,329.6276,391.9954][[0,0,1,2,0,1,2,3,2,1,0,1,3,2,1,0][i]])
			var start = int(i*60.0/bpm/4.0*RATE)
			for j in range(data.size()): mix[start+j] += data[j]*0.4
	make_wav(mix).save_to_wav(path)

func run_tests():
	var checks = []
	toggle_cell(0,1)
	checks.append({'name':'step toggles on','pass':pattern[0][1]==1})
	toggle_cell(0,1)
	checks.append({'name':'repeated step toggles off','pass':pattern[0][1]==0})
	set_tempo(200)
	checks.append({'name':'upper tempo bound','pass':bpm==160})
	set_tempo(1)
	checks.append({'name':'lower tempo bound','pass':bpm==60})
	set_tempo(112)
	toggle_cell(2,1)
	var saved = save_pattern('user://loom-test.json')
	reset_pattern()
	var loaded = load_pattern(true,'user://loom-test.json')
	checks.append({'name':'save and reopen edited pattern','pass':saved and loaded and bpm==112 and pattern[2][1]==1})
	toggle_play()
	checks.append({'name':'play starts first step','pass':playing and step==0})
	toggle_play()
	checks.append({'name':'pause preserves step','pass':not playing and step==0})
	reset_pattern()
	checks.append({'name':'reset restores defaults','pass':pattern==DEFAULT and bpm==104 and step==-1 and not playing})
	for lane in range(4):
		var peak=0.0
		for v in samples[lane]: peak=maxf(peak,absf(v))
		checks.append({'name':'voice %d has nonzero PCM'%lane,'pass':peak>0.01 and peak<1.0,'samples':samples[lane].size(),'peak':peak})
	var passed=true
	for check in checks: passed = passed and check['pass']
	print(JSON.stringify({'passed':passed,'checks':checks}))
