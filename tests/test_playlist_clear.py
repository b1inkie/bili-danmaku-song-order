"""清空队列离线验证，不连接或清空用户网易云。"""
import unittest
from unittest.mock import AsyncMock
from core.player import Player

class ClearTests(unittest.IsolatedAsyncioTestCase):
    async def test_clear_confirmed_by_empty_snapshot(self):
        player = Player()
        before = {'items':[{'id':'1'},{'id':'2'}], 'current':'1','playing':True}
        after = {'items':[], 'current':None, 'playing':False}
        player.playlist = AsyncMock(side_effect=[before, before, after])
        player._evaluate = AsyncMock()
        self.assertEqual(await player.clear_playlist(['1','2']), after)
        expression = player._evaluate.call_args.args[0]
        self.assertIn('removeIds:list.slice()', expression)
        self.assertIn('"expectedIds": ["1", "2"]', expression)
        self.assertEqual(player.playlist.await_count, 3)

    async def test_queue_changed_rejects_clear(self):
        player = Player()
        player.playlist = AsyncMock(return_value={'items':[{'id':'1'},{'id':'2'}]})
        player._evaluate = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, '歌单已变化'):
            await player.clear_playlist(['1'])
        player._evaluate.assert_not_awaited()

    async def test_invalid_input(self):
        for value in ([], None, ['invalid'], ['1;alert(1)'], [1], ['0']):
            with self.subTest(value=value), self.assertRaises(ValueError):
                await Player().clear_playlist(value)

class RuntimeClearTests(unittest.TestCase):
    def test_bulk_clear_uses_full_items_and_guards_changed_queue(self):
        import json
        import subprocess
        from core.playlist_runtime import ACTION
        expression = ACTION.replace('INPUT', json.dumps({'songId':'', 'command':'clear', 'direction':0, 'expectedIds':['1','2']}), 1)
        script = """const assert=require('assert');const items=[{resourceId:1},{resourceId:2}];let calls=[];
        global.window={__songdesk:{store:{getStore:()=>({playingList:{curPlayingList:items},playing:{}}),getDispatch:()=>async action=>calls.push(action)}}};
        (async()=>{await EXPR;assert.strictEqual(calls.length,1);assert.strictEqual(calls[0].payload.removeIds[0],items[0]);
        assert.strictEqual(calls[0].payload.removeIds[1],items[1]);items.push({resourceId:3});
        await assert.rejects(()=>EXPR,/歌单已变化/);assert.strictEqual(calls.length,1);})().catch(e=>{console.error(e);process.exit(1)});""".replace('EXPR', expression)
        subprocess.run(['node','-e',script],check=True,capture_output=True)

if __name__ == '__main__': unittest.main()
