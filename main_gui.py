# -*- coding: utf-8 -*-
"""
GUI 入口 - pywebview 外壳（WebView2 渲染本地 web/ 前端）
引擎跑在后台线程，前端通过 js_api 拉取事件轮询。

窗口形态：
- frameless + SetWindowRgn 圆角区域（GDI 圆角，不透明、可点击）
  注：pywebview 的 transparent=True 在 Win10+WebView2 下鼠标事件穿透，不可用
- 拖拽：标题栏元素带 .pywebview-drag-region 类（pywebview 内置 DRAG_REGION_SELECTOR）
- 缩放：前端边缘手柄 → win_resize(w,h,fix)，pywebview 按 FixPoint 锚定对边
- 最大化时区域恢复直角满屏
"""
import io
import os
import sys

# 保证从任意工作目录启动都能找到项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import webview

from core import bili_login
from core.app_dir import get_web_dir
from core.engine import Engine
from core.capture_window import CaptureWindow, PlaylistFeed

# ---------------- Win32 圆角窗口区域 ----------------

ROUND_RADIUS = 14  # 圆角半径（物理像素）


def _get_window_size(hwnd: int):
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.windll.user32
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.right - rect.left, rect.bottom - rect.top


def apply_round_region(window, maximized: bool = False, radius: int = ROUND_RADIUS) -> bool:
    """给窗口套圆角区域（WinForms 原生 Form.Region）；最大化时移除"""
    try:
        import ctypes
        from System.Drawing import Region

        form = window.native
        hwnd = int(form.Handle.ToInt64())
        w, h = _get_window_size(hwnd)

        def _apply():
            if maximized:
                form.Region = None
            else:
                from System import IntPtr, Int64
                from ctypes import wintypes
                gdi = ctypes.WinDLL("gdi32", use_last_error=True)
                gdi.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
                gdi.CreateRoundRectRgn.restype = wintypes.HRGN
                gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
                rgn = gdi.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius * 2, radius * 2)
                if not rgn:
                    raise ctypes.WinError(ctypes.get_last_error())
                old_region = form.Region
                try:
                    form.Region = Region.FromHrgn(IntPtr(Int64(ctypes.c_ssize_t(rgn).value)))
                finally:
                    gdi.DeleteObject(rgn)
                if old_region is not None:
                    old_region.Dispose()

        if form.InvokeRequired:
            from System import Action
            form.Invoke(Action(_apply))
        else:
            _apply()
        return True
    except Exception as e:
        print(f"[窗口] 应用圆角区域失败: {e}")
        return False


def window_hwnd(window) -> int:
    return int(window.native.Handle.ToInt64())


def window_maximized(window) -> bool:
    try:
        return str(window.native.WindowState).endswith("Maximized")
    except Exception:
        return False


