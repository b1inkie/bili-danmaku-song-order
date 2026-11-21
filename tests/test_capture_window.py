"""捕捉小窗离线测试，不登录、不连接真实播放器。"""
import concurrent.futures
import types
import unittest
from unittest.mock import Mock, patch

from core.capture_window import CaptureWindow, PlaylistFeed, CaptureApi


SNAPSHOT = {"current": "1", "playing": True, "items": [
    {"id": "1", "name": "测试歌曲", "singer": "歌手", "requester": "观众"}]}


class Event:
    def __init__(self): self.callbacks = []
    def __iadd__(self, callback): self.callbacks.append(callback); return self
    def fire(self):
        for callback in self.callbacks: callback()


class Window:
    def __init__(self, **kwargs):
        self.width, self.height = kwargs["width"], kwargs["height"]
        self.events = types.SimpleNamespace(closed=Event(), shown=Event(), resized=Event())
        self.native = types.SimpleNamespace(InvokeRequired=False, Opacity=1.0, TopMost=False)
        self.resize = Mock()
        self.hide, self.show, self.restore, self.move = Mock(), Mock(), Mock(), Mock()
        self.destroy = Mock(side_effect=self.events.closed.fire)


class FeedTests(unittest.TestCase):
    def test_two_readers_share_one_fetch_and_cannot_mutate_cache(self):
        fetch = Mock(return_value=SNAPSHOT)
        feed = PlaylistFeed(fetch)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            results = list(pool.map(lambda _: feed.read(), range(5)))
        fetch.assert_called_once()
        results[0]["snapshot"]["items"].clear()
        self.assertEqual(len(feed.read()["snapshot"]["items"]), 1)

    def test_disconnect_marks_snapshot_stale(self):
        feed = PlaylistFeed(Mock(side_effect=[SNAPSHOT, RuntimeError("offline")]), ttl=0)
        self.assertTrue(feed.read()["connected"])
        view = feed.read()
        self.assertFalse(view["connected"])
        self.assertEqual(view["snapshot"], SNAPSHOT)
        self.assertIn("上次歌单", view["message"])

    def test_initial_failure_does_not_invent_playlist(self):
        view = PlaylistFeed(Mock(side_effect=RuntimeError("offline"))).read()
        self.assertIsNone(view["snapshot"])
        self.assertFalse(view["connected"])

    def test_action_publishes_latest_snapshot(self):
        fetch = Mock(return_value=SNAPSHOT)
        feed = PlaylistFeed(fetch)
        feed.publish({**SNAPSHOT, "playing": False})
        self.assertFalse(feed.read()["snapshot"]["playing"])
        fetch.assert_not_called()


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.factory = Mock(side_effect=lambda *args, **kwargs: Window(**kwargs))
        self.owner = types.SimpleNamespace(x=-1200, y=100)
        self.screens = [types.SimpleNamespace(x=0, y=0, width=1920, height=1080),
                        types.SimpleNamespace(x=-1600, y=0, width=1600, height=900)]
        self.feed = PlaylistFeed(Mock(return_value=SNAPSHOT))
        self.controller = CaptureWindow(self.feed, lambda: self.owner, self.factory, lambda: self.screens)

    def test_create_hide_show_reuses_window_and_title(self):
        self.assertTrue(self.controller.toggle()["visible"])
        window = self.controller._window
        self.assertEqual(self.factory.call_args.args[0], CaptureWindow.TITLE)
        self.assertTrue(self.factory.call_args.kwargs["frameless"])
        self.assertNotIn("transparent", self.factory.call_args.kwargs)
        self.assertFalse(self.controller.toggle()["visible"])
        window.hide.assert_called_once()
        self.assertTrue(self.controller.toggle()["visible"])
        window.show.assert_called_once()
        self.factory.assert_called_once()

    def test_reset_uses_owner_screen_preserves_size(self):
        self.controller.toggle()
        w = self.controller._window
        w.width, w.height = 500, 400
        self.controller.reset_position()
        x, y = w.move.call_args.args
        self.assertTrue(-1600 <= x <= -500)
        self.assertTrue(0 <= y <= 500)
        self.assertEqual((w.width, w.height), (500, 400))

    def test_reset_before_creation_does_not_summon(self):
        self.assertFalse(self.controller.reset_position()["visible"])
        self.factory.assert_not_called()

    def test_closed_window_can_be_created_again(self):
        self.controller.toggle()
        old = self.controller._window
        old.events.closed.fire()
        self.assertFalse(self.controller.state()["visible"])
        self.controller.toggle()
        new = self.controller._window
        self.assertIsNot(new, old)
        old.events.closed.fire()
        self.assertIs(self.controller._window, new)

    def test_shutdown_destroys_hidden_child_and_blocks_new_windows(self):
        self.controller.toggle()
        w = self.controller._window
        self.controller.toggle()
        self.controller.shutdown()
        w.destroy.assert_called_once()
        self.assertFalse(self.controller.toggle()["visible"])
        self.factory.assert_called_once()

    def test_capture_bridge_only_exposes_read_data(self):
        api = CaptureApi(self.controller, self.feed)
        self.assertEqual({name for name in dir(api) if not name.startswith("_")},
                         {"get_view", "set_opacity", "set_pinned", "set_compact", "hide_window", "get_geometry", "resize_window"})
        self.controller.set_theme("haruka")
        self.assertEqual(api.get_view()["theme"], "haruka")
        with self.assertRaises(ValueError): self.controller.set_theme("invalid")

    def test_opacity_and_pin_apply_native_and_survive_recreate(self):
        self.controller.toggle()
        window = self.controller._window
        self.controller.set_opacity(70)
        self.controller.set_pinned(True)
        self.controller.set_compact(True)
        self.assertEqual(window.native.Opacity, .7)
        self.assertTrue(window.native.TopMost)
        window.destroy()
        self.controller.toggle()
        self.assertEqual(self.controller.preferences(), {"opacity": 70, "pinned": True, "compact": True})
        with patch.object(self.controller, "_shape"):
            self.controller._shown(self.controller._window)
        self.assertEqual(self.controller._window.native.Opacity, .7)

    def test_invalid_window_preferences_rejected(self):
        for value in (0, 39, 101, float('nan'), float('inf')):
            with self.assertRaises(ValueError): self.controller.set_opacity(value)
        with self.assertRaises(ValueError): self.controller.set_pinned("true")
        with self.assertRaises(ValueError): self.controller.set_compact(1)
        with self.assertRaises(ValueError): self.controller.resize(100, 100, "se")
        with self.assertRaises(ValueError): self.controller.resize(420, 620, "invalid")

    def test_toolbar_hide_preserves_native_window(self):
        self.controller.toggle()
        window = self.controller._window
        self.assertFalse(CaptureApi(self.controller, self.feed).hide_window()["visible"])
        self.assertIs(self.controller._window, window)
        window.hide.assert_called_once()

    def test_main_api_shares_feed_and_publishes_actions(self):
        from main_gui import Api
        snapshot = {**SNAPSHOT, "playing": False}
        engine = types.SimpleNamespace(player=Mock())
        with patch.object(Api, "_player_call", return_value=SNAPSHOT) as call:
            api = Api(engine)
            self.assertEqual(api.get_playlist(), SNAPSHOT)
            self.assertEqual(api._capture._feed.read()["snapshot"], SNAPSHOT)
            self.assertEqual(call.call_count, 1)
            call.return_value = snapshot
            api.playlist_action("1", "toggle")
            self.assertEqual(api._capture._feed.read()["snapshot"], snapshot)


if __name__ == "__main__": unittest.main()
