"""Real isolated main/capture bridge test; proves saved custom theme survives startup and syncs."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()
import json
import tempfile
import threading
import time
from pathlib import Path
import webview
from core.theme_manager import ThemeManager
from core.capture_window import CaptureWindow, PlaylistFeed

class Bridge:
 def __init__(self,manager):self.manager=manager
 def get_state(self):return {'roomid':'','account':None,'listening':False}
 def poll_events(self):return []
 def get_playlist(self):return {'current':None,'playing':False,'items':[]}
 def theme_state(self,revision=None):return self.manager.state(revision)
 def theme_catalog(self):return self.manager.catalog()
 def select_theme(self,theme):return self.manager.select(theme)
 def delete_theme(self,theme):return self.manager.delete(theme)
 def set_capture_theme(self,theme):return {}
 def capture_state(self):return {'visible':False}
 def open_theme_workshop(self):return self.workshop.open()

errors=[]
with tempfile.TemporaryDirectory() as tmp:
 manager=ThemeManager(Path(tmp)/'themes');draft=manager.new()['config'];draft['text']['name']='同步测试';draft['capture']['fontSize']=17
 draft['capture'].update(background='#142536',card='#263748',compact=True)
 draft['colors'].update(text='#f1e2d3',muted='#a1b2c3',accent='#e4a5b6',border='#647586')
 manager.save(draft);manager.select(draft['id']);manager=ThemeManager(manager.root)
 bridge=Bridge(manager)
 from core.theme_workshop import ThemeWorkshop
 bridge.workshop=ThemeWorkshop(manager)
 window=webview.create_window('主题同步离线测试',str(Path('web/index.html').resolve()),js_api=bridge,width=1180,height=780,frameless=True)
 controller=CaptureWindow(PlaylistFeed(bridge.get_playlist),lambda:window);controller.theme_manager=manager
 def wait(check):
  deadline=time.monotonic()+15
  while time.monotonic()<deadline:
   if check():return
   time.sleep(.1)
  raise AssertionError('sync timeout')
 def worker():
  try:
   wait(lambda:window.evaluate_js("document.documentElement.dataset.customTheme||''")==draft['id'])
   assert manager.active==draft['id'],'localStorage initialization overwrote backend selection'
   window.evaluate_js("document.getElementById('btn-theme-workshop').click()")
   wait(lambda:bridge.workshop.window is not None and bridge.workshop.window.events.loaded.is_set())
   editor=bridge.workshop.window
   wait(lambda:editor.evaluate_js("typeof draft!=='undefined' && !!draft && !busy"))
   bridge.workshop.open();assert bridge.workshop.window is editor
   editor.evaluate_js("dirty=false")
   editor.destroy()
   wait(lambda:bridge.workshop.window is None)
   controller.toggle();child=controller._window
   wait(lambda:child.events.loaded.is_set())
   wait(lambda:child.evaluate_js("document.documentElement.dataset.customTheme||''")==draft['id'])
   assert child.evaluate_js("getComputedStyle(document.querySelector('.capture-shell')).fontSize")=='17px'
   capture_style=json.loads(child.evaluate_js("JSON.stringify({bg:getComputedStyle(document.querySelector('.capture-shell')).backgroundColor,card:getComputedStyle(document.querySelector('.current-card')).backgroundColor,text:getComputedStyle(document.body).color,muted:getComputedStyle(document.querySelector('#connection-note')).color,compact:document.body.dataset.themeCompact,singer:getComputedStyle(document.querySelector('#current-singer')).display,image:document.documentElement.style.getPropertyValue('--custom-bg-image')})"))
   assert capture_style=={'bg':'rgb(20, 37, 54)','card':'rgb(38, 55, 72)','text':'rgb(241, 226, 211)','muted':'rgb(161, 178, 195)','compact':'true','singer':'none','image':''},capture_style
   changed=manager.load(draft['id']);changed['text']['name']='更新名称';changed['capture'].update(background='#314253',fontSize=18,compact=False);manager.save(changed)
   time.sleep(1.2)
   assert window.evaluate_js("document.querySelector('.haruka-name>span').textContent")=='同步测试','saving active draft unexpectedly applied'
   manager.select(draft['id'])
   wait(lambda:window.evaluate_js("document.querySelector('.haruka-name>span').textContent")=='更新名称')
   wait(lambda:child.evaluate_js("getComputedStyle(document.querySelector('.capture-shell')).backgroundColor")=='rgb(49, 66, 83)')
   assert child.evaluate_js("getComputedStyle(document.querySelector('.capture-shell')).fontSize")=='18px'
   assert child.evaluate_js("document.body.dataset.themeCompact")=='false'
   assert child.evaluate_js("getComputedStyle(document.querySelector('#current-singer')).display")!='none'
   window.evaluate_js("window.__originalConfirm=window.confirm;window.confirm=()=>false;document.getElementById('btn-theme').click()")
   wait(lambda:window.evaluate_js("document.querySelectorAll('.custom-theme-choice').length")>0)
   window.evaluate_js("document.querySelector('.custom-theme-choice').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:innerWidth-2,clientY:innerHeight-2}))")
   bounds=json.loads(window.evaluate_js("(()=>{const r=document.getElementById('theme-context-menu').getBoundingClientRect();return JSON.stringify({inside:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight});})()"))
   assert bounds['inside'],bounds
   window.evaluate_js("document.querySelector('.theme-delete-action').click();document.querySelector('[data-confirm-cancel]').click()")
   time.sleep(.2)
   assert len(manager.catalog())==1 and manager.active==draft['id'],'cancelled delete changed state'
   window.evaluate_js("document.querySelector('.custom-theme-choice').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:100,clientY:100}));document.querySelector('.theme-delete-action').click();document.querySelector('[data-confirm-accept]').click()")
   wait(lambda:manager.active=='dark' and not manager.catalog())
   wait(lambda:window.evaluate_js("document.documentElement.dataset.theme")=='dark')
   wait(lambda:child.evaluate_js("document.documentElement.dataset.theme")=='dark')
   wait(lambda:window.evaluate_js("document.querySelectorAll('.custom-theme-choice').length")==0)
   assert ThemeManager(manager.root).active=='dark'
   window.evaluate_js("window.confirm=window.__originalConfirm")
   manager.select('light')
   wait(lambda:window.evaluate_js("document.documentElement.dataset.theme")=='light')
   wait(lambda:child.evaluate_js("document.documentElement.dataset.theme")=='light')
   assert not window.evaluate_js("document.documentElement.dataset.customTheme||''")
   assert not child.evaluate_js("document.documentElement.dataset.customTheme||''")
   window.evaluate_js("document.querySelector('[data-theme-choice=light]').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true}))")
   assert not window.evaluate_js("!!document.getElementById('theme-context-menu')"),'builtin theme offers deletion'
   assert not window.evaluate_js("document.querySelector('[data-theme-choice=haruka]')"),'fixed Haruka entry still present'
   manager._install_presets_once()
   manager.select('black-lotus-violet-resonance')
   wait(lambda:window.evaluate_js("document.documentElement.dataset.customTheme")=='black-lotus-violet-resonance')
   wait(lambda:child.evaluate_js("document.documentElement.dataset.customTheme")=='black-lotus-violet-resonance')
   window.evaluate_js("refreshThemeCatalog()")
   wait(lambda:window.evaluate_js("!!document.querySelector('.custom-theme-choice[data-theme-choice=\"black-lotus-violet-resonance\"]')"))
   assert manager.load('black-lotus-violet-resonance')['name']=='黑睡莲·紫锋共振'
   print('PASS: persisted startup selection; main/capture sync; live edit revision; builtin reset and markup restored',flush=True)
  except Exception as exc:
   import traceback;traceback.print_exc();errors.append(str(exc))
  finally:bridge.workshop.shutdown();controller.shutdown();window.destroy()
 threading.Thread(target=worker,daemon=True).start();webview.start()
if errors:raise SystemExit(1)
