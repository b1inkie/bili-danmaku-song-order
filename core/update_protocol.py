"""Signed release metadata and strict portable archive validation. No user-data writes."""
import base64
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from core.version import UPDATE_PUBLIC_KEY, REPOSITORY, UPDATER_VERSION, APP_NAME, EXE_NAME

MAX_PACKAGE = 250 * 1024 * 1024
MAX_UNPACKED = 350 * 1024 * 1024
FILES = (EXE_NAME, 'LICENSE', 'THIRD_PARTY_NOTICES.md')


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('版本号必须为三段非负整数')
    return tuple(map(int, value.split('.')))


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def parse_manifest(raw, signature, public_key=UPDATE_PUBLIC_KEY):
    if len(raw) > 64 * 1024 or len(signature) > 1024:
        raise ValueError('更新清单过大')
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(
            base64.b64decode(signature.strip(), validate=True), raw)
    except Exception as exc:
        raise ValueError('更新清单签名无效，拒绝安装') from exc
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('更新清单字段重复')
            result[key] = value
        return result
    data = json.loads(raw, object_pairs_hook=pairs)
    if data.get('schemaVersion') != 1 or data.get('platform') != 'windows-x64':
        raise ValueError('更新格式或平台不兼容')
    if type(data.get('minimumUpdaterVersion')) is not int or data['minimumUpdaterVersion'] > UPDATER_VERSION:
        raise ValueError('此版本需手动下载完整安装包')
    version_tuple(data.get('version'))
    if not isinstance(data.get('notes'), str) or len(data['notes']) > 12000:
        raise ValueError('更新说明无效')
    if type(data.get('size')) is not int or not 1 <= data['size'] <= MAX_PACKAGE:
        raise ValueError('更新包大小无效')
    for key in ('sha256', 'exeSha256'):
        if not isinstance(data.get(key), str) or not re.fullmatch('[0-9a-f]{64}', data[key]):
            raise ValueError('更新校验值无效')
    url = urlparse(data.get('url', ''))
    if (url.scheme != 'https' or url.netloc != 'github.com' or url.query or url.fragment
            or not url.path.startswith('/' + REPOSITORY + '/releases/download/v' + data['version'] + '/')
            or not url.path.endswith('.zip')):
        raise ValueError('更新地址不是本仓库的HTTPS正式发布包')
    hashes = data.get('files', {})
    if set(hashes) != set(FILES) or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in hashes.values()):
        raise ValueError('发布文件校验清单不完整')
    if hashes[EXE_NAME] != data['exeSha256']:
        raise ValueError('主程序校验值冲突')
    return data


def safe_directory(path):
    """Reject symlink/junction/reparse parents, not just resolved traversal."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.exists():
            flags = getattr(part.lstat(), 'st_file_attributes', 0)
            if part.is_symlink() or flags & 0x400:
                raise ValueError('更新路径包含链接/重解析点')
    return path


def unpack_package(package, destination, manifest):
    package, destination = Path(package), safe_directory(destination)
    if package.stat().st_size != manifest['size'] or digest(package) != manifest['sha256']:
        raise ValueError('更新包大小或SHA256不符')
    expected = {APP_NAME + '/' + name for name in FILES}
    with zipfile.ZipFile(package) as archive:
        entries = archive.infolist()
        if len(entries) > 8 or sum(i.file_size for i in entries) > MAX_UNPACKED:
            raise ValueError('更新包解压体积或文件数量超限')
        names = set()
        for entry in entries:
            name = entry.orig_filename
            if name != entry.filename or name in names:
                raise ValueError('更新包路径异常或重复')
            names.add(name)
            if name == APP_NAME + '/' and entry.is_dir(): continue
            if name not in expected or entry.is_dir() or entry.flag_bits & 1 or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('更新包包含非白名单文件')
        if {i.filename for i in entries if not i.is_dir()} != expected:
            raise ValueError('更新包缺少主程序或许可证')
        destination.mkdir(parents=True, exist_ok=True)
        for name in FILES:
            target = safe_directory(destination / name)
            data = archive.read(APP_NAME + '/' + name)
            if hashlib.sha256(data).hexdigest() != manifest['files'][name]:
                raise ValueError('发布文件校验失败：' + name)
            target.write_bytes(data)
    if (destination / FILES[0]).read_bytes()[:2] != b'MZ':
        raise ValueError('下载内容不是Windows主程序')
    return destination
