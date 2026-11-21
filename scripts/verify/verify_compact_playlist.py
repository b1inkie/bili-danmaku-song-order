"""Compact rows + pointer-transparent themed tooltip; no account or real player."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()
import os,json,threading,time
import webview
class Mock:
 def get_state(self):return {'roomid':'','account':None,'listening':False}
 def poll_events(self):return []
 def get_playlist(self):return {'current':'2','playing':True,'items':[{'id':str(i),'name':'非常长的完整歌名 · 完整信息测试 '+str(i),'singer':'测试歌手 A / B','duration':213,'requester':'观众小明' if i==2 else ''} for i in range(1,9)]}
errors=[]
w=webview.create_window('紧凑歌单回归',os.path.abspath('web/index.html'),js_api=Mock(),width=1180,height=780,frameless=True,easy_drag=False)
def ev(s):return w.evaluate_js(s)
def worker():
 try:
  time.sleep(2);original=ev('document.documentElement.dataset.theme');ev('loginView(false)')
  for width,height in [(920,600),(1180,780),(1440,900)]:
   w.resize(width,height);time.sleep(.3)
   for theme in ['dark','light','haruka']:
    ev('setTheme('+json.dumps(theme)+')');time.sleep(.25)
    for attempt in range(20):
     # evaluate_js focus() may not emit focus while another desktop window owns focus.
     # Dispatch through the actual registered focus handler in the background test window.
     ev("document.activeElement.blur();const summary=document.querySelector('[data-song-id=\"2\"] .song-summary');if(summary){summary.focus({preventScroll:true});summary.dispatchEvent(new FocusEvent('focus'))}")
     time.sleep(.25)
     if ev("!!document.getElementById('song-detail-tip')&&!document.getElementById('song-detail-tip').classList.contains('hidden')"):break
    else:
     details=ev("JSON.stringify({theme:document.documentElement.dataset.theme,focused:document.activeElement.className,focus:document.hasFocus(),rows:document.querySelectorAll('.playlist-row').length,anchor:songTipAnchor?.className,tip:document.getElementById('song-detail-tip')?.className})")
     raise AssertionError('tooltip did not become ready: '+str((width,height,theme,details)))
    result=json.loads(ev(r'''(()=>{const tip=document.getElementById('song-detail-tip'),r=tip.getBoundingClientRect(),rows=[...document.querySelectorAll('.playlist-row')],panel=document.querySelector('.panels').getBoundingClientRect();return JSON.stringify({rowHeights:rows.map(x=>x.getBoundingClientRect().height),tooltip:tip.textContent,pointer:getComputedStyle(tip).pointerEvents,tipVisible:!tip.classList.contains('hidden'),inside:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,requester:document.querySelector('[data-song-id="2"] .song-requester').textContent,singleLine:!document.querySelector('.playlist-row .q-meta'),panelTop:panel.top,panelHeight:panel.height,overflow:document.documentElement.scrollWidth>innerWidth});})()'''))
    assert all(38<=h<=41 for h in result['rowHeights']),result
    assert result['pointer']=='none' and result['inside'] and result['tipVisible'],result
    assert '测试歌手' in result['tooltip'] and '观众小明' in result['tooltip'] and '3:33' in result['tooltip'],result
    assert result['requester']=='观众小明' and result['singleLine'] and not result['overflow'],result
    if theme=='haruka':
     assert result['panelTop']<=210,result
     layers=json.loads(ev(r'''(()=>{const scene=document.querySelector('.haruka-scene'),bar=document.querySelector('.actionbar'),panel=document.querySelector('.panels'),input=document.getElementById('input-song'),r=input.getBoundingClientRect(),cs=getComputedStyle(scene);return JSON.stringify({overflow:cs.overflow,pointer:cs.pointerEvents,sceneZ:cs.zIndex,barZ:getComputedStyle(bar).zIndex,panelZ:getComputedStyle(panel).zIndex,isolation:cs.isolation,inputHit:document.elementFromPoint(r.left+8,r.top+r.height/2)===input,fadeWidth:getComputedStyle(scene,'::after').width,viewport:innerWidth});})()'''))
     assert layers['overflow']=='visible' and layers['pointer']=='none' and layers['inputHit'],layers
     assert layers['sceneZ']=='0' and layers['barZ']=='1' and layers['panelZ']=='1' and layers['isolation']=='isolate',layers
     assert abs(float(layers['fadeWidth'].removesuffix('px'))-layers['viewport'])<=1,layers
    ev("document.querySelector('.song-summary').dispatchEvent(new MouseEvent('mouseleave'));hideSongTip()")
    assert ev("document.getElementById('song-detail-tip').classList.contains('hidden')")
  ev('setTheme('+json.dumps(original)+')')
  print('PASS: 9 layouts; 40px single-line rows; requester; themed noninteractive tooltip; compact hero',flush=True)
 except Exception as e:errors.append(str(e));print('FAIL: '+str(e),flush=True)
 finally:w.destroy()
threading.Thread(target=worker,daemon=True).start();webview.start()
if errors:raise SystemExit(1)
