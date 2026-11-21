"""Build signed same-repository theme assets, never upload automatically.
python tools/make_theme_catalog.py --theme path/to/folder --output artifacts/theme-library
Repeat --theme to generate the COMPLETE catalog, not a delta. Upload packs first, catalog last.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
if __package__:
    from ._bootstrap import setup
else:
    from _bootstrap import setup
ROOT = setup()
from core.theme_catalog import parse_catalog
from core.theme_manager import ThemeManager
from core.version import REPOSITORY, VERSION
from core.update_protocol import version_tuple
from tools.make_release import signing_key
from tools.theme_tool import source_pack


def build_catalog(sources, output, minimum=VERSION, key=None):
    version_tuple(minimum)
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    # Validate everything before writing output; stage all artifacts separately.
    with tempfile.TemporaryDirectory(prefix='songdesk-catalog-build-') as temporary:
        stage = Path(temporary)
        entries, ids = [], set()
        for index, source in enumerate(sources):
            manager = ThemeManager(stage/str(index)/'themes')
            archive = source_pack(Path(source), stage/(str(index)+'.zip'))
            c = manager.import_pack(archive)['config']
            if c['id'] in ids: raise ValueError('主题ID重复：'+c['id'])
            ids.add(c['id']); version_tuple(c['version'])
            filename = c['id']+'-'+c['version']+'.songtheme'
            pack = stage/filename
            # Fixed ZIP timestamps/order make an unchanged version byte-identical.
            with zipfile.ZipFile(pack, 'w', zipfile.ZIP_DEFLATED) as target:
                contents = {'theme.json': (json.dumps(c, ensure_ascii=False, indent=2)+'\n').encode('utf-8')}
                contents.update({ref: manager._asset(ref, c['id']).read_bytes() for ref in set(manager.image_refs(c))})
                for name, value in sorted(contents.items()):
                    info=zipfile.ZipInfo(name, date_time=(2020,1,1,0,0,0))
                    info.compress_type=zipfile.ZIP_DEFLATED
                    target.writestr(info,value)
            entries.append(dict(id=c['id'], name=c['name'], author=c['author'], description=c['description'],
                                version=c['version'], themeSchemaVersion=1, minimumAppVersion=minimum,
                                url=f'https://github.com/{REPOSITORY}/releases/download/theme-assets/{filename}',
                                size=pack.stat().st_size, sha256=hashlib.sha256(pack.read_bytes()).hexdigest()))
        raw = (json.dumps({'schemaVersion':1, 'themes':entries}, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
        key = key or signing_key()
        signature = base64.b64encode(key.sign(raw))
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
        parse_catalog(raw, signature, public)
        # Versioned asset names must be immutable. Explicitly bump theme.version on changes.
        for entry in entries:
            name = entry['url'].rsplit('/',1)[1]
            target = output/name
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=entry['sha256']:
                raise ValueError('同版本主题包已存在且内容不同，请提升theme.version：'+name)
        for entry in entries:
            name = entry['url'].rsplit('/',1)[1]
            (output/name).write_bytes((stage/name).read_bytes())
        (output/'catalog.json.sig').write_bytes(signature+b'\n')
        (output/'catalog.json').write_bytes(raw)
    return entries


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='校验并生成签名主题库（不自动上传）')
    parser.add_argument('--theme',action='append',required=True,help='独立主题文件夹或.songtheme；可重复')
    parser.add_argument('--output',required=True)
    parser.add_argument('--minimum-app-version',default=VERSION)
    args=parser.parse_args()
    try:
        entries=build_catalog(args.theme,args.output,args.minimum_app_version)
        print(f'PASS: {len(entries)}套主题及签名清单已生成：{Path(args.output).resolve()}')
    except Exception as exc:parser.exit(1,'FAIL: '+str(exc)+'\n')
