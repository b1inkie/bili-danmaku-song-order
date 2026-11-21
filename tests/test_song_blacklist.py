"""歌曲拉黑离线回归，使用临时文件，不改用户黑名单或播放器。"""
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
from core.settings import Settings
from core.engine import Engine
from main_gui import Api


class BlacklistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings()
        self.settings.blacklist_path = str(Path(self.tmp.name) / 'blacklist.txt')

    def test_persist_deduplicate_and_remove(self):
        self.settings.set_blacklist(['原有歌曲'])
        self.assertTrue(self.settings.add_blacklisted_song(' 新歌曲 '))
        self.assertFalse(self.settings.add_blacklisted_song('新歌曲'))
        self.assertEqual(self.settings.get_blacklist(), {'原有歌曲', '新歌曲'})
        self.settings.set_blacklist(['原有歌曲'])
        self.assertNotIn('新歌曲', self.settings.get_blacklist())
        self.assertEqual(len(list(Path(self.tmp.name).iterdir())), 1)

    def test_invalid_name(self):
        for name in ('', ' ', 'a\nb', 'a\rb', 'a\x00b', None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.settings.add_blacklisted_song(name)
        self.assertFalse(Path(self.settings.blacklist_path).exists())

    def test_concurrent_add_preserves_entries(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(self.settings.add_blacklisted_song, ['歌曲'+str(i) for i in range(15)]))
        self.assertEqual(len(self.settings.get_blacklist()), 15)

    def test_api_resolves_name_from_playlist(self):
        api = Api.__new__(Api)
        api._engine = SimpleNamespace(settings=self.settings)
        api.get_playlist = Mock(return_value={'items': [{'id':'1', 'name':'真实歌名'}]})
        self.assertEqual(api.blacklist_song('1'), {'name':'真实歌名','added':True})
        self.assertFalse(api.blacklist_song('1')['added'])
        with self.assertRaises(ValueError): api.blacklist_song('2')
        with self.assertRaises(ValueError): api.blacklist_song('invalid')
        self.assertEqual(self.settings.get_blacklist(), {'真实歌名'})


class EngineBlacklistTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolved_name_blocked_before_enqueue(self):
        engine = Engine()
        engine.settings.get_blacklist = Mock(return_value={'完整歌名'})
        engine.player.search = AsyncMock(return_value={'name':'完整歌名', 'songmid':'1'})
        engine.player.play_search_result = AsyncMock()
        await engine._handle_request('关键词', '', '观众', False)
        engine.player.play_search_result.assert_not_awaited()
        events = engine.bus.drain()
        self.assertEqual([e['phase'] for e in events if e['type']=='song'], ['requested','failed'])
        self.assertEqual([e['name'] for e in events if e['type']=='song_blocked'], ['完整歌名'])

    async def test_manual_request_keeps_bypass(self):
        engine = Engine()
        engine.settings.get_blacklist = Mock(return_value={'完整歌名'})
        engine.player.search = AsyncMock(return_value={'name':'完整歌名', 'songmid':'1'})
        engine.player.play_search_result = AsyncMock()
        await engine._handle_request('完整歌名', '', '手动点歌', True)
        engine.player.play_search_result.assert_awaited_once()

    async def test_danmaku_full_name_blocked_without_search(self):
        engine = Engine()
        engine.settings.get_blacklist = Mock(return_value={'完整歌名'})
        engine.player.search = AsyncMock()
        engine.on_danmaku(SimpleNamespace(msg='点歌 完整歌名 - 歌手', admin=0, uname='观众'))
        engine.player.search.assert_not_called()
        self.assertEqual(engine.bus.drain()[0]['type'], 'song_blocked')


if __name__ == '__main__': unittest.main()
