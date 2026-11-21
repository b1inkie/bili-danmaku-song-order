# -*- coding: utf-8 -*-
"""
配置管理 - config.json（roomid/cookies）与歌曲黑名单。
黑名单每次实时读文件，实现 GUI 编辑后热生效。
"""
import json
import os
import tempfile
import threading
from typing import List, Set

from core.app_dir import get_config_path, get_blacklist_path


class Settings:
    _blacklist_lock = threading.RLock()
    def __init__(self):
        self.config_path = get_config_path()
        self.blacklist_path = get_blacklist_path()

    # ---------- config.json ----------

    def _read_config(self) -> dict:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_config(self, cfg: dict):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)

    def get_roomid(self) -> str:
        return str(self._read_config().get("roomid", "") or "")

    def set_roomid(self, roomid: str):
        cfg = self._read_config()
        cfg["roomid"] = str(roomid or "")
        self._write_config(cfg)

    def get_queue_policy(self):
        value = self._read_config().get("queue_policy", {})
        if not isinstance(value, dict):
            value = {}
        maximum = value.get("maximum", 10)
        if type(maximum) is not int or not 1 <= maximum <= 500:
            maximum = 10
        return {"enabled": value.get("enabled") is True, "maximum": maximum}

    def set_queue_policy(self, enabled, maximum):
        if type(enabled) is not bool or type(maximum) is not int or not 1 <= maximum <= 500:
            raise ValueError("歌单上限必须为1至500的整数")
        cfg = self._read_config()
        cfg["queue_policy"] = {"enabled": enabled, "maximum": maximum}
        self._write_config(cfg)
        return cfg["queue_policy"]

    # ---------- 黑名单 ----------

    def get_blacklist(self) -> Set[str]:
        """实时读取黑名单（热生效），返回非空歌名集合"""
        if not os.path.exists(self.blacklist_path):
            return set()
        try:
            with open(self.blacklist_path, "r", encoding="utf-8") as f:
                return {line.strip() for line in f if line.strip()}
        except OSError:
            return set()

    def get_blacklist_text(self) -> str:
        if not os.path.exists(self.blacklist_path):
            return ""
        try:
            with open(self.blacklist_path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def set_blacklist(self, lines: List[str]):
        """整表原子写回，避免引擎读取到空文件或半写入内容。"""
        cleaned = list(dict.fromkeys(ln.strip() for ln in lines if ln.strip()))
        with self._blacklist_lock:
            directory = os.path.dirname(os.path.abspath(self.blacklist_path))
            fd, temporary = tempfile.mkstemp(dir=directory, prefix=".blacklist-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write("\n".join(cleaned) + ("\n" if cleaned else ""))
                os.replace(temporary, self.blacklist_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def add_blacklisted_song(self, name: str) -> bool:
        """按完整歌名拉黑（同名不同歌手也拦截）；返回是否新增。"""
        if not isinstance(name, str) or not name.strip() or any(c in name for c in ("\r", "\n", "\x00")):
            raise ValueError("歌曲名为空或包含非法换行")
        name = name.strip()
        with self._blacklist_lock:
            lines = self.get_blacklist_text().splitlines()
            if name in {line.strip() for line in lines}:
                return False
            self.set_blacklist([*lines, name])
            return True

    # ---------- cookie（委托 bili_login 的存储格式，保持与控制台互通） ----------

    def has_cookie(self) -> bool:
        return "cookies" in self._read_config()
