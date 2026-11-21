"""Offline real WebView workshop test. Uses only temporary themes/mock player, no CUA."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()
import json
from pathlib import Path
import tempfile
import threading
import time
import webview
from core.theme_manager import ThemeManager
from core.theme_workshop import ThemeWorkshop

errors=[]
with tempfile.TemporaryDirectory() as temporary:
 manager=ThemeManager(Path(temporary)/'themes')
 workshop=ThemeWorkshop(manager)
 workshop.open()
 window=workshop.window
 api=window._js_api
 def ev(code):return window.evaluate_js(code)
 def wait(code):
  deadline=time.monotonic()+15
  while time.monotonic()<deadline:
   if ev(code):return
   time.sleep(.1)
  raise AssertionError('timeout: '+code)
 def worker():
  try:
   wait("typeof draft!=='undefined' && !!draft && !busy && document.querySelectorAll('.field').length>20")
   wait("document.getElementById('theme-preview').contentDocument.documentElement.dataset.customTheme===draft.id")
   assert manager.active=='dark' and not manager.catalog()
   assert ev("document.getElementById('theme-preview').contentDocument.querySelector('.haruka-name>span').textContent")=='这里是名字'
   assert ev("draft.text.signature")=='这里是签名'
   assert not ev("document.getElementById('theme-preview').contentDocument.body.textContent.includes('渚花遥')")
   assert window.native.FormBorderStyle.ToString()=='None'
   assert window.native.Region is not None and not window.native.Region.IsVisible(0,0)
   assert window.native.TransparencyKey.IsEmpty
   assert ev("!!document.elementFromPoint(100,3).closest('.pywebview-drag-region')")
   assert ev("document.getElementById('delete-theme').disabled")
   from unittest.mock import patch
   with patch('os.startfile') as opened:
    ev("document.getElementById('open-theme-directory').click()")
    wait("!busy && document.getElementById('status').textContent.includes('已打开本地主题目录')")
    opened.assert_called_once_with(str(manager.root/'installed'))
   assert len(ev("installedFonts"))>0,'no system fonts enumerated'
   assert ev("document.querySelectorAll('select[id^=font-]').length")==10
   for width in (980,1280):
    window.resize(width,850);time.sleep(.2)
    rows=ev("[...document.querySelectorAll('.text-font-field')].every(f=>{const a=f.querySelector('input').getBoundingClientRect(),b=f.querySelector('select').getBoundingClientRect();return Math.abs(a.top-b.top)<1&&Math.abs(a.height-b.height)<1&&a.right<=b.left&&b.right<=f.getBoundingClientRect().right+1})")
    assert rows,'font/text not aligned at '+str(width)
    assert not ev('document.documentElement.scrollWidth>innerWidth')
   api.resize_window(980,680,'se');time.sleep(.3)
   assert window.native.Region is not None
   assert ev("document.elementFromPoint(innerWidth-3,innerHeight-3).dataset.edge")=='se'
   assert not ev('document.documentElement.scrollHeight>innerHeight||document.documentElement.scrollWidth>innerWidth')
   assert ev("(()=>{const b=document.getElementById('workshop-close'),r=b.getBoundingClientRect();return document.elementFromPoint(r.left+r.width/2,r.top+r.height/2).closest('button')===b})()")
   assert ev("(()=>{const a=document.getElementById('open-theme-directory').getBoundingClientRect(),b=document.getElementById('delete-theme').getBoundingClientRect();return Math.abs(a.top-b.top)<1&&a.right<b.left})()")
   api.window_action('maximize');time.sleep(.5)
   assert window.native.Region is None
   api.window_action('maximize');time.sleep(.5)
   assert window.native.Region is not None
   window.resize(1280,850);time.sleep(.2)
   editor_font=ev("getComputedStyle(document.getElementById('field-text.heading')).fontFamily")
   ev("document.getElementById('font-heading').value='Arial';document.getElementById('font-heading').dispatchEvent(new Event('change'))")
   wait("document.getElementById('theme-preview').contentWindow.getComputedStyle(document.getElementById('theme-preview').contentDocument.querySelector('.haruka-intro h1')).fontFamily.startsWith('Arial')")
   assert ev("getComputedStyle(document.getElementById('field-text.heading')).fontFamily")==editor_font
   assert ev("draft.fonts.heading")=='Arial'
   ev("document.getElementById('font-signature').value='Georgia';document.getElementById('font-signature').dispatchEvent(new Event('change'))")
   wait("document.getElementById('theme-preview').contentWindow.getComputedStyle(document.getElementById('theme-preview').contentDocument.querySelector('.haruka-name em')).fontFamily.startsWith('Georgia')")
   reference=manager.optimize_image((manager.web.parent/'docs/themes/examples/rose-nocturne/assets/character.png').read_bytes())
   url=manager.payload(manager.validate({'schemaVersion':1,'id':'bg-preview','name':'bg','template':'rose-nocturne','background':{'image':reference}}))['assets'][reference]
   ev('assets['+json.dumps(reference)+']='+json.dumps(url)+';put("background.image",'+json.dumps(reference)+')')
   for key,value in [('scale',1.5),('x',120),('y',-80)]:
    ev("(()=>{const e=document.getElementById('field-background."+key+"');e.value="+str(value)+";e.dispatchEvent(new Event('input'));})()")
   wait("document.getElementById('theme-preview').contentDocument.documentElement.style.getPropertyValue('--custom-bg-x')==='120px'")
   transform=ev("(()=>{const f=document.getElementById('theme-preview');return f.contentWindow.getComputedStyle(f.contentDocument.getElementById('app'),'::before').transform})()")
   assert transform=='matrix(1.5, 0, 0, 1.5, 120, -80)',transform
   copied=[]
   api._copy_text=copied.append  # don't overwrite the operator's clipboard during offline regression
   ev("document.getElementById('copy-guide').click()")
   wait("!busy && document.getElementById('status').textContent.includes('已复制 AI 提示词')")
   assert copied and '你不需要程序源码' in copied[0] and 'assets/character.png' in copied[0]
   ev("put('text.heading','自定义标题 <script>无执行</script>');put('text.name','测试主播');put('layout.characterSide','right');put('layout.characterRatio',0.36)")
   wait("document.getElementById('theme-preview').contentDocument.querySelector('.haruka-intro h1').textContent.includes('<script>')")
   wait("document.getElementById('theme-preview').contentDocument.querySelector('.haruka-oc').naturalWidth>0")
   for size in ['920,600','1180,780','1440,900']:
    ev("document.getElementById('preview-size').value="+json.dumps(size)+";fitPreview()")
    time.sleep(.2)
    result=json.loads(ev("(()=>{const f=document.getElementById('theme-preview'),d=f.contentDocument,s=d.querySelector('.haruka-scene').getBoundingClientRect(),b=d.querySelector('.actionbar').getBoundingClientRect();return JSON.stringify({overflow:d.documentElement.scrollWidth>f.contentWindow.innerWidth,sceneLeft:s.left,barRight:b.right,buttons:d.querySelectorAll('.capture-actions button').length})})()"))
    assert not result['overflow'] and result['sceneLeft']>=result['barRight'] and result['buttons']==3,result
   for side in ['left','right']:
    for ratio in [.28,.43]:
     ev("put('layout.characterSide',"+json.dumps(side)+");put('layout.characterRatio',"+str(ratio)+");put('layout.introHeight',140);document.getElementById('preview-size').value='920,600';fitPreview()")
     time.sleep(.2)
     geometry=json.loads(ev("(()=>{const f=document.getElementById('theme-preview'),d=f.contentDocument,p=d.querySelector('.panels').getBoundingClientRect(),b=d.querySelector('.actionbar').getBoundingClientRect(),i=d.querySelector('.haruka-intro').getBoundingClientRect();return JSON.stringify({overflow:d.documentElement.scrollWidth>f.contentWindow.innerWidth,panelBottom:p.bottom,barTop:b.top,introBottom:i.bottom,panelTop:p.top});})()"))
     assert not geometry['overflow'] and geometry['panelBottom']<=geometry['barTop'] and geometry['introBottom']<=geometry['panelTop'],geometry
     layers=json.loads(ev("(()=>{const d=document.getElementById('theme-preview').contentDocument,s=d.querySelector('.haruka-scene'),b=d.querySelector('.actionbar'),i=d.getElementById('input-song'),r=i.getBoundingClientRect(),cs=getComputedStyle(s);const previous=b.style.pointerEvents;b.style.pointerEvents='auto';const hit=d.elementFromPoint(r.left+8,r.top+r.height/2)===i;b.style.pointerEvents=previous;return JSON.stringify({overflow:cs.overflow,pointer:cs.pointerEvents,z:cs.zIndex,barZ:getComputedStyle(b).zIndex,inputHit:hit,fadeWidth:getComputedStyle(s,'::after').width,viewport:d.defaultView.innerWidth});})()"))
     assert layers['overflow']=='visible' and layers['pointer']=='none' and layers['z']=='0' and layers['barZ']=='1' and layers['inputHit'],layers
     assert abs(float(layers['fadeWidth'].removesuffix('px'))-layers['viewport'])<=1,layers
   ev("put('text.vertical','VIOLET · MUSIC');put('text.sceneNumber','02');put('text.sceneTitle','BLACK LOTUS <b>literal</b>');put('text.sectionNumber','B');put('fonts.sceneTitle','Georgia')")
   wait("document.getElementById('theme-preview').contentDocument.querySelector('.scene-title').textContent==='BLACK LOTUS <b>literal</b>'")
   assert ev("document.getElementById('theme-preview').contentDocument.querySelector('.scene-title b')===null")
   assert ev("document.getElementById('theme-preview').contentDocument.querySelector('.haruka-section-no').textContent")=='B'
   ev("put('text.sectionNumber','')")
   wait("document.getElementById('theme-preview').contentWindow.getComputedStyle(document.getElementById('theme-preview').contentDocument.querySelector('.haruka-section-no')).display==='none'")
   ev("put('text.sectionNumber','B')")
   ev("document.getElementById('save-theme').click()")
   wait("!busy && !dirty && document.getElementById('dirty-state').textContent==='已保存'")
   assert manager.active=='dark' and len(manager.catalog())==1
   assert manager.load(manager.catalog()[0]['id'])['text']['sceneTitle']=='BLACK LOTUS <b>literal</b>'
   assert manager.load(manager.catalog()[0]['id'])['fonts']['heading']=='Arial'
   assert manager.load(manager.catalog()[0]['id'])['fonts']['signature']=='Georgia'
   saved_background=manager.load(manager.catalog()[0]['id'])['background']
   assert (saved_background['scale'],saved_background['x'],saved_background['y'])==(1.5,120,-80)
   ev("document.getElementById('apply-theme').click()")
   wait("!busy && document.getElementById('status').textContent.includes('已保存并应用')")
   assert manager.active==manager.catalog()[0]['id']
   ev("document.getElementById('preview-capture').click()")
   wait("document.getElementById('theme-preview').contentDocument?.querySelector('.capture-shell') && document.getElementById('theme-preview').contentDocument.documentElement.dataset.customTheme===draft.id")
   assert ev("document.getElementById('theme-preview').contentDocument.documentElement.style.getPropertyValue('--bg')")=='#1b141e'
   ev("document.getElementById('preview-main').click()")
   wait("document.getElementById('theme-preview').contentDocument?.querySelector('.actionbar') && document.getElementById('theme-preview').contentDocument.documentElement.dataset.customTheme===draft.id")
   time.sleep(.3)  # allow the preview-ready delayed postMessage to settle before explicit reset
   ev("(()=>{const w=document.getElementById('theme-preview').contentWindow;w.setTheme('light');})()")
   assert ev("document.getElementById('theme-preview').contentDocument.documentElement.dataset.customTheme||''")==''
   assert ev("document.getElementById('theme-preview').contentDocument.querySelector('.haruka-name>span').textContent")=='这里是名字'
   assert not ev("document.getElementById('theme-preview').contentDocument.documentElement.style.getPropertyValue('--custom-font-heading')")
   assert not ev("document.getElementById('theme-preview').contentDocument.documentElement.style.getPropertyValue('--custom-bg-scale')")
   assert ev("document.getElementById('theme-preview').contentDocument.querySelector('.scene-title').textContent")=='这里是主题名'
   assert ev("document.getElementById('theme-preview').contentDocument.querySelector('.haruka-section-no').textContent")=='01'
   assert not ev("document.getElementById('delete-theme').disabled")
   ev("document.getElementById('delete-theme').click()")
   wait("!!document.querySelector('[data-confirm-cancel]')")
   ev("document.querySelector('[data-confirm-cancel]').click()")
   wait('!busy')
   assert len(manager.catalog())==1
   ev("document.getElementById('delete-theme').click()")
   wait("!!document.querySelector('[data-confirm-accept]')")
   ev("document.querySelector('[data-confirm-accept]').click()")
   wait("!busy && document.getElementById('status').textContent.includes('主题已删除')")
   assert not manager.catalog() and manager.active=='dark'
   assert ev("document.getElementById('delete-theme').disabled")
   ev("document.getElementById('workshop-close').click()")
   wait("!!document.querySelector('[data-confirm-cancel]')")
   ev("document.querySelector('[data-confirm-cancel]').click()")
   assert workshop.window is window and window.events.loaded.is_set()
   ev('dirty=false')
   print('PASS: rounded workshop region/resize/maximize/drag/control hits; open directory; delete cancel/confirm/fallback; fields/fonts/background preview/save/capture/reset',flush=True)
  except Exception as exc:
   import traceback;traceback.print_exc()
   errors.append(str(exc));print('FAIL:',repr(exc),flush=True)
  finally:workshop.shutdown()
 threading.Thread(target=worker,daemon=True).start()
 webview.start()
if errors:raise SystemExit(1)
