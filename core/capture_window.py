"""直播捕捉歌单窗：只读数据桥、共享短缓存及独立窗口生命周期。"""
import copy
import os
import threading
import time

import webview

from core.app_dir import get_web_dir


class PlaylistFeed:
    """两个窗口共用一次播放器查询；断线保留上次快照，但明确标为离线。"""

    def __init__(self, fetch, ttl=1.0):
        self._fetch = fetch
        self._ttl = ttl
        self._lock = threading.Lock()
        self._expires = 0
        self._snapshot = None
        self._connected = False
        self._message = "等待连接网易云"

    def read(self):
        with self._lock:
            if time.monotonic() >= self._expires:
                try:
                    snapshot = self._fetch()
                    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("items"), list):
                        raise RuntimeError("网易云歌单数据无效")
                    self._snapshot = copy.deepcopy(snapshot)
                    self._connected = True
                    self._message = "网易云实时歌单"
                except Exception:
                    self._connected = False
                    self._message = "网易云未连接 · 显示上次歌单" if self._snapshot else "等待连接网易云"
                self._expires = time.monotonic() + self._ttl
            return copy.deepcopy({"connected": self._connected, "snapshot": self._snapshot,
                                  "message": self._message})

    def publish(self, snapshot):
        with self._lock:
            self._snapshot = copy.deepcopy(snapshot)
            self._connected = True
            self._message = "网易云实时歌单"
            self._expires = time.monotonic() + self._ttl


class CaptureApi:
    """不暴露主窗口账号、事件总线或播放器写操作。"""

    def __init__(self, controller, feed):
        self._controller = controller
        self._feed = feed

    def get_view(self):
        return {**self._feed.read(), "theme": self._controller.theme,
                "window": self._controller.preferences(),
                "customTheme": self._controller.theme_manager.state(capture=True) if self._controller.theme_manager else None}

    def set_opacity(self, percent):
        return self._controller.set_opacity(percent)

    def set_pinned(self, enabled):
        return self._controller.set_pinned(enabled)

    def set_compact(self, enabled):
        return self._controller.set_compact(enabled)

    def hide_window(self):
        return self._controller.hide()

    def get_geometry(self):
        w = self._controller._window
        return {"w": w.width, "h": w.height} if w else {"w": 420, "h": 620}

    def resize_window(self, width, height, edge):
        return self._controller.resize(width, height, edge)


