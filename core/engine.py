# -*- coding: utf-8 -*-
"""
引擎 - 点歌机核心，独立线程跑 asyncio 事件循环。
GUI 线程通过 gui_* 方法下发指令，通过 EventBus 轮询读取事件。
"""
import asyncio
import threading
import time
from typing import Optional

import aiohttp

from core import bili_login
from core.danmaku_service import DanmakuService, DIANGE_RE, SKIP_CMD
from core.events import EventBus
from core.player import Player
from core.settings import Settings

CONFIRM_TIMEOUT = 120  # 账号确认等待秒数（超时视为同意，与控制台回车默认一致）


class Engine:
    def __init__(self):
        self.settings = Settings()
        self.bus = EventBus()
        self.player = Player()
        self.player.queue_policy = self.settings.get_queue_policy

        self.account: Optional[dict] = None   # {'uname','uid'}
        self.listening = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._dm: Optional[DanmakuService] = None
        self._stop: Optional[asyncio.Event] = None

        # 账号确认（GUI 回答）
        self._confirm_evt = threading.Event()
        self._confirm_answer: Optional[bool] = None

    # ==================== 生命周期（GUI 线程调用） ====================

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._thread_main, name="engine", daemon=True)
        self._thread.start()

    def shutdown(self):
        """窗口关闭时调用，尽量优雅退出"""
        if self._loop is not None and self._thread is not None and self._thread.is_alive():
            asyncio.run_coroutine_threadsafe(self._shutdown_async(), self._loop)
            self._thread.join(timeout=3)

    def _thread_main(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run())
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _run(self):
        self._stop = asyncio.Event()
        self._session = aiohttp.ClientSession()
        consumer = asyncio.create_task(self._queue_consumer())
        try:
            await self._auto_login()
            await self._stop.wait()
        finally:
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)
            if self.settings.get_queue_policy()["enabled"]:
                try:
                    await self.player.queue_tick(False)
                except Exception:
                    pass
            if self._dm is not None:
                await self._dm.stop()
            try:
                await self._session.close()
            except Exception:
                pass

    async def _queue_consumer(self):
        was_enabled = False
        last_error = None
        while not self._stop.is_set():
            enabled = self.settings.get_queue_policy()["enabled"]
            try:
                if enabled or was_enabled:
                    await self.player.queue_tick(enabled)
                was_enabled = enabled
                last_error = None
            except Exception as exc:
                if str(exc) != last_error:
                    self._log(f"[错误] 消费队列：{exc}")
                    last_error = str(exc)
            await asyncio.sleep(1)

    async def configure_queue(self, enabled, maximum):
        if type(enabled) is not bool or type(maximum) is not int or not 1 <= maximum <= 500:
            raise ValueError("上限必须为1至500的整数")
        if not enabled:
            result = self.settings.set_queue_policy(False, maximum)
            try:
                await self.player.queue_tick(False)
            except Exception:
                pass  # 离线也必须能关闭；客户端钩子还有15秒租约保护。
            return result
        await self.player.queue_tick(enabled)
        return self.settings.set_queue_policy(enabled, maximum)

    async def _shutdown_async(self):
        if self._dm is not None:
            await self._dm.stop()
        if self._stop is not None:
            self._stop.set()

    # ==================== 登录 ====================

    def _log(self, text: str):
        self.bus.emit("log", text=text)

    async def _auto_login(self):
        """加载cookie→验证→确认/扫码，成功后按需自动开始监听"""
        self.bus.emit("login", phase="checking")
        login_roomid = await bili_login.ensure_login(
            self._session,
            confirm_cb=self._cb_confirm,
            qr_show=lambda url: self.bus.emit("qr", action="show", url=url),
            qr_close=lambda: self.bus.emit("qr", action="hide"),
            log=self._log,
        )
        info = await bili_login.get_user_info(self._session)
        if info:
            self.account = info
            self.bus.emit("login", phase="ok", uname=info["uname"], uid=info["uid"])
        else:
            self.account = None
            self.bus.emit("login", phase="guest")

        roomid = self.settings.get_roomid()
        if not roomid and login_roomid:
            roomid = login_roomid
            self.settings.set_roomid(roomid)
            self._log(f"[配置] 使用登录账号的直播间号: {roomid}")
        if roomid and roomid.isdigit():
            await self._start_listen(int(roomid))
        else:
            self.bus.emit("need_roomid")

    async def _cb_confirm(self, uname: str, uid: int) -> bool:
        """等待账号选择但不阻塞事件循环，让网易云歌单仍可同步。"""
        self._confirm_answer = None
        self._confirm_evt.clear()
        self.bus.emit("login", phase="confirm", uname=uname, uid=uid)
        deadline = time.monotonic() + CONFIRM_TIMEOUT
        while not self._confirm_evt.is_set() and time.monotonic() < deadline:
            if self._stop is not None and self._stop.is_set():
                return False
            await asyncio.sleep(0.1)
        return True if self._confirm_answer is None else self._confirm_answer

    # ==================== 监听 ====================

    async def _start_listen(self, room_id: int):
        if self._dm is not None:
            await self._dm.stop()
        self.bus.emit("conn", state="connecting", roomid=room_id)
        self._dm = DanmakuService(self, self._session)
        await self._dm.start(room_id)
        self.listening = True
        self._log(f"[信息] 监听房间号: {room_id}  https://live.bilibili.com/{room_id}")
        self.bus.emit("conn", state="open", roomid=room_id)

    async def _stop_listen(self):
        if self._dm is not None:
            await self._dm.stop()
        self.listening = False
        self.bus.emit("conn", state="closed")

    def on_disconnected(self):
        """DanmakuService 连接彻底断开时回调（engine线程）"""
        self.listening = False
        self.bus.emit("conn", state="closed")

    # ==================== 弹幕与点歌（engine线程） ====================

    def on_danmaku(self, message):

        # 切歌（房管专属）
        if message.msg == SKIP_CMD and message.admin == 1:
            asyncio.ensure_future(self._skip_next(message.uname))
            return

        # 点歌
        m = DIANGE_RE.match(message.msg)
        if m:
            name = m.group(1)
            singer = m.group(2) or ""
            if name in self.settings.get_blacklist():
                self.bus.emit("song_blocked", name=name, requester=message.uname)
                return
            asyncio.ensure_future(self._handle_request(name, singer, message.uname, manual=False))

    async def _handle_request(self, name: str, singer: str, requester: str, manual: bool):
        """网易云搜索→确认入队；每个请求有稳定 ID，失败不会残留搜索中。"""
        import uuid
        request_id = uuid.uuid4().hex
        self.bus.emit("song", phase="requested", request_id=request_id, name=name,
                      singer=singer, requester=requester, manual=manual)
        try:
            song_info = await self.player.search(name, singer)
            # 搜索可能纠正名称；再次检查以免用关键词绕过完整歌名黑名单。
            if not manual and song_info.get("name", name).strip() in self.settings.get_blacklist():
                blocked_name = song_info.get("name", name).strip()
                self.bus.emit("song", phase="failed", request_id=request_id, name=name,
                              singer=singer, requester=requester, manual=manual, error="歌曲已被拉黑")
                self.bus.emit("song_blocked", name=blocked_name, requester=requester)
                return
            await self.player.play_search_result(song_info)
            self.player.record_request(song_info["songmid"], requester)
            self.bus.emit("song", phase="queued", request_id=request_id,
                          name=song_info.get("name", name), singer=song_info.get("singer", singer),
                          source="网易云", requester=requester, manual=manual)
        except Exception as exc:
            self.bus.emit("song", phase="failed", request_id=request_id, name=name,
                          singer=singer, source="网易云", requester=requester, manual=manual,
                          error=str(exc))
            self._log(f"[错误] 点歌失败：{exc}")

    async def _skip_next(self, by):
        try:
            await self.player.skip_next()
            self.bus.emit("skipped", by=by)
        except Exception as exc:
            self._log(f"[错误] 切歌失败：{exc}")

    # ==================== GUI 指令入口（GUI 线程调用，线程安全） ====================

    def _schedule(self, coro):
        if self._loop is None or self._thread is None or not self._thread.is_alive():
            self.bus.emit("log", text="[错误] 引擎尚未启动")
            return
        asyncio.run_coroutine_threadsafe(coro, self._loop)

    def confirm_use_account(self, ok: bool):
        self._confirm_answer = bool(ok)
        self._confirm_evt.set()

    def set_roomid_and_listen(self, roomid: str):
        roomid = str(roomid or "").strip()
        if not roomid.isdigit():
            self.bus.emit("log", text="[错误] 房间号必须是数字")
            return
        self.settings.set_roomid(roomid)
        self._schedule(self._start_listen(int(roomid)))

    def stop_listen(self):
        self._schedule(self._stop_listen())

    def request_song(self, name: str, singer: str = ""):
        name = (name or "").strip()
        if not name:
            return
        self._schedule(self._handle_request(name, (singer or "").strip(), "手动点歌", manual=True))

    def skip_next(self):
        self._schedule(self._skip_next("手动切歌"))

    def switch_account(self):
        """清除本地账号，重新扫码登录"""
        def do():
            self.confirm_use_account(False)  # 若有未决确认，先拒掉
            self._schedule(self._switch_account_async())

        do()

    async def _switch_account_async(self):
        self.bus.emit("login", phase="switching")
        if self._dm is not None:
            await self._dm.stop()
            self.listening = False
            self.bus.emit("conn", state="closed")
        bili_login.clear_saved_cookies(log=self._log)
        try:
            self._session.cookie_jar.clear()
        except Exception:
            pass
        await self._auto_login()
