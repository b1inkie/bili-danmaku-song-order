"""Online library tests with test signing keys and mocked HTTPS; no user/network writes."""
import base64
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
from PIL import Image
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from core.theme_catalog import ThemeCatalog, parse_catalog, compatible
from core.theme_manager import ThemeManager
from tools.make_theme_catalog import build_catalog


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.key=Ed25519PrivateKey.generate()
        self.public=base64.b64encode(self.key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
        source=self.root/'source';(source/'assets').mkdir(parents=True)
        Image.new('RGBA',(30,40),(120,50,80,90)).save(source/'assets/character.png')
        self.config={'schemaVersion':1,'id':'online-test','name':'测试主题','version':'1.0.0','template':'rose-nocturne',
                     'character':{'image':'assets/character.png'},'capture':{'fontSize':18,'compact':True}}
        (source/'theme.json').write_text(json.dumps(self.config),encoding='utf-8');self.source=source
        self.output=self.root/'assets'
        build_catalog([source],self.output,'0.1.1',self.key)
        self.raw=(self.output/'catalog.json').read_bytes();self.sig=(self.output/'catalog.json.sig').read_bytes()
        self.data=parse_catalog(self.raw,self.sig,self.public);self.entry=self.data['themes'][0]
        self.package=(self.output/'online-test-1.0.0.songtheme').read_bytes()
        self.manager=ThemeManager(self.root/'recipient');self.catalog=ThemeCatalog(self.manager)
        self.addCleanup(self.catalog.close)

    def sign(self,data):
        raw=json.dumps(data).encode();return raw,base64.b64encode(self.key.sign(raw))

    def test_catalog_signature_and_tamper(self):
        self.assertEqual(self.data['themes'][0]['id'],'online-test')
        with self.assertRaises(ValueError):parse_catalog(self.raw+b' ',self.sig,self.public)
        with self.assertRaises(ValueError):parse_catalog(self.raw,b'bad',self.public)

    def test_catalog_rejects_urls_versions_and_duplicate_ids(self):
        for key,value in [('url','https://example.com/a.songtheme'),('url',self.entry['url']+'?bad'),
                          ('size',True),('sha256','bad'),('id','../bad'),('version','1.0'),('minimumAppVersion','foo')]:
            data=copy.deepcopy(self.data);data['themes'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):parse_catalog(*self.sign(data),self.public)
        with self.assertRaises(ValueError):parse_catalog(*self.sign({'schemaVersion':1,'themes':[self.entry,self.entry]}),self.public)

    def test_future_theme_disables_install(self):
        self.assertTrue(compatible({**self.entry,'themeSchemaVersion':2}))
        self.assertTrue(compatible({**self.entry,'minimumAppVersion':'99.0.0'}))
        self.catalog.entries=[{**self.entry,'themeSchemaVersion':2}]
        with self.assertRaises(ValueError):self.catalog.install('online-test','1.0.0')

    def test_publisher_deterministic_and_same_version_immutable(self):
        before=(self.output/'online-test-1.0.0.songtheme').read_bytes()
        build_catalog([self.source],self.output,'0.1.1',self.key)
        self.assertEqual(before,(self.output/'online-test-1.0.0.songtheme').read_bytes())
        changed={**self.config,'text':{'heading':'不同'}}
        (self.source/'theme.json').write_text(json.dumps(changed),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'提升'):build_catalog([self.source],self.output,'0.1.1',self.key)

    def test_refresh_uses_signed_catalog_and_no_account_session(self):
        check=lambda raw,sig:parse_catalog(raw,sig,self.public)
        with patch.object(self.catalog,'_bytes',new=AsyncMock(side_effect=[self.raw,self.sig])),patch('core.theme_catalog.parse_catalog',side_effect=check):
            self.catalog.refresh();self.catalog.worker.join(5)
        self.assertEqual(self.catalog.snapshot()['phase'],'ready')
        self.assertEqual(len(self.catalog.snapshot()['themes']),1)

    def test_missing_catalog_friendly_and_bad_signature_keeps_installed(self):
        with patch.object(self.catalog,'_bytes',new=AsyncMock(return_value=None)):
            self.catalog.refresh();self.catalog.worker.join(5)
        self.assertFalse(self.catalog.snapshot()['available'])
        with patch.object(self.catalog,'_bytes',new=AsyncMock(side_effect=[self.raw,b'bad'])):
            self.catalog.refresh();self.catalog.worker.join(5)
        self.assertEqual(self.catalog.snapshot()['phase'],'error')
        self.assertEqual(self.manager.catalog(),[])

    def download(self,payload=None,entry=None):
        self.catalog.entries=[entry or self.entry];body=self.package if payload is None else payload
        class Response:
            url=SimpleNamespace(scheme='https')
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            def raise_for_status(self):pass
            @property
            def content(self):return self
            async def iter_chunked(self,size):yield body
        class Session:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            def get(self,*args,**kwargs):return Response()
        with patch('core.theme_catalog.aiohttp.ClientSession',return_value=Session()):
            self.catalog.install('online-test','1.0.0');self.catalog.worker.join(10)
        return self.catalog.snapshot()

    def test_download_empty_receiver_install_export_import(self):
        state=self.download();self.assertEqual(state['phase'],'installed',state)
        self.assertEqual(self.manager.active,'dark')
        config=self.manager.load(state['installedId']);self.assertEqual(config['capture']['fontSize'],18)
        target=self.root/'shared.songtheme';self.manager.export_pack(config['id'],target)
        recipient=ThemeManager(self.root/'third-user');received=recipient.import_pack(target)
        self.assertTrue(received['assets']);self.assertTrue(received['config']['capture']['compact'])
        self.assertEqual(self.catalog.snapshot()['themes'][0]['installedVersion'],'1.0.0')

    def test_existing_modified_active_theme_never_overwritten(self):
        original=self.manager.validate({**self.config,'character':{'image':''},'text':{'heading':'我的修改'}})
        self.manager.save(original);before=self.manager.select(original['id'])
        state=self.download();self.assertEqual(state['phase'],'installed',state)
        self.assertNotEqual(state['installedId'],original['id'])
        self.assertEqual(self.manager.load(original['id'])['text']['heading'],'我的修改')
        self.assertEqual(self.manager.state(),before)
        self.assertEqual(len(self.manager.catalog()),2)
        self.manager.delete(state['installedId'])
        self.assertEqual(len(self.manager.catalog()),1) # refresh never reinstalls deleted data

    def test_wrong_hash_or_identity_has_no_install(self):
        self.assertEqual(self.download(b'corrupt')['phase'],'error')
        self.assertEqual(self.manager.catalog(),[])
        entry={**self.entry,'name':'清单名称不匹配'}
        self.assertEqual(self.download(entry=entry)['phase'],'error')
        self.assertEqual(self.manager.catalog(),[])

    def test_arbitrary_or_stale_request_rejected(self):
        self.catalog.entries=[self.entry]
        for args in [('unknown','1.0.0'),('online-test','9.0.0')]:
            with self.assertRaises(ValueError):self.catalog.install(*args)
        self.catalog.close()
        with self.assertRaises(ValueError):self.catalog.refresh()

class PublisherTests(CatalogTests):
    def test_publish_is_prerelease_and_never_latest(self):
        from tools.publish_theme_catalog import publish
        class API:
            def __init__(self):self.calls=[]
            def request(self,path,method='GET',data=None):
                self.calls.append((path,method,data))
                if method=='GET':return []
                if path.endswith('/releases') and method=='POST':
                    return {'id':1,'upload_url':'https://uploads.github.com/test{?name}', 'html_url':'https://github.com/test'}
                if path.startswith('https://uploads'):
                    return {'digest':'sha256:'+__import__('hashlib').sha256(data).hexdigest(),'size':len(data)}
                return {}
        api=API()
        with patch('tools.publish_theme_catalog.parse_catalog',return_value=self.data):
            publish(self.output,api)
        creates=[data for path,method,data in api.calls if path.endswith('/releases') and method=='POST']
        self.assertTrue(creates[0]['draft']);self.assertTrue(creates[0]['prerelease'])
        self.assertEqual(creates[0]['make_latest'],'false')
        final=api.calls[-1][2]
        self.assertFalse(final['draft']);self.assertTrue(final['prerelease']);self.assertEqual(final['make_latest'],'false')
        uploads=[path for path,method,data in api.calls if path.startswith('https://uploads')]
        self.assertIn('online-test-1.0.0.songtheme',uploads[0])
        self.assertTrue(uploads[-1].endswith('catalog.json'))

    def test_remote_immutable_mismatch_rejects_before_any_mutation(self):
        from tools.publish_theme_catalog import publish
        calls=[]
        class API:
            def request(self,path,method='GET',data=None):
                calls.append(method)
                if '/assets?' in path:return [{'id':2,'name':'online-test-1.0.0.songtheme','digest':'sha256:wrong'}]
                return [{'id':1,'tag_name':'theme-assets','prerelease':True}]
        with patch('tools.publish_theme_catalog.parse_catalog',return_value=self.data):
            with self.assertRaisesRegex(ValueError,'提升版本'):publish(self.output,API())
        self.assertEqual(set(calls),{'GET'})

if __name__=='__main__':unittest.main()
