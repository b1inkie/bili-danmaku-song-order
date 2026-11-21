"""Explicit --run only: append temporary songs, test consume then restore original queue/current/status/mode."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()
import asyncio,json,sys
from core.player import Player
from core.netease_runtime import RUNTIME,STATE
async def main():
 p=Player();before=await p._evaluate(RUNTIME+STATE)
 print('BEFORE',{'count':len(before['queue']),'current':before['current'],'status':before['status'],'mode':before['mode']},flush=True)
 if '--run' not in sys.argv:return
 added=[]
 async def dispatch(action,payload):
  return await p._evaluate(RUNTIME+"(async()=>{await window.__songdesk.store.getDispatch()("+json.dumps({'type':action,'payload':payload})+");return true})()")
 try:
  for name,singer in [('Lemon','米津玄師'),('打上花火','DAOKO')]:
   song=await p.search(name,singer)
   if int(song['songmid']) in before['queue']:raise RuntimeError('测试曲已在用户歌单')
   await p.play_search_result(song);added.append(song['songmid'])
  await p.queue_tick(True)
  p.queue_policy=lambda:{'enabled':True,'maximum':500}
  count=len((await p._evaluate(RUNTIME+STATE))['queue'])
  p.queue_policy=lambda:{'enabled':True,'maximum':count}
  try:await p.play_search_result(song)
  except RuntimeError as error:assert '歌单已满' in str(error)
  else:raise AssertionError('full queue accepted song')
  assert len((await p._evaluate(RUNTIME+STATE))['queue'])==count
  print('CAPACITY_FULL_PRESERVES_PASS',flush=True)
  p.queue_policy=lambda:{'enabled':True,'maximum':500}
  await p.playlist_action(added[0],'toggle')
  state=await p._evaluate(RUNTIME+STATE)
  assert state['mode']=='playOrder'
  await p.playlist_action(added[0],'toggle');await p.queue_tick(True)
  assert int(added[0]) in (await p._evaluate(RUNTIME+STATE))['queue']
  print('PAUSE_PRESERVES_PASS',flush=True)
  await p.playlist_action(added[0],'toggle')
  await p.skip_next()
  state=await p._evaluate(RUNTIME+STATE)
  assert int(added[0]) not in state['queue'] and state['current']==int(added[1])
  print('NEXT_CONSUMES_PASS',flush=True)
  # Last temporary song naturally ends; EOF must clear it without replaying/wrapping.
  await asyncio.sleep(2)
  duration=await p._evaluate(RUNTIME+'window.__songdesk.store.getStore().playing.resourceDuration')
  print('TEST_DURATION',duration,flush=True)
  if not duration or duration<5:raise RuntimeError('无可靠时长')
  await dispatch('playing/setPlayingPosition',{'duration':duration-1})
  for _ in range(40):
   await p.queue_tick(True)
   state=await p._evaluate(RUNTIME+STATE)
   if int(added[1]) not in state['queue']:break
   await asyncio.sleep(.5)
  else:raise RuntimeError('自然结束移除未确认')
  print('NATURAL_END_CONSUMES_PASS',flush=True)
  assert state['status']!=2,'last EOF unexpectedly started an older track'
  # Re-add two temporary songs to check natural advance between non-last items.
  p.queue_policy=lambda:{'enabled':False,'maximum':500}
  for name,singer in [('Lemon','米津玄師'),('打上花火','DAOKO')]:
   track=await p.search(name,singer);await p.play_search_result(track)
  p.queue_policy=lambda:{'enabled':True,'maximum':500}
  await p.playlist_action(added[0],'toggle');await asyncio.sleep(2)
  duration=await p._evaluate(RUNTIME+'window.__songdesk.store.getStore().playing.resourceDuration')
  await dispatch('playing/setPlayingPosition',{'duration':duration-1})
  for _ in range(40):
   await p.queue_tick(True);state=await p._evaluate(RUNTIME+STATE)
   if int(added[0]) not in state['queue']:break
   await asyncio.sleep(.5)
  else:raise RuntimeError('中间曲目自然结束未移除')
  assert state['current']==int(added[1]) and state['status']==2
  print('NATURAL_ADVANCE_PASS',flush=True)
 finally:
  p.queue_policy=lambda:{'enabled':False,'maximum':10}
  await p.queue_tick(False)
  state=await p._evaluate(RUNTIME+STATE)
  for song in added:
   if int(song) in state['queue']:await p.playlist_action(song,'delete')
  state=await p._evaluate(RUNTIME+STATE)
  if before['current'] in state['queue']:
   if state['current']!=before['current']:await p.playlist_action(str(before['current']),'toggle')
   state=await p._evaluate(RUNTIME+STATE)
   if (state['status']==2)!=(before['status']==2):await p.playlist_action(str(before['current']),'toggle')
  await dispatch('playing/onUpdate',{'playingMode':before['mode']})
  after=await p._evaluate(RUNTIME+STATE)
  print('RESTORED',{'order':after['queue']==before['queue'],'current':after['current']==before['current'],'status':after['status']==before['status'],'mode':after['mode']==before['mode']},flush=True)
asyncio.run(main())