def qr_svg_data_url(qr_url: str) -> str:
    """登录二维码 URL → SVG data URL（纯Python生成，离线可用）"""
    import qrcode
    import qrcode.image.svg
    from urllib.parse import quote

    img = qrcode.make(qr_url, image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode("utf-8")
    return "data:image/svg+xml;utf8," + quote(svg)


# 缩放手柄 → pywebview FixPoint 锚点（锚定被拖动边的对侧）
FIX_MAP = {
    "n": "SOUTH|WEST", "s": "NORTH|WEST", "e": "NORTH|WEST", "w": "NORTH|EAST",
    "ne": "SOUTH|WEST", "nw": "SOUTH|EAST",
    "se": "NORTH|WEST", "sw": "NORTH|EAST",
}


class Api:
    """暴露给前端 JS 的接口（pywebview 自动序列化为 JSON）"""

    MIN_W, MIN_H = 920, 600

    def __init__(self, engine: Engine):
        self._engine = engine
        self._window = None  # create_window 之后注入
        self._playlist_feed = PlaylistFeed(lambda: self._player_call(self._engine.player.playlist()))
        self._capture = CaptureWindow(self._playlist_feed, lambda: self._window)
        from core.theme_manager import ThemeManager
        from core.theme_workshop import ThemeWorkshop
        self._themes = ThemeManager()
        self._workshop = ThemeWorkshop(self._themes)
        self._capture.theme_manager = self._themes
        from core.updater import Updater
        self._updater = Updater()

    def update_state(self):
        return self._updater.snapshot()

    def check_update(self):
        return self._updater.check()

    def download_update(self):
        return self._updater.download()

    def cancel_update(self):
        return self._updater.cancel()

    def install_update(self, rollback=False):
        if type(rollback) is not bool:
            raise ValueError("无效更新操作")
        editor = self._workshop.window
        if editor is not None and editor.evaluate_js("typeof dirty!=='undefined' && dirty"):
            raise ValueError("主题工坊有未保存修改，请先保存或关闭工坊再更新")
        result = self._updater.prepare_install(rollback=rollback)
        self._window.destroy()
        return result

    def recover_update(self):
        editor = self._workshop.window
        if editor is not None and editor.evaluate_js("typeof dirty!=='undefined' && dirty"):
            raise ValueError("请先保存工坊修改")
        result = self._updater.recover()
        self._window.destroy()
        return result

    def frontend_ready(self):
        self._updater.start()
        if '--update-health' in sys.argv:
            from core.updater import acknowledge_startup
            index = sys.argv.index('--update-health')
            acknowledge_startup(sys.argv[index+1])
        return True

    def attach_window(self, window):
        self._window = window

    # ---------- 状态与事件 ----------

    def get_state(self) -> dict:
        eng = self._engine
        return {
            "roomid": eng.settings.get_roomid(),
            "account": eng.account,           # None 或 {uname, uid}
            "listening": eng.listening,
            "hasCookie": eng.settings.has_cookie(),
        }

    def poll_events(self) -> list:
        events = self._engine.bus.drain()
        # 二维码事件在这里转换成 dataURL，前端直接 <img src>
        for e in events:
            if e.get("type") == "qr" and e.get("action") == "show" and e.get("url"):
                try:
                    e["svg"] = qr_svg_data_url(e["url"])
                except Exception as ex:
                    e["error"] = f"二维码生成失败: {ex}"
        return events

    # ---------- 账号 ----------

    def confirm_use_account(self, ok: bool):
        self._engine.confirm_use_account(bool(ok))

    def switch_account(self):
        self._engine.switch_account()

    # ---------- 监听 ----------

    def start_listen(self, roomid: str):
        self._engine.set_roomid_and_listen(roomid)

    def stop_listen(self):
        self._engine.stop_listen()

    # ---------- 点歌 ----------

    def request_song(self, name: str, singer: str = ""):
        self._engine.request_song(name, singer)

    def skip_next(self):
        self._engine.skip_next()

    def _player_call(self, coro):
        import asyncio
        loop = self._engine._loop
        if loop is not None and loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=40)
        return asyncio.run(coro)

    def player_status(self):
        return self._player_call(self._engine.player.status())

    def launch_player(self):
        return self._player_call(self._engine.player.launch())

    def get_playlist(self):
        view = self._playlist_feed.read()
        if not view["connected"]:
            raise RuntimeError(view["message"])
        return view["snapshot"]

    def playlist_action(self, song_id, command, direction=0):
        snapshot = self._player_call(self._engine.player.playlist_action(song_id, command, direction))
        self._playlist_feed.publish(snapshot)
        return snapshot

    def clear_playlist(self, expected_ids):
        snapshot = self._player_call(self._engine.player.clear_playlist(expected_ids))
        self._playlist_feed.publish(snapshot)
        return snapshot

    def blacklist_song(self, song_id):
        song_id = str(song_id)
        if not song_id.isdecimal() or int(song_id) <= 0:
            raise ValueError("无效的歌曲ID")
        snapshot = self.get_playlist()
        item = next((item for item in snapshot["items"] if str(item["id"]) == song_id), None)
        if item is None:
            raise ValueError("歌曲已不在歌单，请刷新后重试")
        name = item["name"].strip()
        added = self._engine.settings.add_blacklisted_song(name)
        return {"name": name, "added": added}

    # ---------- 直播捕捉窗 ----------

    def capture_state(self):
        return self._capture.state()

    def toggle_capture(self):
        return self._capture.toggle()

    def reset_capture_position(self):
        return self._capture.reset_position()

    def set_capture_theme(self, theme):
        return self._capture.set_theme(theme)

    def theme_catalog(self):
        return self._themes.catalog()

    def theme_state(self, revision=None):
        return self._themes.state(revision)

    def select_theme(self, theme_id):
        result = self._themes.select(theme_id)
        if theme_id in ("dark", "light", "haruka"):
            self._capture.set_theme(theme_id)
        return result

    def delete_theme(self, theme_id):
        result = self._themes.delete(theme_id)
        if result["id"] in ("dark", "light", "haruka"):
            self._capture.set_theme(result["id"])
        return result
    def open_theme_workshop(self):
        return self._workshop.open()

    # ---------- 窗口控制（无边框标题栏用） ----------

    def win_minimize(self):
        if self._window is not None:
            self._window.minimize()

    def win_maximize(self):
        if self._window is not None:
            try:
                self._window.maximize()
            except Exception:
                pass

    def win_restore(self):
        if self._window is not None:
            try:
                self._window.restore()
            except Exception:
                pass

    def win_close(self):
        if self._window is not None:
            self._window.destroy()

    def win_get_geom(self) -> dict:
        """窗口物理尺寸（缩放手柄起点）"""
        if self._window is None:
            return {"w": 0, "h": 0}
        w, h = _get_window_size(window_hwnd(self._window))
        return {"w": w, "h": h}

    def win_resize(self, w, h, fix: str = "se"):
        """按锚点缩放窗口（fix=被拖动的边，锚定对侧）"""
        if self._window is None:
            return
        from webview.window import FixPoint

        parts = FIX_MAP.get(fix, "SOUTH|EAST").split("|")
        fix_point = getattr(FixPoint, parts[0])
        for part in parts[1:]:
            fix_point |= getattr(FixPoint, part)
        w = max(int(w), self.MIN_W)
        h = max(int(h), self.MIN_H)
        try:
            self._window.resize(w, h, fix_point)
        except Exception:
            pass

    # ---------- 设置 ----------

    def get_queue_policy(self):
        return self._engine.settings.get_queue_policy()

    def save_queue_policy(self, enabled, maximum):
        return self._player_call(self._engine.configure_queue(enabled, maximum))
    def get_blacklist(self) -> str:
        return self._engine.settings.get_blacklist_text()

    def save_blacklist(self, text: str):
        lines = [ln for ln in (text or "").replace("\r\n", "\n").split("\n")]
        self._engine.settings.set_blacklist(lines)
        return True

    def open_author_bilibili(self):
        """Only the fixed author profile; do not accept arbitrary URLs from frontend."""
        import webbrowser
        if not webbrowser.open("https://space.bilibili.com/1160389658"):
            raise RuntimeError("无法打开系统浏览器，请复制主页地址访问")
        return True

    def open_room_page(self):
        """在浏览器打开直播间页面（方便主播核对房间号）"""
        roomid = self._engine.settings.get_roomid()
        if roomid:
            import webbrowser
            webbrowser.open(f"https://live.bilibili.com/{roomid}")
            return True
        return False


