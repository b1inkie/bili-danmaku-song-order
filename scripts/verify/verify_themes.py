"""离线主题回归：不登录、不播放，检查 3 主题/3 尺寸、切换和 OC 加载。"""
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
import tempfile
from pathlib import Path
from core.theme_manager import ThemeManager
_temporary = tempfile.TemporaryDirectory()
_manager = ThemeManager(Path(_temporary.name) / 'themes', install_presets=True)
_preset = _manager.new()  # render the workshop template; Haruka is not an initial preset

class MockApi:
    def get_state(self):
        return {"roomid": "", "account": None, "listening": False}
    def poll_events(self):
        return []
    def theme_catalog(self):
        return _manager.catalog() + [{"id": _preset['config']['id'], "name": "工坊模板预览"}]

window = webview.create_window("主题回归", os.path.abspath('web/index.html'), js_api=MockApi(),
                               width=1180, height=780, frameless=True, easy_drag=False,
                               shadow=False, background_color='#110e14')
window.events.shown += lambda: main_gui.apply_round_region(window)
PROBE = r'''(() => {
  loginView(false);
  const rect = s => { const e=document.querySelector(s), r=e.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom}; };
  const visible = s => getComputedStyle(document.querySelector(s)).display !== 'none';
  const img=document.querySelector('.haruka-oc');
  const hit = (x,y) => !!document.elementFromPoint(x,y)?.closest('.pywebview-drag-region');
  const r={theme:document.documentElement.dataset.theme,viewport:[innerWidth,innerHeight],
    title:rect('.windowbar'),panel:rect('.panels'),footer:rect('.actionbar'),intro:rect('.haruka-intro'),
    scene:visible('.haruka-scene'),image:img.complete&&img.naturalWidth>0,
    genericSignature:visible('.background-signature'),
    noOverflow:document.documentElement.scrollWidth===innerWidth,
    topDrag:hit(100,2)&&hit(500,8),
    active:document.querySelectorAll('[data-theme-choice][aria-checked="true"]').length};
  document.getElementById('btn-theme').click();r.menuOpen=!document.getElementById('theme-menu').classList.contains('hidden');
  closeThemeMenu();return JSON.stringify(r);
})()'''
errors = []
def verify():
    try:
        time.sleep(2)
        for _ in range(30):
            if window.evaluate_js("!!document.querySelector('.haruka-oc')&&document.querySelector('.haruka-oc').complete&&document.querySelector('.haruka-oc').naturalWidth>0"):break
            time.sleep(0.2)
        else:raise AssertionError('OC image load timed out')
        assert main_gui.apply_round_region(window), 'native round region failed'
        original_theme = window.evaluate_js("document.documentElement.dataset.theme")
        window.evaluate_js("window.__errors=[];window.addEventListener('error',e=>window.__errors.push(e.message));")
        results = []
        for w,h in [(1180,780),(920,600),(1440,900)]:
            window.resize(w,h)
            time.sleep(0.4)
            for theme in ['dark','light','haruka']:
                if theme == 'haruka':
                    window.evaluate_js('document.querySelectorAll("[data-theme-choice]").forEach(b=>b.setAttribute("aria-checked","false"));ThemeRuntime.apply(' + json.dumps(_preset) + ');refreshThemeCatalog()')
                else:
                    window.evaluate_js(f"setTheme('{theme}')")
                time.sleep(0.1)
                if theme == 'haruka':
                    for _ in range(30):
                        if window.evaluate_js("document.querySelector('.custom-theme-choice[aria-checked=true]')!==null"): break
                        time.sleep(.1)
                r=json.loads(window.evaluate_js(PROBE))
                results.append(r)
                assert r['image'] and r['noOverflow'] and r['topDrag'] and r['menuOpen'] and r['active']==1, r
                assert r['footer']['bottom']<=h and r['panel']['bottom']<=r['footer']['y'], r
                assert r['scene']==(theme=='haruka'),r
                assert not r['genericSignature'],r
                if theme=='haruka':
                    assert r['panel']['w']<w*0.65 and r['panel']['x']>w*0.38,r
                    assert r['intro']['bottom']<=r['panel']['y'],r
        assert not window.evaluate_js('window.__errors'), 'JS errors'
        window.evaluate_js("setTheme(" + json.dumps(original_theme) + ")")
        print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)
    except Exception as exc:
        errors.append(str(exc))
        print('FAILED: '+str(exc),flush=True)
    finally:
        window.destroy()
        _temporary.cleanup()
threading.Thread(target=verify,daemon=True).start()
webview.start()
if errors:
    raise SystemExit(1)
print('PASS: 9 theme/size combinations',flush=True)
