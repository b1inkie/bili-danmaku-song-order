"""真实歌单界面离线回归，不使用账号，不改变网易云。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()
import copy,json,os,threading,time
import webview
class MockApi:
 def __init__(self):
  self.data={'current':'2','playing':True,'items':[{'id':str(i),'name':'很长的歌曲名字 · 歌单界面测试 '+str(i),'singer':'测试歌手','duration':210} for i in range(1,7)]}
  self.commands=[]
  self.blacklisted=[]
 def get_state(self):return {'roomid':'','account':None,'listening':False}
 def poll_events(self):return []
 def get_playlist(self):return copy.deepcopy(self.data)
 def blacklist_song(self,song):
  item=next(x for x in self.data['items'] if x['id']==song)
  added=song not in self.blacklisted
  if added:self.blacklisted.append(song)
  return {'name':item['name'],'added':added}
 def clear_playlist(self,ids):
  assert ids==[x['id'] for x in self.data['items']]
  self.commands.append(('clear',ids))
  self.data.update(items=[],current=None,playing=False)
  return copy.deepcopy(self.data)
 def skip_next(self):
  self.commands.append(('skip',))
 def playlist_action(self,song,command,direction=0):
  self.commands.append((song,command,direction));items=self.data['items'];index=next(i for i,x in enumerate(items) if x['id']==song)
  if command=='toggle':
   self.data['playing']=not self.data['playing'] if self.data['current']==song else True;self.data['current']=song
  elif command=='move':items[index],items[index+direction]=items[index+direction],items[index]
  elif command=='delete':items.pop(index)
  return copy.deepcopy(self.data)
mock=MockApi();errors=[]
w=webview.create_window('歌单离线回归',os.path.abspath('web/index.html'),js_api=mock,width=1180,height=780,frameless=True,easy_drag=False)
def evaluate(js):return w.evaluate_js(js)
def worker():
 try:
  time.sleep(2);original=evaluate('document.documentElement.dataset.theme');evaluate('loginView(false)')
  for width,height in [(920,600),(1180,780),(1440,900)]:
   w.resize(width,height);time.sleep(.3)
   for theme in ['dark','light','haruka']:
    evaluate('setTheme('+json.dumps(theme)+')');time.sleep(.2)
    result=json.loads(evaluate(r'''(()=>{const rows=[...document.querySelectorAll('.playlist-row')];const list=document.getElementById('queue-list');return JSON.stringify({count:rows.length,current:document.querySelector('[aria-current="true"]')?.dataset.songId,controls:document.querySelectorAll('.playlist-row .song-action').length,overflow:list.scrollWidth>list.clientWidth,bodyOverflow:document.documentElement.scrollWidth>innerWidth,listHeight:list.clientHeight,label:document.getElementById('now-playing-state').textContent});})()'''))
    assert result['count']==6 and result['current']=='2' and result['controls']==24,result
    assert not result['overflow'] and not result['bodyOverflow'] and result['listHeight']>40,result
    icons=json.loads(evaluate(r'''JSON.stringify({all:[...document.querySelectorAll('.song-toggle,.song-action,.win-btn,#btn-close-settings')].every(b=>b.querySelector('svg')&&!b.textContent.trim()),pause:document.querySelector('[aria-current="true"] .song-toggle svg').dataset.icon,trash:document.querySelector('.song-delete svg').dataset.icon,pointer:getComputedStyle(document.querySelector('.song-toggle svg')).pointerEvents})'''))
    assert icons['all'] and icons['pause']=='pause' and icons['trash']=='trash' and icons['pointer']=='none',icons
    assert evaluate("document.querySelector('.song-blacklist svg').dataset.icon")=='ban'
  before=copy.deepcopy(mock.data)
  evaluate("window.confirm=()=>{throw Error('native confirmation must not be used')};document.querySelector('[data-song-id=\"2\"] .song-blacklist').click()")
  assert evaluate("!!document.querySelector('.confirm-card[role=alertdialog]')")
  evaluate("document.querySelector('[data-confirm-cancel]').click()")
  time.sleep(.2);assert not mock.blacklisted
  evaluate("document.querySelector('[data-song-id=\"2\"] .song-blacklist').click();document.querySelector('[data-confirm-accept]').click()")
  for _ in range(30):
   if mock.blacklisted and not evaluate('state.playlistBusy'):break
   time.sleep(.1)
  assert mock.blacklisted==['2'] and mock.data==before,(mock.blacklisted,mock.data)
  evaluate("document.querySelector('[data-song-id=\"2\"] .song-blacklist').click();document.querySelector('[data-confirm-accept]').click()")
  time.sleep(.4);assert mock.blacklisted==['2']
  evaluate("document.querySelector('[data-song-id=\"2\"] .song-toggle').click()")
  time.sleep(.5);assert not mock.data['playing']
  assert evaluate("document.querySelector('[data-song-id=\"2\"] .song-toggle svg').dataset.icon")=='play'
  evaluate("document.querySelector('[data-song-id=\"3\"] .song-actions button').click()")
  time.sleep(.5);assert mock.data['items'][1]['id']=='3'
  evaluate("document.querySelector('[data-song-id=\"3\"] .song-delete').click()")
  time.sleep(.5);assert '3' not in [x['id'] for x in mock.data['items']]
  assert len(mock.commands)==3,mock.commands
  evaluate("document.getElementById('btn-playlist-toggle').click()")
  time.sleep(.5);assert mock.data['playing']
  evaluate("document.getElementById('btn-skip').click()")
  time.sleep(.3);assert mock.commands[-1]==('skip',)
  for theme in ['dark','light','haruka']:
   evaluate('setTheme('+json.dumps(theme)+')')
   evaluate("document.getElementById('btn-playlist-clear').click()")
   result=json.loads(evaluate("(()=>{const c=document.querySelector('.confirm-card'),r=c.getBoundingClientRect();return JSON.stringify({inside:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,text:c.textContent,buttons:[...document.querySelectorAll('.playlist-header-actions button')].map(b=>({text:b.textContent,icon:b.querySelector('svg').dataset.icon})),bottomSkip:!!document.querySelector('.actionbar #btn-skip')});})()"))
   assert result['inside'] and '清空' in result['text'] and not result['bottomSkip'],result
   assert [b['icon'] for b in result['buttons']]==['pause','next','trash'] and all(not b['text'] for b in result['buttons']),result
   evaluate("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
   time.sleep(.1);assert mock.data['items'] and not evaluate("!!document.querySelector('.confirm-overlay')")
  evaluate("document.getElementById('btn-playlist-clear').click();document.querySelector('[data-confirm-accept]').click()")
  time.sleep(.5);assert not mock.data['items'] and mock.commands[-1][0]=='clear'
  assert evaluate("document.getElementById('btn-playlist-clear').disabled")
  for listening,expected in [(True,'ready'),(False,'offline')]:
   evaluate('state.listening='+str(listening).lower()+';setListenBtn()')
   assert evaluate("document.getElementById('btn-listen').dataset.state")==expected
   assert evaluate("!!document.querySelector('#btn-listen .player-connection-dot')")
  evaluate('setTheme('+json.dumps(original)+')')
  print('PASS: 9 populated layouts; current highlight; blacklist cancel/confirm/dedup without playback changes; pause/move/delete',flush=True)
 except Exception as e:errors.append(str(e));print('FAIL: '+str(e),flush=True)
 finally:w.destroy()
threading.Thread(target=worker,daemon=True).start();webview.start()
if errors:raise SystemExit(1)
