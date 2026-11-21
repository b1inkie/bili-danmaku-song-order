"""Real GitHub updater: signed metadata, isolated download, user-confirmed install.
Never uses account sessions. Only release whitelist files can be installed.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
import aiohttp
from core.version import VERSION, MANIFEST_URL
from core.update_protocol import parse_manifest, version_tuple, digest, unpack_package, safe_directory, FILES


class Updater:
    def __init__(self, root=None, frozen=None, manifest_url=MANIFEST_URL):
        self.root = Path(root or Path(sys.executable).parent).absolute()
        self.frozen = bool(getattr(sys, 'frozen', False)) if frozen is None else frozen
        self.url = manifest_url  # constructor is internal; never supplied by JS
        self.lock = threading.RLock()
        self.stopped = threading.Event()
        self.cancelled = threading.Event()
        self.worker = None
        self.scheduler = None
        self.manifest = None
        self.transaction = None
        self.raw = self.signature = None
        self.state = dict(phase='idle', current=VERSION, latest=None, available=False,
                          progress=0, message='尚未检查更新', notes='', checkedAt=None,
                          frozen=self.frozen, backup=None, recovery=False)
        self._load_status()
        self._last_status_refresh = 0
        self._restore_ready()

    def _restore_ready(self):
        if not self.frozen or self.state['recovery']: return
        try:
            token=json.loads((self.root/'.update'/'ready.json').read_text('utf-8'))['token']
            if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):return
            tx=safe_directory(self.root/'.update'/token)
            raw=(tx/'latest.json').read_bytes();signature=(tx/'latest.json.sig').read_bytes()
            manifest=parse_manifest(raw,signature)
            if version_tuple(manifest['version'])<=version_tuple(VERSION):return
            for name in FILES:
                if digest(safe_directory(tx/'staged'/name))!=manifest['files'][name]:return
            self.transaction=tx;self.manifest=manifest;self.raw=raw;self.signature=signature
            self.state.update(phase='ready',latest=manifest['version'],available=True,progress=100,notes=manifest['notes'],message='上次下载的更新已验证，可退出并更新')
        except (OSError,ValueError,KeyError): pass

    def _load_status(self):
        if not self.frozen: return
        self.state['backup'] = None
        try:
            backup = safe_directory(self.root/'backup')
            meta = json.loads((backup/'version.json').read_text('utf-8-sig'))
            if digest(backup/FILES[0]) == meta['files'][FILES[0]]:
                version_tuple(meta['version']); self.state['backup'] = meta['version']
        except (OSError, ValueError, KeyError): pass
        try:
            pointer = safe_directory(self.root/'.update'/'pending.json')
            token = json.loads(pointer.read_text('utf-8'))['token']
            if len(token) != 32 or any(c not in '0123456789abcdef' for c in token): return
            result = json.loads(safe_directory(self.root/'.update'/token/'state.json').read_text('utf-8-sig'))
            if result['phase'] == 'complete':
                self.state['message'] = '已完成更新并确认程序启动'
                self.state['recovery'] = False
                if self.state['phase']=='error': self.state['phase']='idle'
                pointer.unlink(missing_ok=True)
            elif result['phase'] in ('failed','restored','needs-attention','replacing','starting','recovering'):
                self.state.update(phase='error', message='上次更新：'+result['message'])
                if result['phase'] in ('failed','restored'):
                    self.state['recovery']=False
                    pointer.unlink(missing_ok=True)
                if result['phase'] in ('needs-attention','replacing','starting','recovering'):
                    self.transaction=safe_directory(self.root/'.update'/token)
                    self.state['recovery']=True
        except (OSError, ValueError, KeyError): pass

    def snapshot(self):
        with self.lock:
            if self.frozen and time.monotonic()-self._last_status_refresh > 3:
                self._last_status_refresh = time.monotonic()
                self._load_status()
            return dict(self.state)

    def _set(self, **values):
        with self.lock: self.state.update(values)

    def start(self):
        if self.scheduler: return
        def schedule():
            if self.stopped.wait(5): return
            while not self.stopped.is_set():
                if self.snapshot()['phase'] not in ('ready','installing'): self.check()
                if self.stopped.wait(4*60*60): return
        self.scheduler = threading.Thread(target=schedule, name='update-check', daemon=True)
        self.scheduler.start()

    def stop(self):
        self.stopped.set(); self.cancelled.set()

    def _spawn(self, task):
        with self.lock:
            if self.worker and self.worker.is_alive(): return False
            def run():
                try: asyncio.run(task())
                except asyncio.CancelledError:
                    self._set(phase='available', progress=0, message='下载已取消')
                except Exception as exc:
                    self._set(phase='error', message=str(exc)[:600])
            self.worker=threading.Thread(target=run,name='updater',daemon=True)
            self.worker.start(); return True

    @staticmethod
    async def _small(session, url, limit):
        async with session.get(url) as response:
            if response.status == 404: return None
            response.raise_for_status()
            if response.url.scheme != 'https': raise ValueError('拒绝非HTTPS更新响应')
            data=bytearray()
            async for block in response.content.iter_chunked(8192):
                data.extend(block)
                if len(data)>limit: raise ValueError('更新响应过大')
            return bytes(data)

    def check(self):
        if self.snapshot()['recovery']: return self.snapshot()
        if self.snapshot()['phase'] in ('ready','installing'): return self.snapshot()
        async def task():
            self._set(phase='checking', message='正在检查 GitHub 正式版本…')
            timeout=aiohttp.ClientTimeout(total=30,connect=10)
            async with aiohttp.ClientSession(timeout=timeout,trust_env=False,headers={'User-Agent':'BiliSongdesk/'+VERSION}) as session:
                raw=await self._small(session,self.url,65536)
                if raw is None:
                    self._set(phase='latest',latest=None,available=False,checkedAt=time.strftime('%Y-%m-%d %H:%M'),message='尚无可用的正式更新；当前版本可继续使用')
                    return
                signature=await self._small(session,self.url+'.sig',1024)
                if signature is None: raise ValueError('更新缺少发布签名，拒绝下载')
                manifest=parse_manifest(raw,signature)
            self.raw,self.signature,self.manifest=raw,signature,manifest
            newer=version_tuple(manifest['version'])>version_tuple(VERSION)
            skipped = None
            if self.frozen:
                try: skipped=json.loads((self.root/'.update'/'skip-version.json').read_text('utf-8'))['version']
                except (OSError,ValueError,KeyError): pass
            suppressed = newer and skipped == manifest['version']
            newer = newer and not suppressed
            self._set(phase='available' if newer else 'latest',latest=manifest['version'],available=newer,
                      notes=manifest['notes'],checkedAt=time.strftime('%Y-%m-%d %H:%M'),
                      message=('已回退并暂缓此版本，可在GitHub手动下载；更高版本仍会提示' if suppressed else '发现新版，可下载更新' if newer else '当前已是最新版'))
        self._spawn(task); return self.snapshot()

    def download(self):
        if self.snapshot()['recovery']:raise ValueError('请先恢复中断的更新')
        if not self.frozen: raise ValueError('源码运行不自动替换工作区，请到GitHub下载便携版')
        if not self.manifest or not self.state['available']: raise ValueError('尚无已验证的新版本')
        if self.snapshot()['phase'] in ('ready','installing'): return self.snapshot()
        self.cancelled.clear()
        async def task():
            manifest=dict(self.manifest)
            token=uuid.uuid4().hex
            tx=safe_directory(self.root/'.update'/token)
            tx.mkdir(parents=True)
            package=tx/'package.zip'
            try:
                if shutil.disk_usage(self.root).free < manifest['size']*3 + 30*1024*1024:
                    raise ValueError('磁盘剩余空间不足，请至少预留更新包三倍空间')
                self._set(phase='downloading',progress=0,message='正在下载完整更新包…')
                timeout=aiohttp.ClientTimeout(total=900,connect=20,sock_read=60)
                async with aiohttp.ClientSession(timeout=timeout,trust_env=False,headers={'User-Agent':'BiliSongdesk/'+VERSION}) as session:
                    async with session.get(manifest['url']) as response:
                        response.raise_for_status()
                        if response.url.scheme!='https': raise ValueError('拒绝非HTTPS下载')
                        received=0
                        with package.open('xb') as output:
                            async for block in response.content.iter_chunked(128*1024):
                                if self.cancelled.is_set() or self.stopped.is_set(): raise asyncio.CancelledError()
                                received+=len(block)
                                if received>manifest['size']: raise ValueError('下载大小超过签名清单')
                                output.write(block)
                                self._set(progress=int(received*100/manifest['size']))
                self._set(phase='verifying',message='验证发布签名与文件校验…')
                if self.cancelled.is_set(): raise asyncio.CancelledError()
                verified=parse_manifest(self.raw,self.signature)
                unpack_package(package,tx/'staged',verified)
                (tx/'latest.json').write_bytes(self.raw)
                (tx/'latest.json.sig').write_bytes(self.signature)
                if self.cancelled.is_set(): raise asyncio.CancelledError()
                self.transaction=tx
                (tx.parent/'ready.json').write_text(json.dumps({'token':token}),encoding='utf-8')
                self._set(phase='ready',progress=100,message='更新包已校验，可在下播后退出并更新')
            except BaseException:
                shutil.rmtree(tx,ignore_errors=True); raise
        self._spawn(task); return self.snapshot()

    def cancel(self):
        if self.snapshot()['phase'] in ('downloading','verifying'):self.cancelled.set()
        return self.snapshot()

    @staticmethod
    def _wait_helper(process, tx):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if (tx/'helper-ready').is_file():
                return
            if process.poll() is not None:
                raise RuntimeError('更新助手未能启动，当前程序不会退出，请检查PowerShell策略或安全软件')
            time.sleep(.1)
        # The helper waits for an explicit go file; no exit means no install.
        process.terminate()
        raise RuntimeError('更新助手启动超时，未替换任何文件')

    def prepare_install(self, rollback=False, test_mode=False):
        """Start a helper waiting for us to exit. Caller must then close the app."""
        if not self.frozen: raise ValueError('源码运行不能自动替换程序')
        if self.snapshot()['recovery']:raise ValueError('请先恢复中断的更新')
        if Path(sys.executable).name.lower()!=FILES[0]: raise ValueError('请保留主程序原文件名：'+FILES[0])
        root=safe_directory(self.root)
        if self.snapshot()['phase']=='installing':raise ValueError('更新事务正在执行')
        if (root/'backup').exists():
            meta_path=safe_directory(root/'backup'/'version.json')
            try:
                prior=json.loads(meta_path.read_text('utf-8-sig'))
                if digest(safe_directory(root/'backup'/FILES[0]))!=prior['files'][FILES[0]]:
                    raise ValueError('备份损坏')
            except (OSError,ValueError,KeyError) as exc:
                raise ValueError('backup目录不是有效版本备份，请先手动备份并移走，不会覆盖其内容') from exc
        if not rollback and self.snapshot()['phase']!='ready':raise ValueError('更新包尚未准备好')
        if rollback:
            backup=safe_directory(root/'backup')
            meta=json.loads((backup/'version.json').read_text('utf-8-sig'))
            version_tuple(meta['version'])
            tx=safe_directory(root/'.update'/uuid.uuid4().hex);(tx/'staged').mkdir(parents=True)
            hashes=meta['files']
            if set(hashes)!=set(FILES):raise ValueError('上一版备份不完整，请手动恢复')
            for name in FILES:
                if digest(safe_directory(backup/name))!=hashes[name]:raise ValueError('备份校验失败')
                shutil.copyfile(backup/name,tx/'staged'/name)
            version=meta['version']
        else:
            tx=safe_directory(self.transaction)
            manifest=parse_manifest((tx/'latest.json').read_bytes(),(tx/'latest.json.sig').read_bytes())
            hashes=manifest['files'];version=manifest['version']
            for name in FILES:
                if digest(safe_directory(tx/'staged'/name))!=hashes[name]:raise ValueError('暂存更新已改变，拒绝安装')
        existing=[name for name in FILES if (root/name).is_file()]
        if FILES[0] not in existing:raise ValueError('未找到当前EXE')
        original={name:digest(safe_directory(root/name)) for name in existing}
        plan=dict(root=str(root),pid=os.getpid(),token=tx.name,version=version,currentVersion=VERSION,
                  currentHash=original[FILES[0]],files=hashes,originalFiles=existing,originalHashes=original,
                  action='rollback' if rollback else 'upgrade',testMode=bool(test_mode))
        (tx/'plan.json').write_text(json.dumps(plan),encoding='utf-8')
        (root/'.update'/'pending.json').write_text(json.dumps({'token':tx.name}),encoding='utf-8')
        helper=Path(__file__).with_name('update-helper.ps1')
        shutil.copyfile(helper,tx/'helper.ps1')
        powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        for marker in ('helper-ready','install-go'):
            (tx/marker).unlink(missing_ok=True)
        process = subprocess.Popen([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                          '-File',str(tx/'helper.ps1'),'-Plan',str(tx/'plan.json')],cwd=str(root),
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self._wait_helper(process, tx)
        (tx/'install-go').write_text('go', encoding='ascii')
        (root/'.update'/'ready.json').unlink(missing_ok=True)
        self._set(phase='installing',message='正在退出点歌台以安装更新…')
        return {'closing':True}

    def recover(self, test_mode=False):
        if not self.frozen or not self.snapshot()['recovery']:
            raise ValueError('没有可恢复的更新事务')
        tx=safe_directory(self.transaction)
        plan=json.loads((tx/'plan.json').read_text('utf-8'))
        if Path(plan['root']).absolute()!=self.root or plan['token']!=tx.name:
            raise ValueError('恢复计划路径异常')
        plan['pid']=os.getpid();plan['testMode']=bool(test_mode)
        (tx/'plan.json').write_text(json.dumps(plan),encoding='utf-8')
        (tx/'state.json').write_text(json.dumps({'phase':'recovering','message':'正在恢复旧版','token':tx.name}),encoding='utf-8')
        shutil.copyfile(Path(__file__).with_name('update-helper.ps1'),tx/'helper.ps1')
        powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        for marker in ('helper-ready','install-go'):
            (tx/marker).unlink(missing_ok=True)
        process = subprocess.Popen([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(tx/'helper.ps1'),'-Plan',str(tx/'plan.json'),'-Recover'],cwd=str(self.root),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self._wait_helper(process, tx)
        (tx/'install-go').write_text('go', encoding='ascii')
        self._set(phase='installing',message='退出后恢复更新前的程序…')
        return {'closing':True}

def acknowledge_startup(token):
    if not getattr(sys,'frozen',False):return False
    if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):raise ValueError('启动确认令牌无效')
    root=Path(sys.executable).parent
    tx=safe_directory(root/'.update'/token)
    plan=json.loads((tx/'plan.json').read_text('utf-8'))
    if plan['version']!=VERSION or digest(sys.executable)!=plan['files'][FILES[0]]:
        raise ValueError('新版启动身份与安装计划不一致')
    temp=tx/'healthy.tmp'
    temp.write_text(json.dumps({'version':VERSION,'token':token}),encoding='utf-8')
    os.replace(temp,tx/'healthy.json')
    return True
