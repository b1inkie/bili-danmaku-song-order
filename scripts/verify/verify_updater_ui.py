"""Real updater GUI contract with mocked transport state, not demo controller."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
ROOT,OUTPUT=setup()
import copy,json,tempfile,threading,time
import webview
from core.theme_manager import ThemeManager

class API:
    def __init__(self):
        self.s=dict(phase='idle',current='0.1.0',latest=None,available=False,progress=0,message='test',notes='',backup=None,checkedAt=None,frozen=True,recovery=False)
        self.installs=[]
    def get_state(self):return {'account':None,'roomid':'','listening':False}
    def poll_events(self):return []
    def get_blacklist(self):return ''
    def get_queue_policy(self):return {'enabled':False,'maximum':10}
    def get_playlist(self):return {'items':[],'current':None,'playing':False}
    def capture_window_state(self):return {'visible':False}
    def frontend_ready(self):return True
    def update_state(self):return copy.deepcopy(self.s)
    def check_update(self):self.s.update(phase='available',latest='0.2.0',available=True,notes='<b>plain text</b>');return self.update_state()
    def download_update(self):self.s.update(phase='downloading',progress=25);return self.update_state()
    def cancel_update(self):self.s.update(phase='available',progress=0);return self.update_state()
    def install_update(self,rollback=False):self.installs.append(rollback);return {'closing':True}
api=API();errors=[]
window=webview.create_window('更新真实界面离线检查',str(ROOT/'web/index.html'),js_api=api,width=1180,height=780,frameless=True)
def ev(js):return window.evaluate_js(js)
def wait(js):
    end=time.monotonic()+10
    while time.monotonic()<end:
        if ev(js):return
        time.sleep(.08)
    raise AssertionError(js)
def click(name):ev('document.getElementById('+json.dumps(name)+').click()')
def worker():
    try:
        wait("window.__songdeskFrontendReady===true")
        assert ev('UpdatePreview.model===undefined')
        assert ev("document.getElementById('update-demo-scenarios').classList.contains('hidden')")
        ev('loginView(false);openSettings()')
        click('update-demo-check');wait("!document.getElementById('settings-update-badge').classList.contains('hidden')")
        assert ev("document.querySelector('#update-demo-notes').textContent.includes('<b>plain text</b>')")
        assert not ev("document.querySelector('#update-demo-notes b')")
        with tempfile.TemporaryDirectory() as root:
            payload=ThemeManager(Path(root)/'themes').new()
            for size in [(920,600),(1180,780),(1440,900)]:
                window.resize(*size);time.sleep(.2)
                for theme in ('dark','light','custom'):
                    ev('ThemeRuntime.apply('+json.dumps(payload)+')' if theme=='custom' else 'setTheme('+json.dumps(theme)+')')
                    geometry=json.loads(ev("(()=>{const body=document.querySelector('.modal-body'),card=document.querySelector('.modal-card').getBoundingClientRect();return JSON.stringify({overflow:body.scrollWidth>body.clientWidth,inside:card.top>=0&&card.bottom<=innerHeight});})()"))
                    assert not geometry['overflow'] and geometry['inside'],geometry
        click('update-demo-download');wait("document.getElementById('update-demo-progress').value===25")
        click('update-demo-cancel');wait("document.getElementById('update-demo-status').textContent==='发现新版'")
        api.s.update(phase='ready');wait("!document.getElementById('update-demo-install').classList.contains('hidden')")
        click('update-demo-install');wait("!!document.querySelector('[data-confirm-cancel]')")
        ev("document.querySelector('[data-confirm-cancel]').click()")
        assert not api.installs
        click('update-demo-install');wait("!!document.querySelector('[data-confirm-accept]')")
        ev("document.querySelector('[data-confirm-accept]').click()")
        wait('!document.querySelector(".confirm-overlay")');assert api.installs==[False]
        api.s.update(phase='idle',available=False,backup='0.0.9');wait("!document.getElementById('update-demo-rollback').disabled")
        click('update-demo-rollback');wait("!!document.querySelector('[data-confirm-accept]')")
        ev("document.querySelector('[data-confirm-accept]').click()")
        wait('!document.querySelector(".confirm-overlay")');assert api.installs==[False,True]
        api.s.update(phase='error',recovery=True);wait("!document.getElementById('update-recover').classList.contains('hidden')")
        print('PASS: real backend UI wiring; no demo auto-run; text-only notes; 9 themed layouts; progress/cancel; install+rollback custom confirmations; recovery entry',flush=True)
    except Exception as exc:errors.append(str(exc));print('FAIL:',repr(exc),flush=True)
    finally:window.destroy()
threading.Thread(target=worker,daemon=True).start();webview.start()
if errors:raise SystemExit(1)
