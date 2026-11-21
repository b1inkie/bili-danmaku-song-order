"""Real workshop WebView + signed test catalog/download, isolated files, mock HTTPS.
No GitHub publication, login, player or clipboard changes.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
ROOT,OUTPUT=setup()
import base64,json,tempfile,threading,time
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from core.theme_catalog import CATALOG_URL,parse_catalog
from core.theme_manager import ThemeManager
from core.theme_workshop import ThemeWorkshop
from tools.make_theme_catalog import build_catalog
import webview

errors=[]
with tempfile.TemporaryDirectory() as temporary:
 root=Path(temporary);key=Ed25519PrivateKey.generate()
 source=root/'source';source.mkdir()
 (source/'theme.json').write_text(json.dumps({'schemaVersion':1,'id':'online-ui','name':'在线测试主题',
     'author':'test','description':'<b>这不是HTML</b>','version':'1.0.0','template':'rose-nocturne',
     'capture':{'fontSize':18,'compact':True}}),encoding='utf-8')
 output=root/'assets';entries=build_catalog([source],output,'0.1.1',key)
 public=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
 responses={CATALOG_URL:(output/'catalog.json').read_bytes(),CATALOG_URL+'.sig':(output/'catalog.json.sig').read_bytes(),
            entries[0]['url']:(output/'online-ui-1.0.0.songtheme').read_bytes()}
 class Response:
  status=200;url=SimpleNamespace(scheme='https')
  def __init__(self,data):self.data=data
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  def raise_for_status(self):pass
  @property
  def content(self):return self
  async def iter_chunked(self,size):yield self.data
 class Session:
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  def get(self,url):return Response(responses[url])
 manager=ThemeManager(root/'recipient');workshop=ThemeWorkshop(manager);workshop.open();window=workshop.window
 def ev(code):return window.evaluate_js(code)
 def wait(code):
  end=time.monotonic()+15
  while time.monotonic()<end:
   if ev(code):return
   time.sleep(.08)
  raise AssertionError('timeout: '+code)
 def click(name):ev('document.getElementById('+json.dumps(name)+').click()')
 def worker():
  try:
   wait("typeof draft!=='undefined' && !!draft && !busy")
   click('open-online-themes')
   wait("!document.getElementById('online-theme-modal').classList.contains('hidden')")
   click('online-theme-refresh');wait("document.querySelectorAll('.online-theme-item').length===1")
   assert ev("document.querySelector('.online-theme-item').textContent.includes('<b>这不是HTML</b>')")
   assert not ev("document.querySelector('.online-theme-item b')")
   for width,height in [(980,680),(1280,850)]:
    window.resize(width,height);time.sleep(.3)
    geometry=json.loads(ev("(()=>{const c=document.querySelector('.online-theme-card'),r=c.getBoundingClientRect();return JSON.stringify({inside:r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight,overflow:c.scrollWidth>c.clientWidth,bg:getComputedStyle(c).backgroundColor});})()"))
    assert geometry['inside'] and not geometry['overflow'] and geometry['bg']!='rgba(0, 0, 0, 0)',geometry
   ev("document.querySelector('.online-theme-item button').click()")
   wait("!document.getElementById('online-theme-load').classList.contains('hidden')")
   assert len(manager.catalog())==1 and manager.active=='dark'
   click('online-theme-load');wait("!!document.querySelector('[data-confirm-cancel]')")
   ev("document.querySelector('[data-confirm-cancel]').click()")
   assert ev("!document.getElementById('online-theme-modal').classList.contains('hidden')")
   click('online-theme-load');wait("!!document.querySelector('[data-confirm-accept]')")
   ev("document.querySelector('[data-confirm-accept]').click()")
   wait("draft.id==='online-ui' && !busy")
   assert manager.active=='dark'
   click('open-online-themes');wait("document.querySelectorAll('.online-theme-item').length===1")
   ev("document.querySelector('.online-theme-item button').click()")
   wait("!!document.querySelector('[data-confirm-cancel]')")
   ev("document.querySelector('[data-confirm-cancel]').click()")
   assert len(manager.catalog())==1
   ev("document.querySelector('.online-theme-item button').click()")
   wait("!!document.querySelector('[data-confirm-accept]')")
   ev("document.querySelector('[data-confirm-accept]').click()")
   end=time.monotonic()+10
   while len(manager.catalog())<2 and time.monotonic()<end:time.sleep(.1)
   assert len(manager.catalog())==2 and manager.active=='dark'
   ev("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
   assert ev("document.getElementById('online-theme-modal').classList.contains('hidden')")
   ev('dirty=false')
   print('PASS: online library actual bridge/signed refresh/install; plain-text metadata; minimum layout; modified-draft cancel/accept; duplicate copy cancel/confirm; no auto-apply',flush=True)
  except Exception as exc:errors.append(str(exc));print('FAIL:',repr(exc),flush=True)
  finally:workshop.shutdown()
 with patch('core.theme_catalog.aiohttp.ClientSession',return_value=Session()),patch('core.theme_catalog.parse_catalog',side_effect=lambda r,s:parse_catalog(r,s,public)):
  threading.Thread(target=worker,daemon=True).start();webview.start()
if errors:raise SystemExit(1)
