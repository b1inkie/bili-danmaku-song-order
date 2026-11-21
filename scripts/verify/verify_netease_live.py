"""本机验证：默认只读；--queue 追加一首；--skip 实际切歌。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import setup
PROJECT_ROOT, OUTPUT_DIR = setup()
import asyncio
import json
import sys
from core.player import Player
from core.netease_runtime import RUNTIME, STATE

async def main():
    player=Player()
    status=await player.status()
    print('STATUS',json.dumps(status,ensure_ascii=True),flush=True)
    if not status['ready']:raise SystemExit(1)
    before=await player._evaluate(RUNTIME+STATE)
    print('BEFORE',json.dumps({k:v for k,v in before.items() if k!='queue'}|{'count':len(before['queue'])},ensure_ascii=True),flush=True)
    song=await player.search('Lemon','米津玄師')
    print('SEARCH',json.dumps(song,ensure_ascii=True),flush=True)
    if '--queue' in sys.argv:
        await player.play_search_result(song)
        after=await player._evaluate(RUNTIME+STATE)
        assert int(song['songmid']) in after['queue']
        assert after['current']==before['current'],'追加队列不应抢播'
        print('QUEUE_PASS',json.dumps({'song':song['songmid'],'count':len(after['queue']),'currentUnchanged':True}),flush=True)
    if '--skip' in sys.argv:
        after=await player.skip_next()
        print('SKIP_PASS',json.dumps({k:v for k,v in after.items() if k!='queue'},ensure_ascii=True),flush=True)

asyncio.run(main())
