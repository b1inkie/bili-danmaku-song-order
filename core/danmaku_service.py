# -*- coding: utf-8 -*-
"""
弹幕监听服务 - 包装 blivedm.BLiveClient，把弹幕事件转发给引擎。
blivedm 为第三方库，不做修改。
"""
import asyncio
import re

import aiohttp

import blivedm
import blivedm.models.web as web_models


class EngineDanmakuHandler(blivedm.BaseHandler):
    """弹幕回调：全部转发引擎，点歌/切歌指令由引擎统一处理"""

    def __init__(self, engine):
        self._engine = engine

    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
        self._engine.on_danmaku(message)


class DanmakuService:
    """一个直播间连接的生命周期管理"""

    def __init__(self, engine, session: aiohttp.ClientSession):
        self._engine = engine
        self._session = session
        self._client: blivedm.BLiveClient = None
        self._join_task: asyncio.Task = None

    @property
    def running(self) -> bool:
        return self._client is not None

    async def start(self, room_id: int):
        """开始监听（不阻塞，join 在后台任务里等）"""
        if self._client is not None:
            return
        client = blivedm.BLiveClient(room_id, session=self._session)
        client.set_handler(EngineDanmakuHandler(self._engine))
        client.start()
        self._client = client
        self._join_task = asyncio.get_event_loop().create_task(self._wait_join(client))

    async def _wait_join(self, client: blivedm.BLiveClient):
        """等待连接结束（彻底断开），期间 blivedm 自动重连"""
        try:
            await client.join()
        except Exception as e:
            print(f"[弹幕] 连接异常退出: {e}")
        finally:
            if self._client is client:
                self._client = None
                self._engine.on_disconnected()

    async def stop(self):
        """停止监听并释放连接"""
        client, self._client = self._client, None
        task, self._join_task = self._join_task, None
        if task is not None:
            task.cancel()
        if client is not None:
            try:
                await client.stop_and_close()
            except Exception:
                pass


# GUI 与控制台共用指令规则。
from core.song_commands import DIANGE_RE
SKIP_CMD = "下一首"
