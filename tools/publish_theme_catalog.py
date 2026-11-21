"""Publish ONLY theme-assets pre-release to the application repository.
Requires explicit --publish; credentials use git credential helper, never printed/stored.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request
if __package__:
    from ._bootstrap import setup
else:
    from _bootstrap import setup
ROOT=setup()
from core.theme_catalog import parse_catalog
from core.version import REPOSITORY


class GitHub:
    def __init__(self):
        result=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,timeout=20)
        fields=dict(x.split('=',1) for x in result.stdout.splitlines() if '=' in x)
        if result.returncode or not fields.get('password'):raise ValueError('请先登录GitHub Git凭据，不要把Token写入项目')
        self._headers={'Authorization':'Bearer '+fields['password'],'Accept':'application/vnd.github+json',
                       'User-Agent':'BiliSongdesk-theme-publisher','X-GitHub-Api-Version':'2022-11-28'}
    def request(self,path,method='GET',data=None):
        url=path if path.startswith('https://') else 'https://api.github.com'+path
        parsed=urllib.parse.urlparse(url)
        if parsed.netloc not in ('api.github.com','uploads.github.com') or parsed.scheme!='https':
            raise ValueError('拒绝非GitHub API地址')
        body=json.dumps(data).encode() if isinstance(data,dict) else data
        content='application/octet-stream' if isinstance(data,bytes) else 'application/json'
        request=urllib.request.Request(url,data=body,method=method,headers={**self._headers,'Content-Type':content})
        try:
            with urllib.request.urlopen(request,timeout=180) as response:
                return None if response.status==204 else json.load(response)
        except Exception as exc:
            raise RuntimeError('GitHub主题发布请求失败（'+method+'），检查权限和网络后重试；旧主题包不会覆盖') from exc


def pages(api,path):
    result=[]
    for page in range(1,101):
        items=api.request(path+('?' if '?' not in path else '&')+'per_page=100&page='+str(page))
        result.extend(items)
        if len(items)<100:return result
    raise ValueError('GitHub分页数量异常，拒绝继续发布')

def publish(directory, api=None):
    directory=Path(directory)
    catalog=parse_catalog((directory/'catalog.json').read_bytes(),(directory/'catalog.json.sig').read_bytes())
    files={name:directory/name for name in ('catalog.json','catalog.json.sig')}
    for entry in catalog['themes']:
        name=entry['url'].rsplit('/',1)[1];path=directory/name
        if path.stat().st_size!=entry['size'] or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('主题包与签名清单不符：'+name)
        files[name]=path
    api=api or GitHub();base='/repos/'+REPOSITORY
    releases=pages(api,base+'/releases')
    release=next((r for r in releases if r['tag_name']=='theme-assets'),None)
    if release and not release['prerelease']:
        raise ValueError('theme-assets不是Pre-release，拒绝发布以免干扰程序更新')
    existing={a['name']:a for a in pages(api,base+'/releases/'+str(release['id'])+'/assets')} if release else {}
    # Preflight ALL immutable packages before changing the live catalog.
    for name,path in files.items():
        if name in existing and name.endswith('.songtheme'):
            expected='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
            if existing[name].get('digest')!=expected:
                raise ValueError('远程已有同名但内容不同的主题包，请提升版本：'+name)
    if not release:
        release=api.request(base+'/releases','POST',dict(tag_name='theme-assets',name='在线主题库 · Theme assets',
                            body='仅供在线主题库下载。不是程序更新，请勿设为Latest。',draft=True,prerelease=True,make_latest='false'))
    # Upload immutable packages first. Readers seeing mixed signatures during catalog
    # replacement reject refresh and keep their already verified in-memory catalog.
    order=sorted(n for n in files if n.endswith('.songtheme'))+['catalog.json.sig','catalog.json']
    for name in order:
        path=files[name];sha='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
        old=existing.get(name)
        if old and old.get('digest')==sha:continue
        if old:api.request(base+'/releases/assets/'+str(old['id']),'DELETE')
        upload=release['upload_url'].split('{',1)[0]+'?'+urllib.parse.urlencode({'name':name})
        asset=api.request(upload,'POST',path.read_bytes())
        if asset.get('digest')!=sha or asset['size']!=path.stat().st_size:
            raise ValueError('GitHub上传校验失败：'+name)
        print('已校验上传：'+name)
    published=api.request(base+'/releases/'+str(release['id']),'PATCH',dict(draft=False,prerelease=True,make_latest='false'))
    return published.get('html_url', f'https://github.com/{REPOSITORY}/releases/tag/theme-assets')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='同仓库在线主题发布，不触碰程序Release')
    parser.add_argument('directory');parser.add_argument('--publish',action='store_true',required=True,help='明确授权上传主题库')
    args=parser.parse_args()
    try:print('主题库已发布：'+publish(args.directory))
    except Exception as exc:parser.exit(1,'FAIL: '+str(exc)+'\n')
