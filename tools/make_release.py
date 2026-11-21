"""Create portable release assets + Ed25519-signed manifest; never upload automatically.
Signing key is DPAPI-protected outside repo at LOCALAPPDATA/BiliSongdesk-publisher.
"""
import argparse
import base64
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile
if __package__:
    from ._bootstrap import setup
else:
    from _bootstrap import setup
ROOT=setup()
from core.version import VERSION, REPOSITORY, UPDATE_PUBLIC_KEY, UPDATER_VERSION, APP_NAME, EXE_NAME
from core.update_protocol import FILES, digest, parse_manifest


def signing_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    path=Path(os.environ['LOCALAPPDATA'])/'BiliSongdesk-publisher/update-signing-key.dpapi'
    raw=path.read_bytes()
    class Blob(ctypes.Structure):
        _fields_=[('size',ctypes.c_uint32),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(raw)
    source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));output=Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output)):
        raise ctypes.WinError()
    try:key=Ed25519PrivateKey.from_private_bytes(ctypes.string_at(output.data,output.size))
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes=[ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(output.data)
    if base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()!=UPDATE_PUBLIC_KEY:
        raise ValueError('签名私钥与客户端公钥不符')
    return key


def package_release(exe, output, notes):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    package=output/f'{APP_NAME}-v{VERSION}-win-x64.zip'
    sources={FILES[0]:Path(exe),FILES[1]:ROOT/'LICENSE',FILES[2]:ROOT/'THIRD_PARTY_NOTICES.md'}
    if sources[FILES[0]].read_bytes()[:2]!=b'MZ':raise ValueError('invalid EXE')
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,path in sources.items():archive.write(path,APP_NAME+'/'+name)
    hashes={name:digest(path) for name,path in sources.items()}
    data=dict(schemaVersion=1,platform='windows-x64',channel='stable',version=VERSION,
              minimumUpdaterVersion=UPDATER_VERSION,url=f'https://github.com/{REPOSITORY}/releases/download/v{VERSION}/{package.name}',
              size=package.stat().st_size,sha256=digest(package),exeSha256=hashes[FILES[0]],files=hashes,
              notes=notes,publishedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
    raw=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    signature=base64.b64encode(signing_key().sign(raw))
    parse_manifest(raw,signature)
    (output/'latest.json').write_bytes(raw);(output/'latest.json.sig').write_bytes(signature+b'\n')
    (output/'SHA256SUMS.txt').write_text(data['sha256']+'  '+package.name+'\n'+hashes[EXE_NAME]+'  '+EXE_NAME+'\n',encoding='ascii')
    print('Release assets:',output.resolve())
    return package


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',default=str(ROOT/'package-exe/dist'/EXE_NAME))
    parser.add_argument('--output',default=str(ROOT/'package-exe/release'/('v'+VERSION)))
    parser.add_argument('--notes',required=True,help='UTF-8 release notes file')
    args=parser.parse_args()
    package_release(args.exe,args.output,Path(args.notes).read_text('utf-8'))
