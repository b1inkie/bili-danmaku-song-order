"""Explicit anonymous online theme download/import/export validation, isolated storage only.
No GitHub credentials, user theme paths, app update, login or player calls.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
ROOT,OUTPUT=setup()
import json
import tempfile
from core.theme_catalog import ThemeCatalog
from core.theme_manager import ThemeManager


def finish(catalog):
    catalog.worker.join(300)
    if catalog.worker.is_alive():
        catalog.close();catalog.worker.join(60)
        raise RuntimeError('online theme verification timed out')
    state=catalog.snapshot()
    if state['phase']=='error':raise RuntimeError(state['message'])
    return state


def main():
    if '--run' not in sys.argv:
        print('Use --run for anonymous GitHub downloads into temporary theme storage only.')
        return
    with tempfile.TemporaryDirectory(prefix='songdesk-public-themes-') as root:
        manager=ThemeManager(Path(root)/'recipient');catalog=ThemeCatalog(manager)
        try:
            catalog.refresh();state=finish(catalog)
            assert state['available'] and state['themes'],'catalog not published'
            print('PASS: anonymous signed catalog refresh;',len(state['themes']),'themes',flush=True)
            for item in state['themes']:
                assert item['compatible'],item['reason']
                catalog.install(item['id'],item['version']);installed=finish(catalog)
                assert installed['phase']=='installed',installed
                config=manager.load(installed['installedId'])
                assert config['id']==item['id'] and config['version']==item['version']
                assert manager.payload(config)['assets'],'published fixture expected images'
                target=Path(root)/(item['id']+'.songtheme');manager.export_pack(config['id'],target)
                other=ThemeManager(Path(root)/('second-'+item['id']))
                payload=other.import_pack(target)
                assert payload['assets'] and payload['config']['capture']==config['capture']
                print('PASS: public download hash/import/export/fresh recipient:',item['id'],flush=True)
            assert manager.active=='dark'
            print('PASS: published themes independently usable; no auto-apply; no personal directory changes',flush=True)
        finally:catalog.close()


if __name__=='__main__':main()
