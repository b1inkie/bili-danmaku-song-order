"""真实操作回归：移动再恢复原位；新增测试曲→播放/暂停/恢复→删除；恢复原曲目及暂停状态。
仅显式 --run 才改变客户端，默认只读。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()
import asyncio,json,sys
from core.player import Player

async def main():
 p=Player();before=await p.playlist()
 print('SNAPSHOT',json.dumps({'count':len(before['items']),'current':before['current'],'playing':before['playing'],'first':before['items'][:1]},ensure_ascii=True),flush=True)
 if '--run' not in sys.argv:return
 if len(before['items'])<2:raise RuntimeError('需要至少2首歌曲')
 last=before['items'][-1]['id'];ids=[x['id'] for x in before['items']]
 added=None
 try:
  up=await p.playlist_action(last,'move',-1)
  assert [x['id'] for x in up['items']][-2]==last
  restored=await p.playlist_action(last,'move',1)
  assert [x['id'] for x in restored['items']]==ids
  print('MOVE_UP_DOWN_PASS',flush=True)
  song=await p.search('打上花火','DAOKO')
  if song['songmid'] in ids:raise RuntimeError('测试歌曲已在列表，停止以免删除用户曲目')
  await p.play_search_result(song);added=song['songmid']
  playing=await p.playlist_action(added,'toggle')
  assert playing['current']==added and playing['playing']
  paused=await p.playlist_action(added,'toggle');assert not paused['playing']
  resumed=await p.playlist_action(added,'toggle');assert resumed['playing']
  print('PLAY_PAUSE_RESUME_PASS',flush=True)
  deleted=await p.playlist_action(added,'delete')
  assert added not in [x['id'] for x in deleted['items']];added=None
  print('DELETE_CURRENT_PASS',flush=True)
 finally:
  if added:
   await p.playlist_action(added,'delete')
  current=await p.playlist()
  if before['current'] in [x['id'] for x in current['items']]:
   if current['current']!=before['current']:
    current=await p.playlist_action(before['current'],'toggle')
   if current['playing']!=before['playing']:
    await p.playlist_action(before['current'],'toggle')
  after=await p.playlist()
  print('RESTORED',json.dumps({'sameOrder':[x['id'] for x in after['items']]==ids,'current':after['current'],'playing':after['playing']},ensure_ascii=True),flush=True)

asyncio.run(main())
