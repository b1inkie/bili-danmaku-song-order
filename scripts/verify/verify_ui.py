"""离线 UI 回归：不启动引擎，不使用账号，不控制网易云。"""
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
    def get_state(self):
        return {"roomid": "", "account": None, "listening": False}
    def poll_events(self):
        return []

window = webview.create_window("点歌台 · 离线预览", os.path.abspath("web/index.html"),
                               js_api=MockApi(), width=1180, height=780,
                               frameless=True, easy_drag=False, shadow=False,
                               background_color="#0a0a0b")
window.events.shown += lambda: main_gui.apply_round_region(window)

def verify():
    time.sleep(2)
    result = window.evaluate_js(r'''(() => {
      loginView(false);
      const rect = s => { const r=document.querySelector(s).getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
      const hit = (x,y) => {const e=document.elementFromPoint(x,y);return !!(e && e.closest('.pywebview-drag-region'));};
      applyEvent({type:'song',phase:'requested',request_id:'test1',name:'原名',requester:'测试'});
      applyEvent({type:'song',phase:'queued',request_id:'test1',name:'搜索后歌名',requester:'测试',source:'网易云'});
      applyEvent({type:'song',phase:'requested',request_id:'test2',name:'失败测试',requester:'测试'});
      applyEvent({type:'song',phase:'failed',request_id:'test2',name:'失败测试',requester:'测试',error:'未连接'});
      const result={title:rect('.windowbar'),panel:rect('.panels'),footer:rect('.actionbar'),
        topDrag:[hit(100,2),hit(500,8),hit(500,30)],
        signature:getComputedStyle(document.querySelector('.background-signature span')).fontFamily,
        latinFont:getComputedStyle(document.querySelector('.background-signature em')).fontFamily,
        signatureHit:getComputedStyle(document.querySelector('.background-signature')).pointerEvents,
        panelAlpha:getComputedStyle(document.querySelector('.queue-panel')).backgroundColor,
        signatureText:document.querySelector('.background-signature').textContent,
        noDanmaku:!document.querySelector('#dm-list')&&!document.querySelector('.ticker'),
        requests:state.queue.length,pending:document.querySelectorAll('.queue-item.pending').length,
        overflow:document.documentElement.scrollWidth>innerWidth};
      state.queue=[];renderQueue();return JSON.stringify(result);
    })()''')
    print(result, flush=True)
    with open(OUTPUT_DIR / 'verify_ui_result.json','w',encoding='utf-8') as f:
        f.write(result)
    data = json.loads(result)
    assert all(data['topDrag']) and data['noDanmaku'] and not data['overflow']
    assert data['pending'] == 0 and data['requests'] == 2
    assert 'STXingkai' in data['signature'] and data['signatureHit'] == 'none'
    time.sleep(1)
    window.destroy()

threading.Thread(target=verify,daemon=True).start()
webview.start()
