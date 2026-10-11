extends Node2D
# Original procedural optical puzzle. No external artwork or fonts.
const INK=Color("dce9e5")
const TEAL=Color("7df9d2")
const GOLD=Color("ffbd72")
const ORIGIN=Vector2(343,210)
const CELL=76.0
var level=0
var selected=0
var moves=0
var won=false
var phase=0.0
var mirrors=[]
var shutters=[]
var beam=[]
var source=Vector2i.ZERO
var receiver=Vector2i.ZERO
var observe=false
var demo=false
var frame=0
var screenshot=""
var capture_path=""
var font:Font=ThemeDB.fallback_font
const TITLES=["A quiet reflection","Through the breakwater","The long way home"]
const SUBTITLES=["Two turns return the light.","A closed gate interrupts the tide.","Six reflections. One unbroken signal."]
const LAYOUTS=[
 {"source":Vector2i(0,3),"target":Vector2i(7,5),"mirrors":[Vector2i(3,3),Vector2i(3,1),Vector2i(7,1)],"gates":[]},
 {"source":Vector2i(0,4),"target":Vector2i(9,4),"mirrors":[Vector2i(2,4),Vector2i(2,1),Vector2i(6,1),Vector2i(6,4)],"gates":[Vector2i(4,1)]},
 {"source":Vector2i(0,5),"target":Vector2i(9,5),"mirrors":[Vector2i(1,5),Vector2i(1,2),Vector2i(5,2),Vector2i(5,0),Vector2i(8,0),Vector2i(8,5)],"gates":[Vector2i(3,2),Vector2i(8,3)]}
]
func _ready():
 for arg in OS.get_cmdline_user_args():
  if arg=="--observe-input":observe=true
  if arg=="--demo":demo=true
  if arg.begins_with("--screenshot="):screenshot=arg.trim_prefix("--screenshot=")
  if arg.begins_with("--capture-path="):capture_path=arg.trim_prefix("--capture-path=")
 load_level(0)
 if "--test" in OS.get_cmdline_user_args():run_tests()
func load_level(i):
 level=i; selected=0; moves=0; mirrors=[]; shutters=[]
 source=LAYOUTS[i].source;receiver=LAYOUTS[i].target
 for p in LAYOUTS[i].mirrors:mirrors.append({"p":p,"slash":false})
 for p in LAYOUTS[i].gates:shutters.append({"p":p,"open":false})
 trace(); report("load")
func trace():
 beam=[center(source)];won=false
 var p=source;var d=Vector2i.RIGHT;var visited={}
 for bounce in range(160):
  p+=d
  if p.x<0 or p.x>=10 or p.y<0 or p.y>=6:
   beam.append(center(p));return
  var key=str(p)+str(d)
  if visited.has(key):return
  visited[key]=true
  beam.append(center(p))
  if p==receiver:won=true;return
  for gate in shutters:
   if gate.p==p and not gate.open:return
  for m in mirrors:
   if m.p==p:
    d=Vector2i(-d.y,-d.x) if m.slash else Vector2i(d.y,d.x)
func center(p):return ORIGIN+Vector2(p)*CELL+Vector2.ONE*CELL/2.0
func activate(i):
 if i<mirrors.size():mirrors[i].slash=not mirrors[i].slash
 else:shutters[i-mirrors.size()].open=not shutters[i-mirrors.size()].open
 moves+=1;trace();report("rotate")
func report(action):
 if observe:print("PRISM_STATE "+JSON.stringify({"action":action,"level":level+1,"selected":selected,"moves":moves,"won":won,"mirrors":mirrors.map(func(m):return m.slash),"gates":shutters.map(func(g):return g.open)}))