class CaptureWindow:
    TITLE = "B站点歌台 · 直播歌单"
    WIDTH, HEIGHT = 420, 620
    MIN_SIZE = (300, 280)

    def __init__(self, feed, owner, factory=None, screens=None):
        self._feed = feed
        self._owner = owner
        self._factory = factory or webview.create_window
        self._screens = screens or (lambda: webview.screens)
        self._window = None
        self._visible = False
        self._stopping = False
        self._lock = threading.Lock()
        self.theme = "dark"
        self.theme_manager = None
        self._opacity = 100
        self._pinned = False
        self._compact = False

    def preferences(self):
        return {"opacity": self._opacity, "pinned": self._pinned, "compact": self._compact}

    @staticmethod
    def _native(window, action):
        """原生属性只能在 WinForms UI 线程设置。"""
        form = window.native
        if form.InvokeRequired:
            from System import Action
            form.Invoke(Action(lambda: action(form)))
        else:
            action(form)

    def set_opacity(self, percent):
        import math
        value = float(percent)
        if not math.isfinite(value) or not 40 <= value <= 100:
            raise ValueError("不透明度必须在40%到100%之间")
        value = round(value)
        if self._window is not None:
            self._native(self._window, lambda form: setattr(form, "Opacity", value / 100))
        self._opacity = value
        return self.preferences()

    def set_pinned(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("置顶状态必须为布尔值")
        if self._window is not None:
            self._native(self._window, lambda form: setattr(form, "TopMost", enabled))
        self._pinned = enabled
        return self.preferences()

    def set_compact(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("精简状态必须为布尔值")
        self._compact = enabled
        return self.preferences()

    def hide(self):
        with self._lock:
            if self._window is not None:
                self._window.hide()
            self._visible = False
            return self.state()

    def resize(self, width, height, edge):
        from webview.window import FixPoint
        edges = {"n": "NORTH", "s": "SOUTH", "w": "WEST", "e": "EAST",
                 "nw": "NORTH|WEST", "ne": "NORTH|EAST", "sw": "SOUTH|WEST", "se": "SOUTH|EAST"}
        if edge not in edges:
            raise ValueError("无效的缩放方向")
        width, height = int(width), int(height)
        if not self.MIN_SIZE[0] <= width <= 5000 or not self.MIN_SIZE[1] <= height <= 5000:
            raise ValueError("小窗尺寸超出范围")
        parts = edges[edge].split("|")
        fix = getattr(FixPoint, parts[0])
        for part in parts[1:]:
            fix |= getattr(FixPoint, part)
        if self._window is not None:
            self._window.resize(width, height, fix)

    def _shape(self, window):
        # 运行时复用主窗已验证的圆角实现，不引入透明背景/WS_THICKFRAME。
        from main_gui import apply_round_region, window_maximized
        if self._window is window:
            if not apply_round_region(window, maximized=window_maximized(window)):
                raise RuntimeError("小窗圆角设置失败")

    def _shown(self, window):
        if self._window is not window:
            return
        self._shape(window)
        self.set_opacity(self._opacity)
        self.set_pinned(self._pinned)

    def state(self):
        return {"visible": self._visible and not self._stopping}

    def set_theme(self, theme):
        if theme not in ("dark", "light", "haruka"):
            raise ValueError("不支持的主题")
        self.theme = theme
        return self.state()

    def _position(self, width, height):
        screens = self._screens()
        if not screens:
            return (60, 60)
        owner = self._owner()
        ox, oy = getattr(owner, "x", 0) or 0, getattr(owner, "y", 0) or 0
        screen = next((s for s in screens if s.x <= ox < s.x + s.width
                       and s.y <= oy < s.y + s.height), screens[0])
        # 避开屏幕边缘及常见任务栏区域；兼容负坐标的副屏。
        x = screen.x + max(12, (screen.width - width) // 2)
        y = screen.y + max(12, (screen.height - height - 48) // 2)
        return int(x), int(y)

    def _closed(self, window):
        # closed 事件异步发出；旧窗口关闭不能清掉后创建的新窗口。
        if self._window is window:
            self._window = None
            self._visible = False

    def toggle(self):
        with self._lock:
            if self._stopping:
                return self.state()
            if self._window is None:
                x, y = self._position(self.WIDTH, self.HEIGHT)
                window = self._factory(
                    self.TITLE, url=os.path.join(get_web_dir(), "capture.html"),
                    js_api=CaptureApi(self, self._feed), width=self.WIDTH, height=self.HEIGHT,
                    min_size=self.MIN_SIZE, x=x, y=y, resizable=True,
                    frameless=True, easy_drag=False, shadow=False,
                    background_color="#101015", text_select=False)
                self._window = window
                window.events.closed += lambda: self._closed(window)
                window.events.shown += lambda: self._shown(window)
                window.events.resized += lambda width, height: self._shape(window)
                self._visible = True
            elif self._visible:
                self._window.hide()
                self._visible = False
            else:
                self._window.show()
                self._window.restore()
                self._visible = True
            return self.state()

    def reset_position(self):
        with self._lock:
            if self._window is not None:
                window = self._window
                window.restore()
                x, y = self._position(window.width, window.height)
                window.move(x, y)
            # 未创建时无需创建：下次召唤本来就在默认位置。
            return self.state()

    def shutdown(self):
        with self._lock:
            self._stopping = True
            window, self._window = self._window, None
            self._visible = False
            if window is not None:
                window.destroy()
