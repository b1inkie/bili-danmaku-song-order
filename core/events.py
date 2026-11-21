# -*- coding: utf-8 -*-
"""
事件总线 - 引擎产生事件，GUI 通过 poll() 拉取。
线程安全：引擎线程 emit，GUI 线程 drain。
"""
import threading
from typing import List


class EventBus:
    def __init__(self, maxsize: int = 2000):
        self._lock = threading.Lock()
        self._events: List[dict] = []
        self._maxsize = maxsize

    def emit(self, etype: str, **data):
        """发一条事件（type 固定字段，其余任意）"""
        event = {"type": etype}
        event.update(data)
        with self._lock:
            self._events.append(event)
            # 防止 GUI 不在线时无限堆积
            if len(self._events) > self._maxsize:
                del self._events[: len(self._events) - self._maxsize]

    def drain(self) -> List[dict]:
        """取走并清空当前所有事件"""
        with self._lock:
            events = self._events
            self._events = []
        return events
