"""Explicit packaged A -> B -> A and failed-start recovery in isolated portable dirs.
Uses only --release-smoke-test (no account/player/settings access). Never modifies user EXE.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
ROOT,OUTPUT=setup()
import base64
import json
import os
import shutil
import subprocess
import time
import uuid
from core.update_protocol import FILES,digest
from tools.make_release import package_release

WORK=OUTPUT/'update-real-install'
from core.version import APP_NAME, EXE_NAME, VERSION
A=OUTPUT/'update-fixture/dist'/EXE_NAME
B=ROOT/'package-exe/dist'/EXE_NAME
assert A.is_file() and B.is_file(),'build both versions first'
WORK.mkdir(parents=True,exist_ok=True)
# Persist driver for inspectability. Each driver process exits, letting the real helper proceed.
driver=WORK/'driver.py'
driver.write_text('''import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import core.updater as module
root=Path(sys.argv[2]);action=sys.argv[3];version=sys.argv[4]
module.VERSION=version
from core.version import EXE_NAME
sys.executable=str(root/EXE_NAME)
p=module.Updater(root,frozen=True)
if action=='recover':
 p.recover(test_mode=True)
elif action=='rollback':
 p.prepare_install(rollback=True,test_mode=True)
else:
 tx=Path(sys.argv[5]);p.transaction=tx;p.state['phase']='ready'
 p.prepare_install(test_mode=True)
''',encoding='utf-8')

def wait_result(folder,token):
    tx=folder/'.update'/token
    deadline=time.monotonic()+130
    result=None
    while time.monotonic()<deadline:
        try:
            result=json.loads((tx/'state.json').read_text('utf-8-sig'))
            if result['phase'] in ('complete','failed','restored','needs-attention'):
                return result
        except (OSError,ValueError):pass
        time.sleep(.2)
    raise AssertionError(('helper timeout',result))

def run_driver(folder,action,version,tx=None):
    args=[sys.executable,str(driver),str(ROOT),str(folder),action,version]
    if tx:args.append(str(tx))
    result=subprocess.run(args,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    token=json.loads((folder/'.update/pending.json').read_text())['token']
    return wait_result(folder,token),folder/'.update'/token

def assert_data(folder):
    assert (folder/'config.json').read_bytes()==b'{"test-only":"unchanged"}'
    assert (folder/'song_blacklist.txt').read_bytes()==b'test-blacklist'
    assert (folder/'user-theme-sentinel.txt').read_bytes()==b'unchanged'

def seed(folder):
    folder.mkdir(parents=True,exist_ok=True)
    for name in FILES:shutil.copyfile(A if name==FILES[0] else ROOT/name,folder/name)
    (folder/'config.json').write_bytes(b'{"test-only":"unchanged"}')
    (folder/'song_blacklist.txt').write_bytes(b'test-blacklist')
    (folder/'user-theme-sentinel.txt').write_bytes(b'unchanged')

def transaction(folder,package,manifest,sig):
    from core.update_protocol import unpack_package
    tx=folder/'.update'/uuid.uuid4().hex;tx.mkdir(parents=True)
    unpack_package(package,tx/'staged',manifest)
    (tx/'latest.json').write_bytes((json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    (tx/'latest.json.sig').write_bytes(sig)
    return tx

if __name__=='__main__':
    # Copy to a unique folder; retain verification artifacts but never collide with a running prior test.
    folder=WORK/('portable-'+uuid.uuid4().hex[:8]);seed(folder)
    output=WORK/'release-assets'
    package=package_release(B,output,'Isolated update verification, not a published release')
    manifest=json.loads((output/'latest.json').read_text('utf-8'));signature=(output/'latest.json.sig').read_bytes()
    tx=transaction(folder,package,manifest,signature)
    result,tx=run_driver(folder,'upgrade','0.0.9',tx)
    assert result['phase']=='complete',result
    assert digest(folder/FILES[0])==digest(B)
    assert digest(folder/'backup'/FILES[0])==digest(A)
    assert_data(folder)
    print(f'PASS: real EXE 0.0.9 -> {VERSION}; packaged GUI+bridge health; backup+user data preserved',flush=True)
    time.sleep(4) # smoke-only GUI finishes; do not interfere with an active executable
    result,_=run_driver(folder,'rollback',VERSION)
    assert result['phase']=='complete',result
    assert digest(folder/FILES[0])==digest(A)
    assert digest(folder/'backup'/FILES[0])==digest(B)
    assert_data(folder)
    assert len(list(folder.rglob('*.exe')))==2
    print(f'PASS: real EXE {VERSION} -> 0.0.9; exactly current+previous EXE; user data unchanged',flush=True)
    # Failure case uses a tiny, valid MZ target which cannot start: helper must restore old files.
    time.sleep(4)
    failing=WORK/('failed-'+uuid.uuid4().hex[:8]);seed(failing)
    tx=transaction(failing,package,manifest,signature)
    bad=tx/'staged'/FILES[0];bad.write_bytes(b'MZ-invalid-startup')
    # Sign the intentionally non-runnable fixture with the local release test key.
    from tools.make_release import signing_key
    import zipfile
    bad_package=WORK/'bad-fixture.zip'
    with zipfile.ZipFile(bad_package,'w',zipfile.ZIP_DEFLATED) as z:
        for name in FILES:z.write(tx/'staged'/name,APP_NAME+'/'+name)
    altered=dict(manifest,files={name:digest(tx/'staged'/name) for name in FILES},exeSha256=digest(bad),size=bad_package.stat().st_size,sha256=digest(bad_package))
    raw=(json.dumps(altered,ensure_ascii=False,indent=2)+'\n').encode()
    (tx/'latest.json').write_bytes(raw);(tx/'latest.json.sig').write_bytes(base64.b64encode(signing_key().sign(raw)))
    result,_=run_driver(failing,'upgrade','0.0.9',tx)
    assert result['phase'] in ('failed','restored'),result
    assert digest(failing/FILES[0])==digest(A);assert_data(failing)
    print('PASS: real helper failed process startup -> original EXE restored, user files preserved',flush=True)
    # Simulate interrupted replacement AFTER old EXE moved, before new file is started.
    recovery=WORK/('recovery-'+uuid.uuid4().hex[:8]);seed(recovery)
    token=uuid.uuid4().hex;tx=recovery/'.update'/token;old=tx/'previous-current';old.mkdir(parents=True)
    original={name:digest(recovery/name) for name in FILES}
    for name in FILES:shutil.move(recovery/name,old/name);shutil.copyfile(B if name==FILES[0] else ROOT/name,recovery/name)
    plan=dict(root=str(recovery),token=token,pid=0,version=VERSION,currentVersion='0.0.9',originalFiles=list(FILES),originalHashes=original,testMode=True)
    (tx/'plan.json').write_text(json.dumps(plan),encoding='utf-8')
    (tx/'state.json').write_text(json.dumps({'phase':'needs-attention','message':'test interrupted','token':token}),encoding='utf-8')
    (recovery/'.update/pending.json').write_text(json.dumps({'token':token}),encoding='utf-8')
    result,_=run_driver(recovery,'recover',VERSION)
    assert result['phase']=='restored',result
    assert digest(recovery/FILES[0])==digest(A);assert_data(recovery)
    print('PASS: interrupted replacement recovery -> original version; config/blacklist untouched',flush=True)
