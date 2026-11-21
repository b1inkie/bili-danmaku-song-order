"""离线回归：连接状态/按钮次序/设置排版，不控制真实播放器。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()
import json
import os
import threading
import time
import webview
import main_gui

class MockApi:
    def __init__(self): self.ready=False; self.launches=0; self.author_opened=0
    def open_author_bilibili(self): self.author_opened+=1; return True
    def get_state(self): return {"roomid":"","account":None,"listening":False}
    def poll_events(self): return []
    def get_blacklist(self): return ''
    def get_queue_policy(self): return getattr(self,'policy',{'enabled':False,'maximum':10})
    def save_queue_policy(self,enabled,maximum):
        self.policy={'enabled':enabled,'maximum':maximum};return self.policy
    def player_status(self): return {"ready":self.ready,"message":"网易云已连接" if self.ready else "未连接，请先退出网易云后点击连接"}
    def get_playlist(self):
        if not self.ready: raise RuntimeError('网易云未连接')
        return {"current":None,"playing":False,"items":[]}
    def launch_player(self):
        self.launches+=1;self.ready=True
        return {"ready":True,"message":"网易云已连接"}

mock=MockApi()
window=webview.create_window('设置回归',os.path.abspath('web/index.html'),js_api=mock,
                            width=1180,height=780,frameless=True,easy_drag=False,shadow=False,background_color='#111111')
errors=[]
PROBE=r'''(() => {
 loginView(false);openSettings();
 const box=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,w:r.width,h:r.height};};
 const body=document.querySelector('.modal-body');body.scrollTop=0;
 const theme=box('#btn-theme'),player=box('#btn-player-connect'),settings=box('#btn-settings');
 const sections=[...document.querySelectorAll('.settings-section')].map(e=>({gap:getComputedStyle(e).gap,padding:getComputedStyle(e).paddingBottom}));
 const topItems=[...document.querySelector('.drag-area').children,...document.querySelector('.top-actions').children];
 let overlap=false;for(let i=1;i<topItems.length;i++){const a=topItems[i-1].getBoundingClientRect(),b=topItems[i].getBoundingClientRect();if(a.right>b.left+1)overlap=true;}
 const roomInput=box('#input-roomid'),roomButton=box('#btn-save-roomid'),textarea=box('#input-blacklist'),save=box('#btn-save-blacklist');
 const modal=box('.modal-card');
 const hit=document.elementFromPoint(modal.x+20,modal.y+20);
 const r={theme:document.documentElement.dataset.theme,viewport:[innerWidth,innerHeight],order:theme.right<=player.x&&player.right<=settings.x,
   overlap,modal,bodyHorizontalOverflow:body.scrollWidth>body.clientWidth,
   rowAligned:Math.abs(roomInput.h-roomButton.h)<1,
   saveGap:save.y-textarea.bottom,
   sectionSpacing:sections,
   modalOnTop:!!hit.closest('.modal-card'),state:document.getElementById('btn-player-connect').dataset.state};
 closeSettings();return JSON.stringify(r);
})()'''
def worker():
 try:
    time.sleep(2)
    original=window.evaluate_js('document.documentElement.dataset.theme')
    results=[]
    for w,h in [(920,600),(1180,780),(1440,900)]:
        window.resize(w,h);time.sleep(.3)
        for theme in ['dark','light','haruka']:
            window.evaluate_js('setTheme('+json.dumps(theme)+')');time.sleep(.3)
            r=json.loads(window.evaluate_js(PROBE));results.append(r)
            assert r['order'] and not r['overlap'] and not r['bodyHorizontalOverflow'],r
            assert r['rowAligned'] and r['saveGap']>=11 and r['modalOnTop'],r
            assert all(s['gap']=='12px' for s in r['sectionSpacing']),r
            assert r['modal']['y']>=0 and r['modal']['bottom']<=h,r
            window.evaluate_js('openSettings()')
            author=window.evaluate_js("(()=>{const e=document.getElementById('btn-author-bilibili');e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect(),b=document.querySelector('.modal-body').getBoundingClientRect();return {visible:r.top>=b.top&&r.bottom<=b.bottom,text:e.textContent,hit:document.elementFromPoint(r.left+r.width/2,r.top+r.height/2).closest('button')===e};})()")
            assert author['visible'] and author['hit'] and '1160389658' in author['text'],author
    window.evaluate_js("document.getElementById('btn-author-bilibili').click()")
    time.sleep(.2);assert mock.author_opened==1
    window.evaluate_js("openSettings();document.getElementById('queue-limit-enabled').checked=true;document.getElementById('queue-limit-maximum').value='5';document.getElementById('btn-save-queue-policy').click()")
    assert window.evaluate_js("!!document.querySelector('.confirm-card')")
    window.evaluate_js("document.querySelector('[data-confirm-accept]').click()")
    time.sleep(.5)
    assert mock.get_queue_policy()=={'enabled':True,'maximum':5}
    window.evaluate_js("openSettings()")
    time.sleep(.2)
    assert window.evaluate_js("document.getElementById('queue-limit-enabled').checked&&document.getElementById('queue-limit-maximum').value==='5'")
    window.evaluate_js("closeSettings()")
    assert window.evaluate_js("document.getElementById('btn-player-connect').dataset.state")=='offline'
    window.evaluate_js("document.getElementById('btn-player-connect').click()")
    time.sleep(.7)
    assert mock.launches==1
    assert window.evaluate_js("document.getElementById('btn-player-connect').dataset.state")=='ready'
    mock.ready=False
    window.evaluate_js('refreshPlayerStatus()');time.sleep(.5)
    assert window.evaluate_js("document.getElementById('btn-player-connect').dataset.state")=='offline'
    window.evaluate_js('setTheme('+json.dumps(original)+')')
    print(json.dumps(results,ensure_ascii=False),flush=True)
    print('PASS: 9 layouts, offline -> connect -> ready -> offline',flush=True)
 except Exception as e:
    errors.append(str(e));print('FAIL: '+str(e),flush=True)
 finally:window.destroy()
threading.Thread(target=worker,daemon=True).start()
webview.start()
if errors:raise SystemExit(1)
