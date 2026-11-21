"""自动化离线小窗回归：使用程序自身 WebView API，不使用 CUA、不登录或连接播放器。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()
import copy
import json
import os
import threading
import time

import webview
from core.capture_window import CaptureWindow, PlaylistFeed

snapshot = {"current": "2", "playing": True, "items": [
    {"id": str(i), "name": ("测试歌名 <script> & 完整标题 " + str(i)) * 2,
     "singer": "歌手甲 / 歌手乙", "requester": "观众小明" if i == 2 else ""}
    for i in range(1, 20)]}
connected = True
errors = []


def fetch():
    if not connected: raise RuntimeError("offline")
    return copy.deepcopy(snapshot)


feed = PlaylistFeed(fetch, ttl=0)


class MockApi:
    def get_state(self): return {"roomid": "", "account": None, "listening": False}
    def poll_events(self): return []
    def get_playlist(self): return fetch()
    def capture_state(self): return controller.state()
    def toggle_capture(self): return controller.toggle()
    def reset_capture_position(self): return controller.reset_position()
    def set_capture_theme(self, theme): return controller.set_theme(theme)


main = webview.create_window("歌单捕捉窗离线回归", os.path.abspath("web/index.html"),
                             js_api=MockApi(), width=1180, height=780, frameless=True)
controller = CaptureWindow(feed, lambda: main)


def wait_for(probe, message, timeout=12):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if probe(): return
        time.sleep(.15)
    raise AssertionError(message)


def ev(window, expression): return window.evaluate_js(expression)


def worker():
    global connected
    original_theme = None
    try:
        wait_for(lambda: main.events.loaded.is_set(), "main window not loaded")
        time.sleep(1)
        original_theme = ev(main, "document.documentElement.dataset.theme")
        ev(main, "loginView(false);window.__errors=[];window.addEventListener('error',e=>window.__errors.push(e.message))")
        for width, height in [(920, 600), (1180, 780), (1440, 900)]:
            main.resize(width, height); time.sleep(.3)
            for theme in ["dark", "light", "haruka"]:
                ev(main, "setTheme(" + json.dumps(theme) + ")"); time.sleep(.15)
                result=json.loads(ev(main, """(()=>{const r=id=>document.getElementById(id).getBoundingClientRect(),s=r('input-song'),ids=['btn-capture-toggle','btn-capture-reset','btn-listen'],bs=ids.map(r),q=document.querySelector('.panels').getBoundingClientRect();return JSON.stringify({below:bs.every(b=>b.top>=s.bottom),sameRow:bs.every(b=>Math.abs(b.top-bs[0].top)<1&&Math.abs(b.height-bs[0].height)<1),adjacent:bs.every((b,i)=>!i||b.left>=bs[i-1].right),inside:bs.every(b=>b.left>=0&&b.right<=innerWidth&&b.bottom<=innerHeight),noOverflow:document.documentElement.scrollWidth===innerWidth,panelHeight:q.height});})()"""))
                assert result['below'] and result['sameRow'] and result['adjacent'] and result['inside'] and result['noOverflow'],result
                assert result['panelHeight']>=150,result
        ev(main,"document.getElementById('btn-capture-toggle').click()")
        wait_for(lambda: controller.state()['visible'] and controller._window is not None, "did not summon child")
        child = controller._window
        wait_for(lambda: child.events.loaded.is_set(), "child not loaded")
        wait_for(lambda: ev(child,"document.querySelectorAll('.song').length===19"), "child snapshot not rendered")
        ev(child,"window.__errors=[];window.addEventListener('error',e=>window.__errors.push(e.message))")
        for width,height in [(300,280),(420,620),(700,850)]:
            child.resize(width,height);time.sleep(.3)
            for theme in ["dark","light","haruka"]:
                controller.set_theme(theme)
                ev(child,"refreshCapture()")
                wait_for(lambda: ev(child,"document.documentElement.dataset.theme") == theme, "theme mismatch")
                result=json.loads(ev(child,"""(()=>{const r=document.getElementById('songs').getBoundingClientRect();return JSON.stringify({rows:document.querySelectorAll('.song').length,active:document.querySelectorAll('[aria-current=true]').length,controls:document.querySelectorAll('button,input').length,overflow:document.documentElement.scrollWidth>innerWidth,listHeight:r.height,playing:document.body.dataset.playing,safe:document.querySelectorAll('#songs script').length===0});})()"""))
                assert result['rows']==19 and result['active']==1 and result['controls']==9 and not result['overflow'] and result['listHeight']>35 and result['safe'],result
                assert result['playing']=='true',result
        assert child.native.Region is not None, 'missing native rounded region'
        drag=json.loads(ev(child,"""JSON.stringify({drag:!!document.elementFromPoint(100,8).closest('.pywebview-drag-region'),icons:document.querySelectorAll('.capture-toolbar svg').length,first:document.querySelector('.capture-toolbar button').id})"""))
        assert drag=={'drag':True,'icons':5,'first':'btn-opacity'},drag
        ev(child,"document.getElementById('btn-opacity').click();document.querySelector('[data-opacity=\"70\"]').click()")
        wait_for(lambda: abs(float(child.native.Opacity)-.7)<.01, 'native opacity not applied')
        assert controller.preferences()['opacity']==70
        wait_for(lambda: ev(child,"!opacitySending"), 'opacity callback pending')
        ev(child,"document.getElementById('btn-pin').click()")
        wait_for(lambda: bool(child.native.TopMost), 'pin not applied')
        wait_for(lambda: ev(child,"!controlBusy&&document.getElementById('btn-pin').getAttribute('aria-pressed')==='true'"), 'pin callback pending')
        ev(child,"document.getElementById('btn-compact').click()")
        wait_for(lambda: ev(child,"document.body.dataset.compact")=='true', 'compact mode failed')
        assert ev(child,"getComputedStyle(document.querySelector('.song-detail')).display")=='none'
        ev(child,"document.getElementById('songs').scrollTop=1000;document.getElementById('btn-current').click()")
        assert ev(child,"document.getElementById('songs').scrollTop")<200
        child.resize(420,620);time.sleep(.3)
        ev(child,"window.pywebview.api.resize_window(450,640,'se')")
        wait_for(lambda: child.width==450 and child.height==640, 'resize API failed')
        assert child.native.Region is not None
        ev(child,"""(()=>{const h=document.querySelector('.edge-se');h.setPointerCapture=()=>{};h.dispatchEvent(new PointerEvent('pointerdown',{pointerId:1,screenX:100,screenY:100}));h.dispatchEvent(new PointerEvent('pointermove',{pointerId:1,screenX:120,screenY:120}));h.dispatchEvent(new PointerEvent('pointerup',{pointerId:1,screenX:120,screenY:120}));})()""")
        wait_for(lambda: child.width==470 and child.height==660,'resize handle event chain failed')
        assert not ev(child,"window.__errors"),'capture JS errors'
        ev(child,"document.getElementById('btn-hide').click()")
        wait_for(lambda: not controller.state()['visible'], 'toolbar hide failed')
        controller.toggle()
        wait_for(lambda: child.native.Visible, 'show after toolbar hide failed')
        assert abs(float(child.native.Opacity)-.7)<.01 and child.native.TopMost
        controller.set_opacity(100);controller.set_pinned(False)
        snapshot['playing']=False
        ev(child,"refreshCapture()")
        wait_for(lambda: ev(child,"document.getElementById('current-state').textContent")=='已暂停',"pause not synchronized")
        snapshot['current']='12'; snapshot['playing']=True
        ev(child,"refreshCapture()")
        wait_for(lambda: ev(child,"document.querySelector('[aria-current=true]').dataset.songId")=='12',"current not synchronized")
        connected=False
        ev(child,"refreshCapture()")
        wait_for(lambda: ev(child,"document.body.dataset.playing")=='false',"disconnect still showing playing")
        assert '上次' in ev(child,"document.getElementById('current-state').textContent")
        connected=True
        ev(child,"refreshCapture()")
        wait_for(lambda: ev(child,"document.body.dataset.playing")=='true',"reconnection failed")
        ev(main,"document.getElementById('btn-capture-toggle').click()")
        wait_for(lambda: not controller.state()['visible'],"did not hide")
        ev(main,"document.getElementById('btn-capture-reset').click()")
        time.sleep(.4)
        assert not controller.state()['visible'],"reset unexpectedly summons child"
        assert not child.native.Visible,"reset unexpectedly showed native hidden window"
        ev(main,"document.getElementById('btn-capture-toggle').click()")
        wait_for(lambda: controller.state()['visible'],"did not reopen")
        assert controller._window is child,"hide/show recreated native window"
        child.move(-15000,-15000)
        ev(main,"document.getElementById('btn-capture-reset').click()")
        wait_for(lambda: child.x > -10000 and child.y > -10000,"position reset failed")
        child.destroy()
        wait_for(lambda: controller._window is None,"child close not reflected")
        wait_for(lambda: ev(main,"document.getElementById('btn-capture-toggle').textContent")=='召唤小窗',"toggle label stale")
        ev(main,"document.getElementById('btn-capture-toggle').click()")
        wait_for(lambda: controller._window is not None,"closed child could not be summoned")
        assert not ev(main,"window.__errors"),"JS errors"
        print('PASS: 9 main layouts; 9 capture layouts; read-only safe text; pause/current/disconnect/reconnect; toggle/reset/close/recreate',flush=True)
    except Exception as exc:
        errors.append(str(exc));print('FAIL: '+repr(exc),flush=True)
    finally:
        if original_theme is not None:
            try: ev(main,'setTheme('+json.dumps(original_theme)+')')
            except Exception: pass
        controller.shutdown()
        main.destroy()


threading.Thread(target=worker,daemon=True).start()
webview.start()
if errors: raise SystemExit(1)
