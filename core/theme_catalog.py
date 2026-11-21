"""Same-repository signed theme library. Never carries Bilibili credentials.
Only validated data/image packs are installed; existing themes are copied, never replaced.
"""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import re
import tempfile
import threading
from urllib.parse import urlparse

import aiohttp
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from core.version import REPOSITORY, UPDATE_PUBLIC_KEY, VERSION
from core.update_protocol import version_tuple
from core.theme_manager import ThemeManager, MAX_TOTAL, read_json, _atomic

CATALOG_URL = f"https://github.com/{REPOSITORY}/releases/download/theme-assets/catalog.json"
MAX_CATALOG = 256 * 1024
MAX_THEMES = 200


def parse_catalog(raw, signature, public_key=UPDATE_PUBLIC_KEY):
    if len(raw) > MAX_CATALOG or len(signature) > 1024:
        raise ValueError("在线主题清单过大")
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(
            base64.b64decode(signature.strip(), validate=True), raw)
    except Exception as exc:
        raise ValueError("主题清单签名无效，请稍后刷新；不会安装未验证内容") from exc
    data = read_json(raw.decode('utf-8'))
    if (not isinstance(data, dict) or set(data) != {'schemaVersion', 'themes'}
            or type(data['schemaVersion']) is not int or data['schemaVersion'] != 1):
        raise ValueError("在线主题清单格式不兼容")
    if not isinstance(data['themes'], list) or len(data['themes']) > MAX_THEMES:
        raise ValueError("在线主题数量超限")
    ids, urls = set(), set()
    fields = {'id', 'name', 'author', 'description', 'version', 'themeSchemaVersion',
              'minimumAppVersion', 'url', 'size', 'sha256'}
    for entry in data['themes']:
        if not isinstance(entry, dict) or set(entry) != fields:
            raise ValueError("在线主题字段不完整或含未知字段")
        theme_id = entry['id']
        if (not isinstance(theme_id, str) or not re.fullmatch(r'[a-z][a-z0-9-]{2,47}', theme_id)
                or theme_id in ('dark', 'light', 'haruka') or theme_id in ids):
            raise ValueError("在线主题ID重复或无效")
        ids.add(theme_id)
        for key, limit in (('name', 40), ('author', 60), ('description', 300)):
            if (not isinstance(entry[key], str) or len(entry[key]) > limit
                    or any(ord(c) < 32 for c in entry[key])):
                raise ValueError("在线主题文字无效")
        if not entry['name'].strip(): raise ValueError("在线主题名称为空")
        version_tuple(entry['version']); version_tuple(entry['minimumAppVersion'])
        if type(entry['themeSchemaVersion']) is not int or entry['themeSchemaVersion'] < 1:
            raise ValueError("主题格式版本无效")
        if type(entry['size']) is not int or not 1 <= entry['size'] <= MAX_TOTAL:
            raise ValueError("主题包大小无效")
        if not isinstance(entry['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
            raise ValueError("主题包校验值无效")
        if not isinstance(entry['url'], str): raise ValueError("主题包地址无效")
        url = urlparse(entry['url'])
        # Immutable versioned filenames. No arbitrary URLs from either the UI or catalog.
        expected = f'/{REPOSITORY}/releases/download/theme-assets/{theme_id}-{entry["version"]}.songtheme'
        if (url.scheme != 'https' or url.netloc != 'github.com' or url.path != expected
                or url.query or url.fragment or entry['url'] in urls):
            raise ValueError("主题下载地址不属于本仓库专用主题Release")
        urls.add(entry['url'])
    return data


def compatible(entry):
    if entry['themeSchemaVersion'] != 1:
        return "需要支持新版主题格式的程序，请先更新点歌台"
    if version_tuple(entry['minimumAppVersion']) > version_tuple(VERSION):
        return "需要点歌台 v" + entry['minimumAppVersion'] + " 或更高版本"
    return ""


class ThemeCatalog:
    def __init__(self, manager):
        self.manager = manager
        self.lock = threading.RLock()
        self.worker = None
        self.closed = threading.Event()
        self.entries = []
        self.state = {'phase': 'idle', 'message': '点击刷新获取在线主题，不会自动安装',
                      'progress': 0, 'installedId': None, 'task': 0, 'available': False}

    def _set(self, **values):
        with self.lock: self.state.update(values)

    def snapshot(self):
        with self.lock, self.manager.lock:
            result = dict(self.state)
            # Receipts are informational only. Never trust them for replacing files.
            receipts = self._receipts()
            installed = {c['id']: c for c in self.manager.catalog()}
            items = []
            for entry in self.entries:
                item = dict(entry)
                local = [c for c in receipts if c['sourceId'] == entry['id'] and c['installedId'] in installed]
                matching = [c for c in local if c['version'] == entry['version']]
                local_id = matching[-1]['installedId'] if matching else (entry['id'] if entry['id'] in installed else None)
                local_version = (installed[local_id]['version'] if local_id else
                                 installed[local[-1]['installedId']]['version'] if local else None)
                if local_id is None and local: local_id = local[-1]['installedId']
                item.update(installedId=local_id, installedVersion=local_version,
                            reason=compatible(entry), compatible=not compatible(entry))
                items.append(item)
            result['themes'] = items
            return result

    def _receipts(self):
        try:
            value = read_json((self.manager.root/'online-installations.json').read_text('utf-8'))
            if not isinstance(value, list): return []
            return [x for x in value[-1000:] if isinstance(x, dict)
                    and all(isinstance(x.get(k), str) for k in ('sourceId', 'installedId', 'version'))]
        except (OSError, ValueError, TypeError): return []

    def _start(self, phase, task):
        with self.lock:
            if self.closed.is_set(): raise ValueError("主题库已关闭")
            if self.worker and self.worker.is_alive(): raise ValueError("主题库正在处理，请稍候")
            self.state.update(phase=phase, progress=0, installedId=None, task=self.state['task'] + 1)
            def run():
                try: asyncio.run(task())
                except Exception as exc:
                    self._set(phase='error', message=str(exc)[:500])
            self.worker = threading.Thread(target=run, name='theme-library', daemon=True)
            self.worker.start()
        return self.snapshot()

    @staticmethod
    async def _bytes(session, url, limit, missing=False):
        async with session.get(url) as response:
            if response.status == 404 and missing: return None
            response.raise_for_status()
            if response.url.scheme != 'https': raise ValueError("拒绝非HTTPS主题响应")
            data = bytearray()
            async for block in response.content.iter_chunked(65536):
                data.extend(block)
                if len(data) > limit: raise ValueError("主题下载超过大小限制")
            return bytes(data)

    def refresh(self):
        async def task():
            self._set(message='正在获取同仓库的签名主题清单…')
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35, connect=10),
                                            trust_env=False, headers={'User-Agent':'BiliSongdesk-themes/'+VERSION}) as session:
                raw = await self._bytes(session, CATALOG_URL, MAX_CATALOG, missing=True)
                if raw is None:
                    with self.lock: self.entries = []
                    self._set(phase='ready', available=False, message='在线主题库尚未发布，可继续导入本地主题包')
                    return
                sig = await self._bytes(session, CATALOG_URL+'.sig', 1024)
                data = parse_catalog(raw, sig)
            if self.closed.is_set(): return
            with self.lock: self.entries = data['themes']
            self._set(phase='ready', available=True, message=f'已验证在线清单，共{len(data["themes"])}套主题')
        return self._start('refreshing', task)

    def install(self, theme_id, version):
        with self.lock:
            entry = next((dict(x) for x in self.entries if x['id'] == theme_id and x['version'] == version), None)
        if entry is None: raise ValueError("主题清单已变化，请刷新后重试")
        reason = compatible(entry)
        if reason: raise ValueError(reason)
        async def task():
            self._set(message='正在下载主题包；不会改变当前主题…')
            with tempfile.TemporaryDirectory(prefix='songdesk-online-theme-') as temporary:
                package = Path(temporary)/'download.songtheme'
                timeout = aiohttp.ClientTimeout(total=240, connect=15, sock_read=45)
                async with aiohttp.ClientSession(timeout=timeout, trust_env=False,
                                                headers={'User-Agent':'BiliSongdesk-themes/'+VERSION}) as session:
                    async with session.get(entry['url']) as response:
                        response.raise_for_status()
                        if response.url.scheme != 'https': raise ValueError("拒绝非HTTPS主题包")
                        received, sha = 0, hashlib.sha256()
                        with package.open('xb') as output:
                            async for block in response.content.iter_chunked(65536):
                                if self.closed.is_set(): raise ValueError("工坊已关闭，已取消主题下载")
                                received += len(block)
                                if received > entry['size']: raise ValueError("主题包超过签名清单大小")
                                sha.update(block); output.write(block)
                                self._set(progress=int(received * 100 / entry['size']))
                if received != entry['size'] or sha.hexdigest() != entry['sha256']:
                    raise ValueError("主题包大小或SHA256不符，未安装")
                self._set(message='正在校验主题配置与图片…')
                # Fully validate and decode in clean storage BEFORE touching user's installed themes.
                verifier = ThemeManager(Path(temporary)/'validation')
                normalized = verifier.import_pack(package)['config']
                # Destroy temporary decoder drafts when validation finishes.
                verifier._draft_cleanup()
                if (normalized['id'] != entry['id'] or normalized['version'] != entry['version']
                        or normalized['name'] != entry['name'] or normalized['schemaVersion'] != entry['themeSchemaVersion']):
                    raise ValueError("主题包身份/版本与清单不一致，未安装")
                with self.lock:
                    if self.closed.is_set(): raise ValueError("工坊已关闭，未安装主题")
                    with self.manager.lock:
                        payload = self.manager.import_pack(package)
                        installed_id = payload['config']['id']
                        records = self._receipts()
                        records.append({'sourceId':entry['id'], 'version':entry['version'], 'installedId':installed_id})
                        try:
                            _atomic(self.manager.root/'online-installations.json', json.dumps(records[-1000:]).encode('utf-8'))
                        except OSError:
                            # Theme is already safely installed; don't report a nonexistent failure.
                            pass
                    self._set(phase='installed', installedId=installed_id, progress=100,
                              message='主题已安装，未自动应用；可载入工坊预览。原有同ID主题保留为原样，新下载为副本。')
        return self._start('downloading', task)

    def close(self):
        with self.lock: self.closed.set()
