"""Read-only inspection of a freshly built PyInstaller EXE; never launches login/player."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
ROOT, OUTPUT = setup()
from PyInstaller.archive.readers import CArchiveReader

from core.version import EXE_NAME
exe=ROOT/'package-exe/dist'/EXE_NAME
archive=CArchiveReader(str(exe))
mapping={name.replace('\\','/'):name for name in archive.toc}
names=set(mapping)
required={'web/index.html','web/app.js','web/update-preview.js','web/update-preview.css',
          'web/workshop.html','web/capture.html','web/themes/ai-prompt.md','web/theme.schema.json',
          'web/themes/presets.json','docs/themes/README.md','docs/themes/FIELDS.md',
          'web/updater.js','core/update-helper.ps1','web/theme-library.js',
          'web/theme-library.css','docs/themes/ONLINE.md'}
assert required<=names, required-names
for theme in ('black-lotus-violet-resonance','strelizia-twilight-resonance'):
    assert 'web/themes/'+theme+'/theme.json' in names
    assert any(n.startswith('web/themes/'+theme+'/assets/') for n in names)
for name in names:
    assert Path(name).name not in ('config.json','song_blacklist.txt','.A歌曲黑名单.txt','cookies.json'),name
    assert not name.startswith('web/themes/preset-haruka/'),name
    assert name not in ('web/assets/haruka.png','web/assets/haruka.webp'),name
import json
manifest=json.loads(archive.extract(mapping['web/themes/presets.json']))
assert set(manifest['themes'])=={'black-lotus-violet-resonance','strelizia-twilight-resonance'}
template=json.loads(archive.extract(mapping['web/themes/rose-nocturne.json']))
assert template['text']['name']=='这里是名字' and template['text']['signature']=='这里是签名'
assert template['character']['image']==''
for filename in ('web/index.html','web/theme.schema.json','web/themes/rose-nocturne.json','web/haruka.css'):
    content=archive.extract(mapping[filename]).decode('utf-8')
    assert '渚花遥' not in content and "HARUKA'S MUSIC ROOM" not in content,filename
pyz=archive.open_embedded_archive('PYZ.pyz')
for module in ('core.player','core.netease_runtime','core.queue_runtime','core.theme_manager','core.theme_workshop','core.theme_catalog','core.capture_window','core.updater','core.update_protocol','core.version','cryptography','PIL.Image','jsonschema'):
    assert module in pyz.toc,module
print('PASS: packaged GUI/online theme library/docs/two preset assets/updater modules; no removed OC or personal configuration; EXE not launched')
