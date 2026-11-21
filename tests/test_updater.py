"""Real updater protocol regression, temporary files and generated test signing keys only."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from core.update_protocol import parse_manifest, unpack_package, version_tuple, digest, FILES
from core.updater import Updater

class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.key=Ed25519PrivateKey.generate()
        self.public=base64.b64encode(self.key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
        self.files={name:(b'MZ-test-executable' if name.endswith('.exe') else name.encode()) for name in FILES}
        self.package=self.root/'package.zip'
        self.write_package()
        self.manifest=dict(schemaVersion=1,platform='windows-x64',version='0.2.0',minimumUpdaterVersion=1,
            url='https://github.com/b1inkie/bili-danmaku-song-order/releases/download/v0.2.0/test.zip',
            size=self.package.stat().st_size,sha256=digest(self.package),exeSha256=hashlib.sha256(self.files[FILES[0]]).hexdigest(),
            files={name:hashlib.sha256(value).hexdigest() for name,value in self.files.items()},notes='test')
    def write_package(self,extra=None):
        with zipfile.ZipFile(self.package,'w') as archive:
            from core.version import APP_NAME
            for name,value in self.files.items():archive.writestr(APP_NAME+'/'+name,value)
            for name,value in (extra or {}).items():archive.writestr(name,value)
    def signed(self,data=None):
        raw=json.dumps(data or self.manifest).encode();return raw,base64.b64encode(self.key.sign(raw))
    def test_signed_manifest_valid_and_tampering_rejected(self):
        raw,sig=self.signed();self.assertEqual(parse_manifest(raw,sig,self.public),self.manifest)
        with self.assertRaises(ValueError):parse_manifest(raw+b' ',sig,self.public)
        with self.assertRaises(ValueError):parse_manifest(raw,b'invalid',self.public)
    def test_manifest_restricts_platform_url_sizes_and_file_whitelist(self):
        for key,value in [('url','https://example.org/test.zip'),('url','http://github.com/test.zip'),('platform','linux'),
                          ('size',True),('minimumUpdaterVersion',999),('version','0.2.0-beta'),('files',{'config.json':'0'*64})]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                raw,sig=self.signed({**self.manifest,key:value});parse_manifest(raw,sig,self.public)
    def test_version_comparison(self):
        self.assertGreater(version_tuple('1.10.0'),version_tuple('1.9.0'))
        for version in ('01.0.0','1.0','-1.0.0','1.0.0-beta',None):
            with self.assertRaises(ValueError):version_tuple(version)
    def test_archive_self_contained_preserves_user_files(self):
        user=self.root/'user';user.mkdir();(user/'config.json').write_text('private')
        stage=unpack_package(self.package,user/'staged',self.manifest)
        self.assertEqual({x.name for x in stage.iterdir()},set(FILES))
        self.assertEqual((user/'config.json').read_text(),'private')
    def test_archive_rejects_unexpected_paths_and_data_files(self):
        from core.version import APP_NAME, EXE_NAME
        for name in ('../evil.exe',APP_NAME+'/config.json',APP_NAME+'/song_blacklist.txt',APP_NAME+'/CON',APP_NAME+'/'+EXE_NAME+':stream'):
            self.write_package({name:b'bad'})
            manifest={**self.manifest,'size':self.package.stat().st_size,'sha256':digest(self.package)}
            with self.subTest(name=name),self.assertRaises(ValueError):unpack_package(self.package,self.root/'bad',manifest)
    def test_archive_hash_failure(self):
        self.package.write_bytes(b'broken')
        with self.assertRaises(ValueError):unpack_package(self.package,self.root/'bad',self.manifest)
    def test_source_install_forbidden(self):
        updater=Updater(self.root,frozen=False)
        with self.assertRaisesRegex(ValueError,'源码'):updater.download()
        with self.assertRaisesRegex(ValueError,'源码'):updater.prepare_install()
    def test_corrupt_backup_not_offered(self):
        backup=self.root/'backup';backup.mkdir();(backup/FILES[0]).write_bytes(b'changed')
        (backup/'version.json').write_text(json.dumps({'version':'0.0.1','files':{FILES[0]:'0'*64}}))
        self.assertIsNone(Updater(self.root,frozen=True).snapshot()['backup'])
    def test_scheduler_five_seconds_and_four_hours(self):
        updater=Updater(self.root,frozen=False)
        delays=[]
        class Event:
            def wait(self,seconds):delays.append(seconds);return len(delays)>1
            def is_set(self):return False
        updater.stopped=Event()
        with patch('threading.Thread') as thread,patch.object(updater,'check') as check:
            updater.start();thread.call_args.kwargs['target']()
            self.assertEqual(delays,[5,4*60*60]);check.assert_called_once()

class CheckDownloadTests(ProtocolTests):
    def test_real_check_download_verify_and_restart_ready_with_mock_transport(self):
        from unittest.mock import AsyncMock
        from types import SimpleNamespace
        raw,sig=self.signed()
        updater=Updater(self.root/'portable',frozen=True)
        package=self.package.read_bytes()
        class Response:
            status=200
            url=SimpleNamespace(scheme='https')
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            def raise_for_status(self):pass
            @property
            def content(self):return self
            async def iter_chunked(self,size):
                yield package[:20];yield package[20:]
        class Session:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            def get(self,*args,**kwargs):return Response()
        validate=lambda r,s:parse_manifest(r,s,self.public)
        with patch('core.updater.aiohttp.ClientSession',return_value=Session()),patch('core.updater.parse_manifest',side_effect=validate):
            with patch.object(updater,'_small',new=AsyncMock(side_effect=[raw,sig])):
                updater.check();updater.worker.join(5)
            self.assertEqual(updater.snapshot()['phase'],'available')
            updater.download();updater.worker.join(5)
            self.assertEqual(updater.snapshot()['phase'],'ready',updater.snapshot())
            self.assertEqual(updater.snapshot()['progress'],100)
            restored=Updater(updater.root,frozen=True)
            self.assertEqual(restored.snapshot()['phase'],'ready')
            self.assertEqual(restored.snapshot()['latest'],'0.2.0')
            self.assertEqual((restored.transaction/'staged'/FILES[0]).read_bytes(),self.files[FILES[0]])

    def test_missing_release_and_bad_signature_never_offer_update(self):
        from unittest.mock import AsyncMock
        for responses in ([None],[b'{}',b'bad-signature']):
            updater=Updater(self.root,frozen=False)
            with patch.object(updater,'_small',new=AsyncMock(side_effect=responses)):
                updater.check();updater.worker.join(5)
            self.assertFalse(updater.snapshot()['available'])
            self.assertIn(updater.snapshot()['phase'],('latest','error'))

if __name__=='__main__':unittest.main()