func _unhandled_input(event):
 if event is InputEventKey and event.pressed and not event.echo:
  match event.keycode:
   KEY_TAB: selected=(selected+1)%(mirrors.size()+shutters.size());report("select")
   KEY_SPACE,KEY_ENTER:activate(selected)
   KEY_R:load_level(level)
   KEY_N:if won:load_level((level+1)%3)
   KEY_F12:if not capture_path.is_empty():capture.call_deferred(capture_path)
 elif event is InputEventMouseButton and event.pressed and event.button_index==MOUSE_BUTTON_LEFT:
  var pos=get_global_mouse_position()
  for i in range(mirrors.size()+shutters.size()):
   var item=mirrors[i] if i<mirrors.size() else shutters[i-mirrors.size()]
   if pos.distance_to(center(item.p))<32:selected=i;activate(i);return
  if Rect2(60,664,215,48).has_point(pos):load_level(level)
  if won and Rect2(60,590,215,52).has_point(pos):load_level((level+1)%3)
func capture(path):
 await RenderingServer.frame_post_draw
 get_viewport().get_texture().get_image().save_png(path)
func _process(delta):
 phase+=delta;frame+=1
 if demo:
  if frame in [30,60]:activate((frame/30 as int)-1)
  if frame==130:load_level(1)
  if frame in [160,190,220]:activate([0,1,4][(frame-160)/30 as int])
  if frame==285:load_level(2)
  if frame in [310,330,350,370,390,410]:activate([0,1,2,3,6,7][(frame-310)/20 as int])
 if frame==105 and not screenshot.is_empty():capture.call_deferred(screenshot)
 queue_redraw()
func text_at(s,p,size=18,color=INK):draw_string(font,p,s,HORIZONTAL_ALIGNMENT_LEFT,-1,size,color)
func box(rect,color,radius=14):
 var style=StyleBoxFlat.new();style.bg_color=color
 style.set_corner_radius_all(radius);draw_style_box(style,rect)
