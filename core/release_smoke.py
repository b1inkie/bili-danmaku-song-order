"""Explicit packaged GUI verification. Never loads login settings or connects a player."""
import json
from pathlib import Path
import sys
import threading
import time
import webview
from core.app_dir import get_web_dir
from core.version import VERSION


def run():
    class API:
        def get_state(self): return {'roomid':'','account':None,'listening':False}
        def poll_events(self): return []
        def get_playlist(self): return {'items':[],'current':None,'playing':False}
        def player_status(self): return {'ready':False,'message':'Release verification — no player connection'}
        def capture_window_state(self): return {'visible':False}
        def get_blacklist(self): return ''
        def get_queue_policy(self): return {'enabled':False,'maximum':10}
        def update_state(self): return dict(phase='idle',current=VERSION,latest=None,available=False,progress=0,message='离线构建验证',backup=None,notes='',checkedAt=None,frozen=True)
        def frontend_ready(self):
            if '--release-smoke-fail' in sys.argv: return False
            if '--update-health' in sys.argv:
                from core.updater import acknowledge_startup
                acknowledge_startup(sys.argv[sys.argv.index('--update-health')+1])
            return True
    window=webview.create_window('Bili Songdesk — release verification',str(Path(get_web_dir())/'index.html'),js_api=API(),width=1000,height=700,frameless=True,easy_drag=False)
    errors=[]
    def check():
        try:
            for _ in range(100):
                if window.events.loaded.is_set() and window.evaluate_js("!!window.__songdeskFrontendReady"):break
                time.sleep(.1)
            else: raise RuntimeError('packaged frontend bridge not ready')
            assert window.evaluate_js("document.getElementById('update-demo-current').textContent.includes('"+VERSION+"')")
            time.sleep(2)
        except Exception as exc:errors.append(str(exc))
        finally:window.destroy()
    threading.Thread(target=check,daemon=True).start()
    webview.start()
    if errors:raise SystemExit(2)
