"""Actual WebView offline update UI rehearsal; no real account, player, network or file replacement."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()
import json
import tempfile
import threading
import time
import webview
from core.theme_manager import ThemeManager

class Mock:
    def get_state(self): return {'roomid':'','account':None,'listening':False}
    def poll_events(self): return []
    def get_blacklist(self): return ''
    def get_playlist(self): return {'items':[],'current':None,'playing':False}
    def get_queue_policy(self): return {'enabled':False,'maximum':10}
    def capture_window_state(self): return {'visible':False}

errors=[]
window=webview.create_window('更新模拟离线回归',str(PROJECT_ROOT/'web/index.html')+'?updateDemo=1',js_api=Mock(),width=1180,height=780,frameless=True,easy_drag=False,shadow=False)
def ev(js): return window.evaluate_js(js)
def wait(js, timeout=12):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if ev(js): return
        time.sleep(.06)
    raise AssertionError('timeout: '+js)
def click(id):ev("document.getElementById("+json.dumps(id)+").click()")
def scenario(value):ev("document.getElementById('update-demo-scenario').value="+json.dumps(value)+";document.getElementById('update-demo-scenario').dispatchEvent(new Event('change'))")
def worker():
    try:
        wait("typeof UpdatePreview!=='undefined' && !!UpdatePreview.model")
        ev('loginView(false)')
        # First actual timer produces a badge even with settings closed.
        wait("UpdatePreview.model.state.phase==='available'")
        assert ev("!document.getElementById('settings-update-badge').classList.contains('hidden')")
        assert ev("document.getElementById('modal-settings').classList.contains('hidden')")
        with tempfile.TemporaryDirectory() as root:
            manager=ThemeManager(Path(root)/'themes');payload=manager.new()
            for width,height in [(920,600),(1180,780),(1440,900)]:
                window.resize(width,height);time.sleep(.2)
                for theme in ('dark','light','custom'):
                    if theme=='custom':ev('ThemeRuntime.apply('+json.dumps(payload)+')')
                    else:ev('setTheme('+json.dumps(theme)+')')
                    ev('openSettings();document.querySelector(".modal-body").scrollTop=0')
                    data=json.loads(ev('''(()=>{const b=document.getElementById('btn-settings').getBoundingClientRect(),dot=document.getElementById('settings-update-badge').getBoundingClientRect(),m=document.querySelector('.modal-card').getBoundingClientRect(),body=document.querySelector('.modal-body'),s=document.getElementById('update-demo').getBoundingClientRect(),actions=[...document.querySelectorAll('.update-demo-actions button:not(.hidden)')].map(e=>e.getBoundingClientRect());return JSON.stringify({overflow:body.scrollWidth>body.clientWidth,inside:m.top>=0&&m.bottom<=innerHeight,badge:dot.width===10&&dot.right>=b.right-2,section:s.width>100,actions:actions.every(r=>r.left>=m.left&&r.right<=m.right)});})()'''))
                    assert not data['overflow'] and all(data[k] for k in ('inside','badge','section','actions')),data
        click('update-demo-download')
        wait("UpdatePreview.model.state.progress>=10")
        ev('closeSettings()')
        wait("UpdatePreview.model.state.phase==='ready'")
        ev('openSettings()')
        assert ev("!document.getElementById('update-demo-install').classList.contains('hidden')")
        click('update-demo-install');wait("!!document.querySelector('[data-confirm-cancel]')")
        ev("document.querySelector('[data-confirm-cancel]').click()")
        assert ev("UpdatePreview.model.state.phase==='ready'")
        click('update-demo-install');wait("!!document.querySelector('[data-confirm-accept]')")
        ev("document.querySelector('[data-confirm-accept]').click()")
        wait("UpdatePreview.model.state.phase==='complete'")
        assert ev("document.getElementById('settings-update-badge').classList.contains('hidden')")
        click('update-demo-rollback');wait("!!document.querySelector('[data-confirm-accept]')")
        ev("document.querySelector('[data-confirm-accept]').click()")
        assert ev("UpdatePreview.model.state.current==='0.1.0' && !UpdatePreview.model.state.backup")
        for name,phase in [('latest','latest'),('check-error','check-error'),('download-error','available')]:
            scenario(name);click('update-demo-check');wait('UpdatePreview.model.state.phase==='+json.dumps(phase))
        click('update-demo-download');wait("UpdatePreview.model.state.phase==='download-error'")
        scenario('available');click('update-demo-check');wait("UpdatePreview.model.state.phase==='available'")
        click('update-demo-download');wait("UpdatePreview.model.state.progress>=10")
        click('update-demo-cancel');assert ev("UpdatePreview.model.state.phase==='available' && UpdatePreview.model.state.progress===0")
        ev('UpdatePreview.model.stop()')
        print('PASS: startup 5s badge; 9 themed layouts; download while settings closed; confirm cancel/accept; simulated install/rollback; latest/check failure/download failure/cancel; no real update operations',flush=True)
    except Exception as exc:
        errors.append(str(exc));print('FAIL:',repr(exc),flush=True)
    finally:window.destroy()
threading.Thread(target=worker,daemon=True).start()
webview.start()
if errors:raise SystemExit(1)
