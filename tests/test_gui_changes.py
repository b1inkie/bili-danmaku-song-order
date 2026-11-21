"""离线回归，不登录、不播放、不改客户端队列。"""
import unittest
from unittest.mock import AsyncMock
from core.engine import Engine
from core.player import Player


class CommandTests(unittest.TestCase):
    def test_dash_format_and_spaces(self):
        from core.song_commands import DIANGE_RE
        cases = {
            "点歌 青花瓷 - 周杰伦": ("青花瓷", "周杰伦"),
            "点歌 青花瓷": ("青花瓷", None),
            "点歌 See You Again - Wiz Khalifa": ("See You Again", "Wiz Khalifa"),
            "  点歌  青花瓷  -  周杰伦  ": ("青花瓷", "周杰伦"),
            "点歌 All-Time Low - Jon Bellion": ("All-Time Low", "Jon Bellion"),
            "点歌 晚餐歌 - Bansanka": ("晚餐歌", "Bansanka"),
            "点歌 See You Again": ("See You Again", None),
            "点歌 青花瓷 周杰伦": ("青花瓷 周杰伦", None),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                match = DIANGE_RE.match(text)
                self.assertIsNotNone(match)
                self.assertEqual(match.groups(), expected)

    def test_invalid_or_multiline_command_rejected(self):
        from core.song_commands import DIANGE_RE
        for text in ("点歌", "点歌   ", "点歌青花瓷", "我想点歌 青花瓷", "点歌 青花瓷\n下一首"):
            with self.subTest(text=text):
                self.assertIsNone(DIANGE_RE.match(text))

class PlayerTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_incompatible(self):
        player = Player()
        player._evaluate = AsyncMock(return_value=None)
        self.assertFalse((await player.status())["ready"])

    async def test_status_ready(self):
        player = Player()
        player._evaluate = AsyncMock(return_value={"queue": [], "current": None})
        self.assertTrue((await player.status())["ready"])

    async def test_wrong_source_rejected(self):
        with self.assertRaises(ValueError):
            await Player().play_search_result({"songmid": "1", "source": "kg"})

    async def test_queue_payload_and_confirmation(self):
        import json
        from core.netease_runtime import RUNTIME
        player = Player()
        player._evaluate = AsyncMock(side_effect=[
            {"songs": [{"id": 123, "name": "song"}]},
            {"queue": [1, 2], "current": 1}, True,
            {"queue": [1, 2, 123], "current": 1}])
        self.assertEqual(await player.play_search_result({"songmid": "123", "source": "wy"}), 123)
        expression = player._evaluate.call_args_list[2].args[0]
        payload = json.loads(expression.split("payload:", 1)[1].split("});return", 1)[0])
        self.assertEqual(payload["trackFrom"]["fromInfo"]["sourceData"], {})
        self.assertFalse(payload["options"]["play"])
        self.assertFalse(payload["options"]["clear"])
        self.assertEqual(payload["options"]["offset"], 1)
        self.assertNotIn("require__(12)", RUNTIME)

    async def test_queue_waits_for_client_state(self):
        player = Player()
        player._evaluate = AsyncMock(side_effect=[
            {"songs": [{"id": 123}]}, {"queue": [], "current": None}, True,
            {"queue": [], "current": None}, {"queue": [123], "current": 123}])
        self.assertEqual(await player.play_search_result({"songmid": "123", "source": "wy"}), 123)
        self.assertEqual(player._evaluate.await_count, 5)

    async def test_skip_waits_for_current_change(self):
        player = Player()
        player._evaluate = AsyncMock(side_effect=[
            {"queue": [1, 2], "current": 1}, True,
            {"queue": [1, 2], "current": 1}, {"queue": [1, 2], "current": 2}])
        self.assertEqual((await player.skip_next())["current"], 2)
        self.assertIn("playingList/jump2Track", player._evaluate.call_args_list[1].args[0])

    async def test_skip_rejects_single_song(self):
        player = Player()
        player._evaluate = AsyncMock(return_value={"queue": [1], "current": 1})
        with self.assertRaisesRegex(RuntimeError, "不足两首"):
            await player.skip_next()

    async def test_playlist_move_and_delete_confirm(self):
        player = Player()
        before = {"current": "1", "playing": True, "items": [{"id": "1"}, {"id": "2"}]}
        moved = {**before, "items": [{"id": "2"}, {"id": "1"}]}
        player.playlist = AsyncMock(side_effect=[before, moved])
        player._evaluate = AsyncMock(return_value=True)
        self.assertEqual(await player.playlist_action("2", "move", -1), moved)
        self.assertIn('"direction": -1', player._evaluate.call_args.args[0])
        player.playlist = AsyncMock(side_effect=[moved, {**before, "items": [{"id": "1"}]}])
        result = await player.playlist_action("2", "delete")
        self.assertEqual([x["id"] for x in result["items"]], ["1"])

    async def test_playlist_toggle_waits_for_status(self):
        player = Player()
        before = {"current": "1", "playing": True, "items": [{"id": "1"}]}
        player.playlist = AsyncMock(side_effect=[before, before, {**before, "playing": False}])
        player._evaluate = AsyncMock(return_value=True)
        result = await player.playlist_action("1", "toggle")
        self.assertFalse(result["playing"])
        self.assertEqual(player.playlist.await_count, 3)

    async def test_playlist_invalid_action_or_id_rejected(self):
        player = Player()
        for song, command, direction in [("1;alert(1)", "toggle", 0), ("1", "eval", 0), ("1", "move", 3)]:
            with self.assertRaises(ValueError):
                await player.playlist_action(song, command, direction)

    async def test_playlist_boundary_does_not_dispatch(self):
        player = Player()
        player.playlist = AsyncMock(return_value={"items": [{"id": "1"}]})
        player._evaluate = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "边界"):
            await player.playlist_action("1", "move", -1)
        player._evaluate.assert_not_awaited()

    async def test_account_confirmation_does_not_block_loop(self):
        import asyncio
        engine = Engine()
        task = asyncio.create_task(engine._cb_confirm("测试", 1))
        await asyncio.sleep(0.01)
        self.assertFalse(task.done())
        engine.confirm_use_account(True)
        self.assertTrue(await task)

    async def test_request_failure_is_terminal(self):
        engine = Engine()
        engine.player.search = AsyncMock(side_effect=RuntimeError("offline"))
        await engine._handle_request("测试", "", "观众", False)
        events = [e for e in engine.bus.drain() if e["type"] == "song"]
        self.assertEqual([e["phase"] for e in events], ["requested", "failed"])
        self.assertEqual(events[0]["request_id"], events[1]["request_id"])

    async def test_request_success_same_id_even_if_name_changes(self):
        engine = Engine()
        engine.player.search = AsyncMock(return_value={"name": "新名字", "singer": "歌手", "songmid": "1"})
        engine.player.play_search_result = AsyncMock(return_value=1)
        await engine._handle_request("旧名字", "", "观众", False)
        events = [e for e in engine.bus.drain() if e["type"] == "song"]
        self.assertEqual([e["phase"] for e in events], ["requested", "queued"])
        self.assertEqual(events[0]["request_id"], events[1]["request_id"])
        self.assertEqual(events[1]["source"], "网易云")
        self.assertEqual(engine.player._requesters["1"], "观众")


if __name__ == '__main__':
    unittest.main()