func line(a,b,c,width=1.0):draw_line(a,b,c,width,true)
func _draw():
 draw_rect(Rect2(0,0,1280,800),Color("071b24"))
 for i in range(22):
  var y=50+i*36
  var points=PackedVector2Array()
  for x in range(0,1281,16):points.append(Vector2(x,y+sin(x*0.007+i*0.45+phase*0.25)*14))
  draw_polyline(points,Color(0.15,0.36,0.39,0.13),1,true)
 text_at("P / T",Vector2(60,56),20,TEAL)
 text_at("OPTICAL FIELD STATION",Vector2(143,55),12,Color("89a9ad"))
 text_at("PRISM TIDE",Vector2(60,118),44)
 text_at("STEER A LITTLE LIGHT THROUGH THE DEEP.",Vector2(62,151),12,Color("87a8ad"))
 text_at("REFRACTION STUDY  /  0"+str(level+1),Vector2(864,82),14,TEAL)
 text_at("10 × 06    •    NORTH ATLANTIC",Vector2(864,107),12,Color("87a8ad"))
 line(Vector2(60,174),Vector2(1220,174),Color("24434b"))
 text_at("0"+str(level+1)+" / 03",Vector2(60,231),38,TEAL)
 text_at(TITLES[level],Vector2(60,271),19)
 var descriptions=[["Rotate the brass mirrors.","Carry the signal into the", "receiver at the far shore."],["The striped shutter is closed.","Open it, then bend the beam", "around the sleeping water."],["Trace every corner of the bay.","Both shutters must be open", "before the light comes home."]]
 for i in range(3):text_at(descriptions[level][i],Vector2(60,307+24*i),14,Color("9bb8ba"))
 line(Vector2(60,398),Vector2(275,398),Color("24434b"))
 text_at("SIGNAL",Vector2(60,432),11,Color("88a8ad"))
 text_at("CONNECTED" if won else "SEEKING",Vector2(60,461),24,TEAL if won else GOLD)
 text_at("ADJUSTMENTS",Vector2(60,505),11,Color("88a8ad"))
 text_at("%02d"%moves,Vector2(60,541),28)
 if won:
  box(Rect2(60,590,215,52),TEAL)
  text_at("NEXT WATERS  →" if level<2 else "SAIL AGAIN  →",Vector2(78,622),16,Color("09262c"))
 else:text_at("A clear path is a quiet victory.",Vector2(60,624),12,Color("75999f"))
 box(Rect2(60,664,215,48),Color("15343e"))
 text_at("↺   RESET FIELD   /   R",Vector2(80,694),14)
 box(Rect2(323,190,800,496),Color("0c2631"),20)
 for x in range(10):
  for y in range(6):
   var p=center(Vector2i(x,y))
   draw_circle(p,1.5,Color("3c5962"))
   line(p+Vector2(-28,-28),p+Vector2(-22,-28),Color("163640"))
   line(p+Vector2(-28,-28),p+Vector2(-28,-22),Color("163640"))
 for i in range(beam.size()-1):
  var a=beam[i];var b=beam[i+1]
  # Keep termination at the edge of the inset board.
  b.x=clampf(b.x,333,1113);b.y=clampf(b.y,200,676)
  for width in [18,10,4]:line(a,b,Color(0.38,0.97,0.79,0.04 if width==18 else (0.12 if width==10 else 0.45)),width)
  line(a,b,TEAL,1.8)
 for i in range(mirrors.size()):
  var m=mirrors[i];var p=center(m.p)
  draw_circle(p,29,Color("102c36"));draw_arc(p,29,0,TAU,64,Color("9e805a"),1.5,true)
  if selected==i:draw_arc(p,34,-0.3,4.8,48,TEAL,1.2,true)
  var v=Vector2(17,-17) if m.slash else Vector2(17,17)
  line(p-v,p+v,Color("786753"),9);line(p-v,p+v,GOLD,3)
  draw_circle(p-v,3,GOLD);draw_circle(p+v,3,GOLD)
  text_at(str(i+1),p+Vector2(27,-27),10,Color("8ba5a8"))
 for i in range(shutters.size()):
  var gate=shutters[i];var p=center(gate.p)
  box(Rect2(p-Vector2(23,23),Vector2(46,46)),Color("243742"),7)
  for dy in [-12,0,12]:line(p+Vector2(-15,dy),p+Vector2(15,dy),Color("607780") if gate.open else Color("e99573"),3)
  if gate.open:draw_circle(p,8,Color("0c2631"))
  if selected==i+mirrors.size():draw_arc(p,34,0,TAU,48,TEAL,1.2,true)
 var s=center(source);draw_circle(s,19,Color("285b58"));draw_circle(s,9,TEAL);draw_circle(s,4,INK)
 var target=center(receiver)
 draw_arc(target,25,0,TAU,64,TEAL if won else Color("789b9d"),2,true)
 draw_arc(target,18,phase*0.5,phase*0.5+4.9,48,TEAL if won else Color("456b75"),2,true)
 draw_circle(target,8,TEAL if won else Color("284653"))
 for x in range(10):text_at(str(x+1),Vector2(377+x*76,710),10,Color("658991"))
 text_at("SOURCE",Vector2(343,744),10,TEAL)
 text_at("/   CLICK A MIRROR OR SHUTTER TO TURN IT",Vector2(434,744),11,Color("86a6ae"))
 line(Vector2(60,763),Vector2(1220,763),Color("24434b"))
 text_at("TAB  SELECT      SPACE  TURN      R  RESET      N  NEXT AFTER CONNECTION",Vector2(60,786),11,Color("89a9ad"))
 text_at("PRISM TIDE     •     FIELD NOTES 001",Vector2(953,786),10,Color("89a9ad"))
func run_tests():
 var checks={}
 var solutions=[[true,true,false],[true,true,false,false],[true,true,true,true,false,false]]
 for k in range(3):
  load_level(k);checks["level_%d_starts_unsolved"%(k+1)]=not won
  for i in range(mirrors.size()):mirrors[i].slash=solutions[k][i]
  for g in shutters:g.open=true
  trace();checks["level_%d_solution"%(k+1)]=won
  activate(0);checks["level_%d_wrong_turn"%(k+1)]=not won
  activate(0);checks["level_%d_restored"%(k+1)]=won
  if not shutters.is_empty():
   shutters[0].open=false;trace();checks["level_%d_closed_shutter"%(k+1)]=not won
  load_level(k);checks["level_%d_reset"%(k+1)]=not won and moves==0
 var passed=checks.values().all(func(v):return v)
 print("PRISM_TEST "+JSON.stringify({"checks":checks,"passed":passed}))
 get_tree().quit(0 if passed else 1)
