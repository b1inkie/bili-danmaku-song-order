"""容量与消费队列离线回归；不写用户配置、不连接播放器。"""
import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock
from core.player import Player
from core.settings import Settings
from core.queue_runtime import INSTALL, REMOVE_ENDED, TICK

class PolicySettingsTests(unittest.TestCase):
    def test_defaults_persistence_and_validation(self):
        with tempfile.TemporaryDirectory() as root:
            settings=Settings();settings.config_path=str(Path(root)/'config.json')
            self.assertEqual(settings.get_queue_policy(),{'enabled':False,'maximum':10})
            settings._write_config({'roomid':'1','cookies':{'test':'keep'}})
            settings.set_queue_policy(True,5)
            self.assertEqual(settings.get_queue_policy(),{'enabled':True,'maximum':5})
            self.assertEqual(settings._read_config()['cookies'],{'test':'keep'})
            for args in [(True,0),(True,501),(1,10),(True,True),(True,1.5)]:
                with self.assertRaises(ValueError):settings.set_queue_policy(*args)

class CapacityTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_queue_rejects_even_existing_track_without_dispatch(self):
        player=Player();player.queue_policy=lambda:{'enabled':True,'maximum':1}
        player._evaluate=AsyncMock(side_effect=[{'songs':[{'id':1}]},{'queue':[1],'current':1}])
        with self.assertRaisesRegex(RuntimeError,'歌单已满'):
            await player.play_search_result({'source':'wy','songmid':'1'})
        self.assertEqual(player._evaluate.await_count,2)

    async def test_concurrent_add_only_one_slot(self):
        player=Player();player.queue_policy=lambda:{'enabled':True,'maximum':2}
        queue=[1];dispatched=[]
        async def evaluate(expression):
            await asyncio.sleep(.001)
            if '/api/v3/song/detail' in expression:return {'songs':[{'id':2}]}
            if "'playingList/addItemToCurPlayingList',payload:" in expression:
                self.assertIn('消费队列未就绪',expression)
                queue.append(2);dispatched.append(2);return True
            return {'queue':queue[:],'current':1}
        player._evaluate=evaluate
        result=await asyncio.gather(*(player.play_search_result({'source':'wy','songmid':'2'}) for _ in range(2)),return_exceptions=True)
        self.assertEqual(sum(isinstance(x,RuntimeError) for x in result),1)
        self.assertEqual(dispatched,[2]);self.assertEqual(queue,[1,2])

    async def test_skip_removes_previous_only_when_enabled(self):
        player=Player();player.queue_policy=lambda:{'enabled':True,'maximum':3}
        player._evaluate=AsyncMock(side_effect=[{'queue':[1,2],'current':1},True,{'queue':[1,2],'current':2}])
        player._remove_previous=AsyncMock()
        await player.skip_next()
        player._remove_previous.assert_awaited_once_with(1)

    async def test_consumer_waits_for_native_state_not_pause(self):
        player=Player()
        player._evaluate=AsyncMock(side_effect=[True,{'mode':'playOrder','events':[{'id':'1','seq':1,'playId':'1_a'}]},'waiting'])
        await player.queue_tick(True)
        self.assertEqual(player._evaluate.await_count,3) # no acknowledgement/removal while paused

class NativeHookTests(unittest.TestCase):
    def test_end_callback_guards_and_mode_preserves_queue(self):
        script=r'''
const assert=require('assert');let callback;const qitems=[{resourceId:1},{resourceId:2}];
const state={playing:{curPlaying:{resourceId:1},playId:'1_a',playingState:1,playingMode:'playAi'},playingList:{curPlayingList:qitems}};
const calls=[];global.window={__songdesk_require__:{c:{a:{exports:{AudioPlayer:{subscribePlayStatus:x=>callback=x.callback}}}}},__songdesk:{store:{getStore:()=>state,getDispatch:()=>async a=>{calls.push(a);if(a.type==='playing/onUpdate')Object.assign(state.playing,a.payload);}}}};
(async()=>{INSTALL;await TICK;
assert.strictEqual(state.playing.playingMode,'playOrder');assert.strictEqual(state.playingList.curPlayingList,qitems);
for(const code of [-1,-2,404])callback({playId:'1_a',info:{code}});
assert.strictEqual(window.__songdesk.consumer.events.length,0);
callback({playId:'1_a',info:{code:0}});assert.strictEqual(window.__songdesk.consumer.events.length,1);
assert.strictEqual(await REMOVE,'waiting'); // paused must not be removed even if an old event arrives
state.playing.playId='1_b';assert.strictEqual(await REMOVE,'stale');
window.__songdesk.consumer.lease=0;callback({playId:'1_a',info:{code:0}});
assert.strictEqual(window.__songdesk.consumer.events.length,1);
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('INSTALL',INSTALL).replace('TICK',TICK.replace('ENABLED','true')).replace('REMOVE',REMOVE_ENDED.replace('INPUT',json.dumps({'id':'1','playId':'1_a'}),1))
        subprocess.run(['node','-e',script],check=True,capture_output=True)

if __name__=='__main__':unittest.main()