def main():
    from core.app_instance import acquire
    if not acquire():
        return
    # Explicit build verification mode: tests a real packaged WebView bridge without
    # constructing Engine/ThemeManager or loading account cookies/player connections.
    if '--release-smoke-test' in sys.argv:
        from core.release_smoke import run
        run()
        return
    engine = Engine()
    api = Api(engine)
    engine.start()

    index_path = os.path.join(get_web_dir(), "index.html")
    window = webview.create_window(
        "B站点歌台",
        url=index_path,
        js_api=api,
        width=1180,
        height=780,
        min_size=(Api.MIN_W, Api.MIN_H),
        frameless=True,          # 无边框：圆角由 GDI 区域裁剪
        background_color="#0a0a0b",
        shadow=False,
        easy_drag=False,         # 只允许 .pywebview-drag-region 标题栏拖拽
    )
    api.attach_window(window)
    def shutdown():
        api._updater.stop()
        api._capture.shutdown()
        api._workshop.shutdown()
        engine.shutdown()

    window.events.closing += shutdown

    def sync_window_shape():
        """圆角区域 + 最大化状态同步（UI线程安全调用）"""
        try:
            hwnd = window_hwnd(window)
            maximized = window_maximized(window)
            apply_round_region(window, maximized=maximized)
            window.evaluate_js(
                f"document.documentElement.dataset.maximized='{str(maximized).lower()}'"
            )
        except Exception as e:
            print(f"[窗口] 同步窗口形状失败: {e}")

    window.events.shown += lambda: sync_window_shape()
    window.events.resized += lambda width, height: sync_window_shape()

    webview.start()


if __name__ == "__main__":
    main()
